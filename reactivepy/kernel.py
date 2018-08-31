import sys
import traceback as tb
from typing import Union, Any, Dict, FrozenSet
from importlib.abc import InspectLoader
from asyncio.locks import Lock
from asyncio import Queue
import asyncio
import time
from functools import partial
from typing import Union, Tuple, List
import random
import string
import inspect
import builtins as builtin_mods
from ipykernel.kernelbase import Kernel
from IPython.core.formatters import DisplayFormatter
import IPython.core.ultratb as ultratb
from tornado.ioloop import IOLoop
from ipython_genutils import py3compat
from ipykernel.jsonutil import json_clean
from graphviz import Digraph
from .code_object import CodeObject, SymbolWrapper
from .execute import Executor, ExecutionResult, CapturedIOCtx
from .dependencies import DependencyTracker
from .transactional import TransactionDict, TransactionalABC
from .user_namespace import BuiltInManager

__version__ = '0.1.0'


class ExecutionUnitInfo:
    """ Container of all relevant information needed to update, execute, and display any code sent"""

    def __init__(self, code_obj: CodeObject,
                 pinning_cell: Union[None, str]=None):
        self.code_obj = code_obj
        self.display_id: str = code_obj.display_id
        self.stdout_display_id: str = f"{code_obj.display_id}-stdout"
        self.pinning_cell: Union[None, str] = pinning_cell

    @property
    def is_pinned(self):
        return self.pinning_cell is not None

    def __eq__(self, other):
        if isinstance(other, ExecutionUnitInfo):
            return self.code_obj.display_id == other.code_obj.display_id
        return False

    def unpin(self):
        self.pinning_cell = None

    def __repr__(self):
        return f"<ExecUnitInfo id='{self.display_id}' owning_cell='{self.pinning_cell}' code='{self.code_obj.code}'>"


class RedefiningOwnedCellException(Exception):
    """Code object is already tied to a different, existing cell

    Execution units (code objects) may only be owned by a single cell at a time.

    The prior defining cell must be deleted before it can be redefined in a different cell
    """
    pass


class DefinitionNotFoundException(Exception):
    """No definition was found for the given input variable

    Variables must be defined in a code cell before they are used
    """
    pass


class ExecUnitContainer(InspectLoader, TransactionalABC):

    def __init__(self, *args, **kwargs):
        super(ExecUnitContainer, self).__init__(*args, **kwargs)

        # Maps display id to execution unit info
        self._data = TransactionDict()
        # Maps cell id to display id
        self._cell_id_to_display_id = TransactionDict()
        # Maps symbol to display id
        self._symbol_to_display_id = TransactionDict()

    def register(self, exec_unit: ExecutionUnitInfo):
        display_id = exec_unit.code_obj.display_id

        assert display_id not in self._data

        # Register in main index
        self._data[display_id] = exec_unit

        if exec_unit.is_pinned:
            self._cell_id_to_display_id[exec_unit.pinning_cell] = display_id

        for symbol in exec_unit.code_obj.output_vars:
            self._symbol_to_display_id[symbol] = display_id

        return exec_unit

    def contains_display_id(self, display_id: str):
        return display_id in self._data

    def get_by_display_id(self, display_id: str):
        if display_id in self._data:
            return self._data[display_id]
        else:
            return None

    def get_by_symbol(self, symbol: SymbolWrapper):
        if symbol in self._symbol_to_display_id:
            display_id = self._symbol_to_display_id[symbol]
            return self._data[display_id]
        else:
            return None

    def get_by_cell_id(self, cell_id: str):
        if cell_id in self._cell_id_to_display_id:
            display_id = self._cell_id_to_display_id[cell_id]
            return self._data[display_id]
        else:
            return None

    def unpin_exec_unit(self, cell_id: str):
        if cell_id in self._cell_id_to_display_id:
            display_id = self._cell_id_to_display_id[cell_id]
            exec_unit = self._data[display_id]

            if exec_unit is not None:
                exec_unit.unpin()

            del self._cell_id_to_display_id[cell_id]
            return True
        else:
            return False

    def get_source(self, display_id: str):
        if display_id in self._data:
            return self._data[display_id].code_obj.code
        else:
            raise ImportError()

    def start_transaction(self):
        self._data.start_transaction()
        self._cell_id_to_display_id.start_transaction()
        self._symbol_to_display_id.start_transaction()

    def commit(self):
        self._data.commit()
        self._cell_id_to_display_id.commit()
        self._symbol_to_display_id.commit()

    def rollback(self):
        self._data.rollback()
        self._cell_id_to_display_id.rollback()
        self._symbol_to_display_id.rollback()


def generate_id(size=24, chars=(string.ascii_letters + string.digits)):
    return ''.join(random.choice(chars) for _ in range(size))


class RequestInfo:
    def __init__(self, parent, ident):
        self.parent = parent
        self.ident = ident
        content = self.content = parent[u'content']
        header = self.header = parent['header']
        self.code = py3compat.cast_unicode_py2(content[u'code'])
        self.silent = content[u'silent']
        self.store_history = content.get(u'store_history', not self.silent)
        self.user_expressions = content.get('user_expressions', {})
        self.allow_stdin = content.get('allow_stdin', False)
        self.metadata = parent[u'metadata']
        self.msg_id = header['msg_id']
        self.msg_type = header['msg_type']

        # Fields to populate later
        self.execution_count = None


class ExecBlock:
    COUNTER = 0

    def __init__(self, request: RequestInfo, current_exec_unit: ExecutionUnitInfo,
                 descendant_exec_units: List[ExecutionUnitInfo], async_gen_obj=None):
        self.current = current_exec_unit
        self.descendants = descendant_exec_units
        self.request = request

        # Is this block of execution from a previous iteration
        self.is_iter_exec = async_gen_obj is not None
        self.async_gen_obj = async_gen_obj

        ExecBlock.COUNTER += 1
        self.id = ExecBlock.COUNTER


class AsyncGenContainer:
    def __init__(self):
        # Mapping from target id (variable name) to current async generator
        self.generators = dict()


class ReactivePythonKernel(Kernel):
    implementation = 'reactivepy'
    implementation_version = __version__
    language_info = {
        'name': 'python',
        'version': sys.version.split()[0],
        'nbconvert_exporter': 'python',
        'mimetype': 'text/x-python',
        'file_extension': '.py'
    }
    banner = ''

    # measured in seconds. This value is intended to delay the same amount as
    # 60fps does between frames
    REGULAR_GENERATOR_DELAY = 0.016666

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._eventloop = IOLoop.current()
        self._key = generate_id(size=32).encode('utf-8')
        self._execution_lock = Lock(loop=self._eventloop.asyncio_loop)
        self._inner_state_lock = Lock(loop=self._eventloop.asyncio_loop)
        self._dep_tracker = DependencyTracker()
        self._exec_unit_container = ExecUnitContainer()
        self.formatter = DisplayFormatter()
        self.ns_manager = BuiltInManager()
        self.initialize_builtins()
        self._execution_ctx = Executor(
            self._exec_unit_container, ns_manager=self.ns_manager)
        self.KernelTB = ultratb.AutoFormattedTB(mode='Plain',
                                                color_scheme='LightBG',
                                                tb_offset=1,
                                                debugger_cls=None)
        self._execution_queue = Queue(loop=self._eventloop.asyncio_loop)
        self._registered_generators = dict()

        self._eventloop.spawn_callback(
            self._execution_loop)
    
    def initialize_builtins(self):
        self.ns_manager.add_builtin('var_dependency_graph', self._var_dependency_graph)
        self.ns_manager.add_builtin('cell_dependency_graph', self._cell_dependency_graph)


    def _var_dependency_graph(self):
        h = Digraph()
        for start_node in self._dep_tracker.get_nodes():
            if "-" in start_node:
                for dest_node in self._dep_tracker.get_neighbors(start_node):
                    if "-" in dest_node:
                        first = start_node[:start_node.find('-')]
                        second = dest_node[:dest_node.find('-')]
                        for char in "[]":
                            first = first.replace(char, "")
                            second = second.replace(char, "")
                        h.edge(first, second)
        return h
    
    def _cell_dependency_graph(self):
        h = Digraph()
        for start_node in self._dep_tracker.get_nodes():
            if "-" in start_node:
                for dest_node in self._dep_tracker.get_neighbors(start_node):
                    if "-" in dest_node:
                        first = self._exec_unit_container.get_by_display_id(start_node).pinning_cell
                        second = self._exec_unit_container.get_by_display_id(dest_node).pinning_cell
                        h.edge(first,second)
        return h

    async def _run_single_async_iter_step(self, item, exec_unit):
        # Make sure only single variable is important for execution
        # unit
        assert len(exec_unit.code_obj.output_vars) == 1
        target_id = list(
            exec_unit.code_obj.output_vars)[0].get_name()

        request_id, async_gen_obj, insert_id = self._registered_generators[
            target_id]
        async with self._inner_state_lock:
            if request_id != item.request.msg_id and insert_id < item.id:
                # self._log(item.request,
                #           f"Cancelling ({request_id}, {insert_id}) for ({item.request.msg_id}, {item.id}) 1")
                await async_gen_obj.aclose()

                self._registered_generators[target_id] = item.request.msg_id, item.async_gen_obj, item.id
            elif insert_id > item.id:
                return None

        try:
            exec_result = await self._execution_ctx.run_coroutine(anext(item.async_gen_obj), target_id, nohandle_exceptions=(StopAsyncIteration, ))
        except StopAsyncIteration as e:
            # iteration is complete
            raise e

        # Schedule next instance of iterator
        # Compute execution units which depend on this unit,
        # and schedule a new block to run which contains them
        descendants = self._dep_tracker.get_descendants(
            exec_unit.display_id)
        descendant_exec_units = list(
            map(lambda display_id: self._exec_unit_container.get_by_display_id(display_id), descendants))

        next_iter_round = ExecBlock(
            item.request,
            exec_unit,
            descendant_exec_units,
            async_gen_obj=item.async_gen_obj)
        await self._execution_queue.put(next_iter_round)

        return exec_result

    async def _first_async_iter_step(self, item: ExecBlock, exec_unit: ExecutionUnitInfo, exec_result: ExecutionResult):
        # self._log(item.request, "Before inner state lock")
        async with self._inner_state_lock:
            # self._log(item.request, "After inner state lock")
            if exec_result.target_id in self._registered_generators:
                request_id, async_gen_obj, insert_id = self._registered_generators[
                    exec_result.target_id]

                if insert_id < item.id:
                    # self._log(
                    #     item.request, f"Cancelling ({request_id}, {insert_id}) for ({item.request.msg_id}, {item.id}) 2")

                    await async_gen_obj.aclose()
                else:
                    raise ValueError(
                        f"Very confuse. {insert_id} vs {item.id}")

            # self._log(
            #     item.request,
            #     f"Storing {(item.request.msg_id, exec_result.output, item.id)}")
            self._registered_generators[exec_result.target_id] = item.request.msg_id, exec_result.output, item.id

        # Get first value and replace async gen with first
        # value or None
        async_gen_obj = exec_result.output
        try:
            exec_result.output = await anext(exec_result.output)
        except Exception:
            # DO not schedule further updates on failure
            return False

        # Schedule next instance of iterator
        # Compute execution units which depend on this unit,
        # and schedule a new block to run which contains
        # them
        descendants = self._dep_tracker.get_descendants(
            exec_unit.display_id)
        descendant_exec_units = list(
            map(lambda display_id: self._exec_unit_container.get_by_display_id(display_id), descendants))
        next_iter_round = ExecBlock(
            item.request, exec_unit, descendant_exec_units, async_gen_obj=async_gen_obj)

        await self._execution_queue.put(next_iter_round)

        return True

    async def _execution_loop(self):
        while True:
            item: ExecBlock = await self._execution_queue.get()
            # self._log(item.request, f"Handling {item.request.msg_id}")
            if item is None:
                # Use None to signal end
                # self._log(item.request, 'Breaking execution loop!')
                break

            for exec_unit in ([item.current] + item.descendants):
                # async with self._execution_lock:
                # self._log(item.request, exec_unit.display_id)

                is_current = exec_unit == item.current
                is_iter = item.is_iter_exec and is_current

                if is_iter:
                    # self._log(item.request, "Stepping iter")

                    try:
                        exec_result = await self._run_single_async_iter_step(item, exec_unit)
                    except StopAsyncIteration:
                        # self._log(item.request,
                        #           'Step failed, breaking exec unit loop!')
                        break
                else:
                    # self._log(item.request, "Executing normally")
                    # Execute code normally
                    exec_result = self._execution_ctx.run_cell(
                        exec_unit.code_obj.code, exec_unit.display_id)

                if exec_result.output is not None and not is_iter:
                    is_awaitable, is_gen, is_async_gen = inspect_output_attrs(
                        exec_result.output)
                    # self._log(item.request,
                    #           f"{is_awaitable} {is_gen} {is_async_gen}")

                    # These flags should be disjoint (never multiple True at same time)
                    # but this layout allows for transforming a regular generator into an async generator
                    # with a small timeout, and then passing it to the
                    # async_gen branch

                    # If the output is awaitable, wait for it and then replace
                    # the old output
                    if is_awaitable:
                        exec_result.output = await exec_result.output

                    # If the output is a regular generator, wrap it in an async
                    # generator that will add a very small delay
                    if is_gen:
                        exec_result.output = convert_gen_to_async(
                            exec_result.output, ReactivePythonKernel.REGULAR_GENERATOR_DELAY)()
                        is_async_gen = True
                        is_gen = False

                    # If it is an async generator, either replace the old
                    # generator that was active for this target name or
                    # register this completely new generator. Remove the old
                    # generator by canceling it
                    if is_async_gen:
                        # self._log(item.request, "Is now async gen!")
                        setup_succeeded = await self._first_async_iter_step(
                            item, exec_unit, exec_result)

                        if not setup_succeeded:
                            break

                    if is_awaitable or is_gen or is_async_gen:
                        self._execution_ctx.update_ns(
                            {exec_result.target_id: exec_result.output})

                if not item.request.silent:
                    self._output_exec_results(
                        exec_unit, item.request, is_current and not is_iter, exec_result)

            self._execution_queue.task_done()

    def _update_existing_exec_unit(self, code_obj, cell_id):
        # 4a. If it is a redefinition, get the old execution unit
        current_exec_unit = self._exec_unit_container.get_by_display_id(
            code_obj.display_id)

        if current_exec_unit.is_pinned and current_exec_unit.pinning_cell != cell_id:
            raise RedefiningOwnedCellException

        old_code_obj = current_exec_unit.code_obj

        new_input_vars = set(code_obj.input_vars)
        old_input_vars = set(old_code_obj.input_vars)

        # 4b. Compute the sets of edges to be added and deleted if the
        # variable dependencies of the cell have changed
        to_delete = old_input_vars - new_input_vars
        to_add = new_input_vars - old_input_vars

        # 4c. Actually replace old code object, delete old edges,
        # add new edges
        exec_unit = self._exec_unit_container.get_by_display_id(
            code_obj.display_id)
        exec_unit.code_obj = code_obj

        for sym in to_delete:
            code_object_id = self._exec_unit_container.get_by_symbol(
                sym).code_obj.display_id
            self._dep_tracker.delete_edge(
                code_object_id, code_obj.display_id)

        for sym in to_add:
            code_object_id = self._exec_unit_container.get_by_symbol(
                sym).code_obj.display_id
            self._dep_tracker.add_edge(
                code_object_id, code_obj.display_id)

        # 4d. Get the updated execution unit and return it
        return self._exec_unit_container.get_by_display_id(
            code_obj.display_id)

    def _create_new_exec_unit(self, code_obj, cell_id):
        # 4a. Create new execution unit to hold code object + display
        # id + cell id data
        current_exec_unit = self._exec_unit_container.register(ExecutionUnitInfo(
            code_obj, pinning_cell=cell_id))

        # 4b. Add new node
        self._dep_tracker.add_node(code_obj.display_id)

        # 4c. For each variable it depends on, find the complete set of
        # defining variables (all the variables that were defined in
        # the same code block), and create a dependency to them
        for sym in code_obj.input_vars:
            dep = self._exec_unit_container.get_by_symbol(sym)

            if dep is not None:
                code_object_id = dep.code_obj.display_id
                self._dep_tracker.add_edge(
                    code_object_id, code_obj.display_id)
            else:
                raise DefinitionNotFoundException(str(sym))

        return current_exec_unit

    async def _inner_execute_request_callback(self, stream, ident, parent):
        # COPIED FROM IPYKERNEL/KERNELBASE.PY
        # async with self._execution_lock:
        try:
            request = RequestInfo(parent, ident)
        except BaseException:
            self.log.error(f"Got bad msg: {parent}")
            return

        # Re-broadcast our input for the benefit of listening clients, and
        # start computing output
        if not request.silent:
            request.execution_count = self.execution_count = 1 + self.execution_count
            self._publish_execute_input(
                request.code, parent, request.execution_count)

        stop_on_error = request.content.get('stop_on_error', True)

        response_meta = self.init_metadata(parent)

        reply_content = await self.do_execute(request)

        # Flush output before sending the reply.
        sys.stdout.flush()
        sys.stderr.flush()
        # FIXME: on rare occasions, the flush doesn't seem to make it to the
        # clients... This seems to mitigate the problem, but we definitely need
        # to better understand what's going on.
        if self._execute_sleep:
            time.sleep(self._execute_sleep)

        # Send the reply.
        reply_content = json_clean(reply_content)
        response_meta = self.finish_metadata(
            parent, response_meta, reply_content)

        reply_msg = self.session.send(stream, u'execute_reply',
                                      reply_content, parent, metadata=response_meta,
                                      ident=ident)

        self.log.debug(f"{reply_msg}")

        if not request.silent and reply_msg['content']['status'] == u'error' and stop_on_error:
            self._abort_queues()

    def execute_request(self, stream, ident, parent):
        """handle an execute_request"""

        self._eventloop.spawn_callback(
            self._inner_execute_request_callback,
            stream, ident, parent)

    def _update_kernel_state(self, code_obj,
                             cell_id, deleted_cell_ids):
        # 3. If deletedCells was passed, then unpin all execution units
        # that were previously attached to a cell
        if deleted_cell_ids is not None:
            for to_delete_cell_id in deleted_cell_ids:
                self._exec_unit_container.unpin_exec_unit(to_delete_cell_id)

        self._dep_tracker.start_transaction()
        self._exec_unit_container.start_transaction()

        try:
            # 4. Test if the code is new or a redefinition
            if self._exec_unit_container.contains_display_id(
                    code_obj.display_id):
                current_exec_unit = self._update_existing_exec_unit(
                    code_obj, cell_id)
            else:
                current_exec_unit = self._create_new_exec_unit(
                    code_obj, cell_id)
        except Exception as e:
            # rollback changes made to dep graph
            self._dep_tracker.rollback()
            self._exec_unit_container.rollback()

            raise e
        else:
            self._dep_tracker.commit()
            self._exec_unit_container.commit()

        return current_exec_unit

    def _output_exec_results(
            self, exec_unit: ExecutionUnitInfo, request: RequestInfo, is_current: bool, exec_result: ExecutionResult):

        # 6b. Determine whether the current execution unit will be
        # directly display or update
        message_mode = 'update_display_data' if not is_current else 'display_data'

        # 6c. Create rich outputs for captured output
        if exec_result.output is not None:
            data, md = self.formatter.format(exec_result.output)
        else:
            data, md = {}, {}

        stdout, stderr = exec_result.stdout.getvalue(), exec_result.stderr.getvalue()

        # 6d. For the captured output value, stdout, and stderr
        # send appropriate responses back to the front-end
        if len(stdout) > 0:
            self.session.send(self.iopub_socket, message_mode, content={
                'data': {
                    'text/plain': stdout
                },
                'metadata': {},
                'transient': {
                    'display_id': exec_unit.stdout_display_id
                }
            }, parent=request.parent)

        if exec_result.output is not None:
            self.session.send(self.iopub_socket, message_mode, content={
                'data': data,
                'metadata': md,
                'transient': {
                    'display_id': exec_unit.display_id
                }
            }, parent=request.parent)

        if len(stderr) > 0:
            self.session.send(
                self.iopub_socket, 'stream', content={
                    'name': 'stderr', 'text': stderr}, parent=request.parent)

    def _log(self, request, text):
        self.session.send(
            self.iopub_socket, 'stream', content={
                'name': 'stdout', 'text': text + '\n'}, parent=request.parent)

    async def do_execute(self, request: RequestInfo):
        try:
            # 1. Create code object
            code_obj = CodeObject(request.code, self._key,
                                  self._execution_ctx.ns_manager)

            # 2. Extract metadata (both are optional)
            cell_id = request.metadata['cellId'] if 'cellId' in request.metadata else None
            deleted_cell_ids = request.metadata[
                'deletedCells'] if 'deletedCells' in request.metadata else None

            # Doesn't need lock because the code inside _update_kernel_state
            # will never await. If that ever changes, uncomment lock below
            async with self._inner_state_lock:
                current_exec_unit = self._update_kernel_state(
                    code_obj, cell_id, deleted_cell_ids)

                # 5. Compute the dependant execution units which must be rerun, and
                # add the current execution unit to the front of the list
                descendants = self._dep_tracker.get_descendants(
                    code_obj.display_id)
                descendant_exec_units = list(
                    map(lambda display_id: self._exec_unit_container.get_by_display_id(display_id), descendants))

            block = ExecBlock(
                request,
                current_exec_unit,
                descendant_exec_units)
            await self._execution_queue.put(block)

        except Exception:
            etype, value, tb = sys.exc_info()
            stb = self.KernelTB.structured_traceback(
                etype, value, tb
            )
            formatted_lines = self.KernelTB.stb2text(stb).splitlines()

            error_content = {
                'ename':
                    str(etype),
                    'evalue': str(value),
                    'traceback': formatted_lines}
            if not request.silent:
                self.session.send(self.iopub_socket,
                                  'error', content=error_content, parent=request.parent)
            error_content['status'] = 'error'

            return error_content

        return {'status': 'ok',
                'execution_count': request.execution_count,
                }


async def anext(*args):
    if len(args) < 1:
        raise TypeError(
            f"anext expected at least 1 arguments, got {len(args)}")

    aiterable, default, has_default = args[0], None, False

    if len(args) > 2:
        raise TypeError(f"anext expected at most 2 arguments, got {len(args)}")

    if len(args) == 2:
        default = args[1]
        has_default = True

    try:
        return await aiterable.__anext__()
    except StopAsyncIteration as exc:
        if has_default:
            return default
        raise StopAsyncIteration() from exc


def inspect_output_attrs(obj):
    is_awaitable = inspect.isawaitable(obj)
    is_gen = inspect.isgenerator(obj)
    is_async_gen = inspect.isasyncgen(obj)

    return (is_awaitable, is_gen, is_async_gen)


def convert_gen_to_async(gen, delay):
    async def inner_async_gen():
        for value in gen:
            yield value
            await asyncio.sleep(delay)

    return inner_async_gen
