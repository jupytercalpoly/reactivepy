from ipykernel.kernelbase import Kernel
import sys
from .codeObject import CodeObject
from .execute import ExecutionContext
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

    # Creating a kernel of class ExecuteKernel

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.innerKernel = ExecutionContext(log_func=self._log)

    def do_execute(self, code, silent, store_history=True, user_expressions=None,
                   allow_stdin=False):

        self.silent = silent

        if not silent:
            try:
                exec_ctx = self.innerKernel.exec_code(code)
                output = next(exec_ctx)
                self._log(f"Stdout: \"{str(output.stdout)}\"")
                self._log(f"Stderr: \"{str(output.stderr)}\"")
                self._log(f"Outputs: \"{str(output.outputs)}\"")

                try:
                    next(exec_ctx)
                except StopIteration:
                    pass
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
            'name': 'stderr', 'text': value + "\n"})
