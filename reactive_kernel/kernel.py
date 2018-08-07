from ipykernel.kernelbase import Kernel
import sys
from .code_object import CodeObject
from .execute import ExecutionContext
from .captured_io import CapturedIOCtx
from .captured_display import CapturedDisplayCtx
from .dependencies import DependencyTracker
import traceback as tb

__version__ = '0.1.0'


class ReactivePythonKernel(Kernel):
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
        self.execution_ctx = ExecutionContext()

        self.dep_tracker = DependencyTracker()

    def do_execute(self, code, silent, store_history=True, user_expressions=None,
                   allow_stdin=False):
        try:
            code_obj = CodeObject(code)

            if code_obj in self.dep_tracker:
                self._update_code_object(code_obj)
            else:
                self._register_new_code_object(code_obj)

            with CapturedIOCtx() as captured_io, CapturedDisplayCtx() as a:
                self.execution_ctx._run_cell(code)

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

        if not silent:
            stream_content = {
                'name': 'stdout', 'text': str(
                    self.dep_tracker.order_nodes())}
            self.send_response(self.iopub_socket, 'stream', stream_content)

        if not silent:
            if len(captured_io.stdout) > 0:
                self.send_response(
                    self.iopub_socket, 'stream', {
                        'name': 'stdout', 'text': captured_io.stdout})

            if len(captured_io.stderr) > 0:
                self.send_response(
                    self.iopub_socket, 'stream', {
                        'name': 'stderr', 'text': captured_io.stderr})

        return {'status': 'ok',
                'execution_count': self.execution_count,
                }

    def _update_code_object(self, new_code_obj):
        self.log.debug("Updating existing code object", exc_info=True)
        old_code_obj = self.dep_tracker[new_code_obj]

        new_input_vars = set(new_code_obj.input_vars)
        old_input_vars = set(old_code_obj.input_vars)

        to_delete = old_input_vars - new_input_vars
        to_add = new_input_vars - old_input_vars

        self.dep_tracker.start_transaction()

        try:
            self.dep_tracker.replace_node(new_code_obj)

            for sym in to_delete:
                defining_code = self.dep_tracker.get_code_defining_symbol(sym)
                self.dep_tracker.delete_edge(defining_code, new_code_obj)

            for sym in to_add:
                defining_code = self.dep_tracker.get_code_defining_symbol(sym)
                self.dep_tracker.add_edge(defining_code, new_code_obj)

            self.dep_tracker.commit()
        except Exception as e:
            # rollback changes made to dep graph
            self.dep_tracker.rollback()

            raise e

    def _register_new_code_object(self, code_obj):
        self.dep_tracker.add_node(code_obj)

        self.dep_tracker.start_transaction()

        for sym in code_obj.input_vars:
            defining_code = self.dep_tracker.get_code_defining_symbol(sym)
            self.dep_tracker.add_edge(defining_code, code_obj)

        self.dep_tracker.commit()
