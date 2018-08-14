from ipykernel.kernelbase import Kernel
import sys
from .code_object import CodeObject, SymbolWrapper
from .execute import ExecutionContext
from .captured_io import CapturedIOCtx
from .captured_display import CapturedDisplayCtx
from .dependencies import DependencyTracker
import traceback as tb
from typing import Union, Any, Dict, FrozenSet
from IPython.core.formatters import DisplayFormatter
import IPython.core.ultratb as ultratb
from importlib.abc import InspectLoader
from .transactional import TransactionDict, TransactionalABC


__version__ = '0.1.0'


class MetadataBaseKernel(Kernel):

    def init_metadata(self, parent):
        """Initialize metadata.

        Run at the beginning of execution requests.
        """

        self.current_metadata = super(
            MetadataBaseKernel, self).init_metadata(parent)
        return self.current_metadata

    def finish_metadata(self, parent, metadata, reply_content):
        """Finish populating metadata.

        Run after completing an execution request.
        """
        self.current_metadata = None
        return super(MetadataBaseKernel, self).finish_metadata(
            parent, metadata, reply_content)


class ExecutionUnitInfo:
    """ Container of all relevant information needed to update, execute, and display any code sent"""

    def __init__(self, code_obj: CodeObject,
                 pinning_cell: Union[None, str]=None):
        self.code_obj = code_obj
        self.display_id: str = code_obj.display_id
        self.stdout_display_id: str = 'stdout-' + code_obj.display_id
        self.pinning_cell: Union[None, str] = pinning_cell

    @property
    def is_pinned(self):
        return self.pinning_cell is not None

    def __eq__(self, other):
        if isinstance(other, ExecutionUnitInfo):
            return self.code_obj.display_id == other.code_obj.display_id
        return False

    def pin(self, cell_id: str):
        if self.is_pinned:
            raise RedefiningOwnedCellException
        else:
            self.pinning_cell = cell_id

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


class ReactivePythonKernel(MetadataBaseKernel):
    implementation = 'reactive_python'
    implementation_version = __version__
    language_info = {
        'name': 'python',
        'version': sys.version.split()[0],
        'nbconvert_exporter': 'python',
        'mimetype': 'text/x-python',
        'file_extension': '.py'
    }
    banner = ''

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._dep_tracker = DependencyTracker()
        self._exec_unit_container = ExecUnitContainer()
        self.formatter = DisplayFormatter()
        self._execution_ctx = ExecutionContext(
            self._exec_unit_container, loop=self.eventloop)
        self.SyntaxTB = ultratb.SyntaxTB(color_scheme='NoColor')

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
                raise DefinitionNotFoundException()

        return current_exec_unit

    def do_execute(self, code: str, silent: bool, store_history=True, user_expressions=None,
                   allow_stdin=False):
        try:
            # TODO: Encapsulate the related portions of these steps into
            # functions or classes

            # 1. Create code object
            code_obj = CodeObject(code)

            # 2. Extract metadata (both are optional)
            cell_id = self.current_metadata['cellId'] if 'cellID' in self.current_metadata else None
            deleted_cell_ids = self.current_metadata[
                'deletedCells'] if 'deletedCells' in self.current_metadata else None

            # 3. If deletedCells was passed, then unpin all execution units
            # that were previously attached to a cell
            if deleted_cell_ids is not None:
                for cell_id in deleted_cell_ids:
                    self._exec_unit_container.unpin_exec_unit(cell_id)

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

            # 5. Compute the dependant execution units which must be rerun, and
            # add the current execution unit to the front of the list
            descendants = self._dep_tracker.get_descendants(
                code_obj.display_id)
            to_run = [current_exec_unit] + list(
                map(lambda display_id: self._exec_unit_container.get_by_display_id(display_id), descendants))

            # 6. For each execution unit which must be run
            for exec_unit in to_run:
                # 6a. Run the code and capture everything written to stdout,
                # stderr, and the displayhook
                with CapturedIOCtx() as captured_io, CapturedDisplayCtx() as captured_output:
                    self._execution_ctx.run_cell(
                        exec_unit.code_obj.code, exec_unit.display_id)

                if not silent:
                    # 6b. Determine whether the current execution unit will be
                    # directly display or update
                    message_mode = 'update_display_data' if exec_unit != current_exec_unit else 'display_data'

                    # 6c. Create rich outputs for captured output
                    if len(captured_output.values) > 0:
                        data, md = self.formatter.format(
                            captured_output.values[0])
                    else:
                        data, md = {}, {}

                    # 6d. For the captured output value, stdout, and stderr
                    # send appropriate responses back to the front-end
                    if len(captured_io.stdout) > 0:
                        self.send_response(
                            self.iopub_socket, message_mode, {
                                'data': {
                                    'text/plain': captured_io.stdout
                                },
                                'metadata': {},
                                'transient': {
                                    'display_id': exec_unit.stdout_display_id
                                }
                            })

                    if len(captured_output.values) > 0:
                        self.send_response(self.iopub_socket, message_mode, {
                            'data': data,
                            'metadata': md,
                            'transient': {
                                'display_id': exec_unit.display_id
                            }
                        })

                    if len(captured_io.stderr) > 0:
                        self.send_response(
                            self.iopub_socket, 'stream', {
                                'name': 'stderr', 'text': captured_io.stderr})

        except Exception as e:
            formatted_lines = tb.format_exc().splitlines()

            error_content = {
                'ename':
                    e.__class__.__name__,
                    'evalue': str(e),
                    'traceback': formatted_lines}
            if not silent:
                self.send_response(self.iopub_socket,
                                   'error', error_content)
            error_content['status'] = 'error'

            return error_content

        return {'status': 'ok',
                'execution_count': self.execution_count,
                }
