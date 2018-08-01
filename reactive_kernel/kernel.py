
from ipykernel.kernelbase import Kernel
import sys
from symtable import symtable

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

    def do_execute(self, code, silent, store_history=True, user_expressions=None,
                   allow_stdin=False):
        
        symbols = symtable(code, '<string>', 'exec')

        if not silent:
            try: 
                obj = Code_Object(code)
            except Exception as e:
                return {
                    'status' : 'error',
                    'ename' : e.expr,
                    'evalue' : e.expr,
                    'traceback' : sys.exc_info()
                }
            #stream_content = {'name': 'stdout', 'text': obj.input_vars}
            #self.send_response(self.iopub_socket, 'stream', stream_content)

        return {'status': 'ok',
                # The base class increments the execution count
                'execution_count': self.execution_count,
                'payload': [],
                'user_expressions': {},
                }


class Code_Object:
    def __init__(self, code):
        self.input_vars = self.input_variables(code)
        self.output_vars = self.output_variables(code)
        self.code = code


    def input_variables(self, code):
        input_vars = []
        symbols = symtable(code, '<string>', 'exec')
        for i in symbols.get_symbols() :
            if(i.is_global()) :
                input_vars.append(i)
        return str(input_vars)

    def output_variables(self, code):
        #return one top level defined variable, only including support for one as of now 
        output_vars = []
        symbols = symtable(code, '<string>', 'exec')
        for i in symbols.get_symbols() :
            if(i.is_assigned()) :
                output_vars.append(i)
        if len(output_vars) == 0:
            return
        if len(output_vars) == 1:
            return str(output_vars[0])
        raise DuplicateCellAddedError()

    def code(self, code):
        return code

class DuplicateCellAddedError(Exception):
    """Dependency graph already contains this code object

    Code object identity is determined by a tuple of its exported variables
    """
    def __init__(self):
        self.expr = "Attempted to define more than one local variable"