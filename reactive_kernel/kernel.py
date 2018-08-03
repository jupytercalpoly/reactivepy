from ipykernel.kernelbase import Kernel
import sys
from .codeObject import CodeObject
from .execute import ExecutionContext
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

    #Creating a kernel of class ExecuteKernel
    innerKernel = ExecutionContext()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def do_execute(self, code, silent, store_history=True, user_expressions=None,
                   allow_stdin=False):

        self.silent = silent

        if not silent:
            try: 
                #obj = CodeObject(code)
                self.innerKernel.exec_code(code)
            except Exception as e:
                error_content = {'ename': str(e.__class__), 'evalue': e.__doc__, 'traceback': []}
                self.send_response(self.iopub_socket, 'error', error_content)
                error_content['status'] = 'error'
                return error_content
            stream_content = {'name': 'stdout', 'text': str(self.innerKernel.namespace)}
            self.send_response(self.iopub_socket, 'stream', stream_content)

        return {'status': 'ok',
                # The base class increments the execution count
                'execution_count': self.execution_count,
                'payload': {},
                'user_expressions': [],
            }