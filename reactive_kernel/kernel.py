
from ipykernel.kernelbase import Kernel

import re

__version__ = '0.1.0'


class ReactivePythonKernel(Kernel):
    implementation = 'reactive_kernel  '
    implementation_version = __version__
    language_info = {
        'name': 'reactive_kernel',
        'mimetype': 'text/x-python',
        'file_extension': '.py',
    }

    def __init__(self):
        pass

    def do_execute(self, code, silent, store_history=True, user_expressions=None,
                   allow_stdin=False):
        print("Executing code")
        print(code)
        if not silent:
            stream_content = {'name': 'stdout', 'text': code}
            self.send_response(self.iopub_socket, 'stream', stream_content)

        return {'status': 'ok',
                # The base class increments the execution count
                'execution_count': self.execution_count,
                'payload': [],
                'user_expressions': {},
                }
