from ipykernel.kernelbase import Kernel
import sys
from .codeObject import CodeObject
from .execute import ExecuteKernel
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

    innerKernel = ExecuteKernel()


    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def do_execute(self, code, silent, store_history=True, user_expressions=None,
                   allow_stdin=False):
        if not silent:
            try: 
                obj = CodeObject(code)
            except Exception as e:
                error_content = {'ename': str(e.__class__), 'evalue': e.__doc__, 'traceback': []}
                self.send_response(self.iopub_socket, 'error', error_content)
                error_content['status'] = 'error'
                return error_content
            stream_content = {'name': 'stdout', 'text': str(obj.input_vars)}
            self.send_response(self.iopub_socket, 'stream', stream_content)

        self.innerKernel.do_execute(code, silent=silent)

        return {'status': 'ok',
                # The base class increments the execution count
                'execution_count': self.execution_count,
                'payload': [],
                'user_expressions': {},
                }