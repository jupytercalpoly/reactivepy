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

    #Creating a kernel of class Execute Kernel
    innerKernel = ExecuteKernel()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def do_execute(self, code, silent, store_history=True, user_expressions=None,
                   allow_stdin=False):

        self.silent = silent

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
        
        some_dict = self.innerKernel.do_execute(code, silent)

        #return some_dict

        return {'status': some_dict[u'status'],
                # The base class increments the execution count
                'execution_count': some_dict[u'execution_count'],
                'payload': some_dict[u'payload'],
                'user_expressions': some_dict[u'user expressions'],
                }