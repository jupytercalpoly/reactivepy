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
    """ Container of all relevant information needed to update, execute, and display any code sent

    """

    def __init__(self, code_obj: CodeObject,
                 pinning_cell: Union[None, str]=None):
        self.code_obj = code_obj
        self.display_id: str = code_obj.display_id
        self.stdout_display_id: str = 'stdout-' + code_obj.display_id
        self.pinning_cell: Union[None, str] = pinning_cell
        self.has_run_before = False

    @property
    def is_pinned(self):
        return self.pinning_cell is not None

    def __eq__(self, other):
        if isinstance(other, ExecutionUnitInfo):
            return self.code_obj.display_id == other.code_obj.display_id
        return False

    def pin(self, cell_id: str):
        if self.is_pinned:
            raise RePinningExecutionUnitException
        else:
            self.pinning_cell = cell_id

    def unpin(self):
        self.pinning_cell = None


class RePinningExecutionUnitException(Exception):
    """Execution unit is already tied to a single existing cell

    An already pinned (owned) execution unit may only have a single owning cell
    """
    pass


class RedefiningOwnedCellException(Exception):
    """Code object is already tied to a different, existing cell

    Execution units (code objects) may only be tied (owned/pinned) to a single cell at a time.

    The prior defining cell must be deleted before it can be redefined in a different cell
    """


class ReactivePythonKernel(MetadataBaseKernel):
    implementation = 'reactive_python'
    implementation_version = __version__
    language_info = {
        'name': 'python',
        'version': sys.version.split()[0],
        'mimetype': 'text/x-python',
        'nbconvert_exporter': 'python',
        'file_extension': '.py'
    }
    banner = ''

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._execution_ctx = ExecutionContext()
        self._dep_tracker = DependencyTracker()
        self._execution_units: Dict[FrozenSet[SymbolWrapper],
                                    ExecutionUnitInfo] = dict()
        self._cell_id_to_exec_unit: Dict[str, ExecutionUnitInfo] = dict()
        self._symbol_to_exec_unit: Dict[SymbolWrapper,
                                        ExecutionUnitInfo] = dict()
        self.formatter = DisplayFormatter()

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
                    self._cell_id_to_exec_unit[cell_id].unpin()

            # 4. Test if the code is new or a redefinition
            if code_obj.display_id in self._execution_units:
                # 4a. If it is a redefinition, get the old execution unit
                current_exec_unit = self._execution_units[code_obj.display_id]

                if current_exec_unit.is_pinned and current_exec_unit.pinning_cell != cell_id:
                    raise RedefiningOwnedCellException

                old_code_obj = current_exec_unit.code_obj

                new_input_vars = set(code_obj.input_vars)
                old_input_vars = set(old_code_obj.input_vars)

                # 4b. Compute the sets of edges to be added and deleted if the
                # variable dependencies of the cell have changed
                to_delete = old_input_vars - new_input_vars
                to_add = new_input_vars - old_input_vars

                self._dep_tracker.start_transaction()

                try:
                    # 4c. Actually replace old code object, delete old edges,
                    # add new edges
                    self._execution_units[code_obj.display_id].code_obj = code_obj

                    for sym in to_delete:
                        code_object_id = self._symbol_to_exec_unit[sym].code_obj.display_id
                        self._dep_tracker.delete_edge(
                            code_object_id, code_obj.display_id)

                    for sym in to_add:
                        code_object_id = self._symbol_to_exec_unit[sym].code_obj.display_id
                        self._dep_tracker.add_edge(
                            code_object_id, code_obj.display_id)

                    self._dep_tracker.commit()
                except Exception as e:
                    # rollback changes made to dep graph
                    self._dep_tracker.rollback()
                    self._execution_units[code_obj.display_id].code_obj = old_code_obj

                    raise e
            else:
                # 4a. Create new execution unit to hold code object + display
                # id + cell id data
                current_exec_unit = self._execution_units[code_obj.display_id] = ExecutionUnitInfo(
                    code_obj, pinning_cell=cell_id)

                # 4b. If execution unit is pinned (owned) by a cell, add to
                # auxilary index
                if current_exec_unit.is_pinned:
                    self._cell_id_to_exec_unit[current_exec_unit.pinning_cell] = current_exec_unit

                # 4c. Add new node
                self._dep_tracker.add_node(code_obj.display_id)

                self._dep_tracker.start_transaction()

                for sym in code_obj.output_vars:
                    self._symbol_to_exec_unit[sym] = current_exec_unit

                # 4d. For each variable it depends on, find the complete set of
                # defining variables (all the variables that were defined in
                # the same code block), and create a dependency to them
                for sym in code_obj.input_vars:
                    code_object_id = self._symbol_to_exec_unit[sym].code_obj.display_id
                    self._dep_tracker.add_edge(
                        code_object_id, code_obj.display_id)

                self._dep_tracker.commit()

            # 5. Compute the dependant execution units which must be rerun, and
            # add the current execution unit to the front of the list
            descendants = self._dep_tracker.get_descendants(
                code_obj.display_id)
            to_run = [current_exec_unit] + list(
                map(lambda display_id: self._execution_units[display_id], descendants))

            # 6. For each execution unit which must be run
            for exec_unit in to_run:
                # 6a. Run the code and capture everything written to stdout,
                # stderr, and the displayhook
                with CapturedIOCtx() as captured_io, CapturedDisplayCtx() as captured_output:
                    self._execution_ctx.run_cell(exec_unit.code_obj.code)

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
