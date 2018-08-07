from ipykernel.kernelbase import Kernel
import sys
from .codeObject import CodeObject
from .execute import ExecutionContext
from .captured_io import CapturedIOCtx
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

    def do_execute(self, code, silent, store_history=True, user_expressions=None,
                   allow_stdin=False):

        if not silent:
            try:
                with CapturedIOCtx() as captured_io:
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
                if len(captured_io.stdout) > 0:
                    self.send_response(
                        self.iopub_socket, 'stream', {
                            'name': 'stdout', 'text': captured_io.stdout})

                if len(captured_io.stderr) > 0:
                    self.send_response(
                        self.iopub_socket, 'stream', {
                            'name': 'stderr', 'text': captured_io.stderr})

        return {
            'status': 'ok',
            'execution_count': self.execution_count,
        }
