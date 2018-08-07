from ipykernel.kernelbase import Kernel
import sys
from .codeObject import CodeObject
from .execute import ExecutionContext
from .capturedObject import CaptureObject
import traceback as tb
from .capturedDisplay import CaptureDisplay
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

    # Creating a kernel of class ExecuteKernel

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.innerKernel = ExecutionContext(log_func=self._log)

    def do_execute(self, code, silent, store_history=True, user_expressions=None,
                   allow_stdin=False):

        self.silent = silent

        if not silent:
            try:
                with CaptureObject(log_func=self._log) as s, CaptureDisplay(log_func=self.log) as a:
                    self.innerKernel._run_cell(code)
                    self._log(s.stdout)

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
                # The base class increments the execution count
                'execution_count': self.execution_count,
                'payload': {},
                'user_expressions': [],
                }

    def _log(self, value):
        self.send_response(self.iopub_socket, 'stream', {
            'name': 'stdout', 'text': value + "\n"})
