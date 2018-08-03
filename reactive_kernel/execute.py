from ipykernel.kernelbase import Kernel
import sys
import getpass

class ExecutionContext:

    def __init__(self, **kwargs):
        self.namespace = {}
        sys.displayhook = self.createDisplayHook()
        ##sys.stdout = self.stdout # do more stuff
        ##sys.stderr = self.stderr # here too

    def exec_code(self, code):
        exec(code, globals(), self.namespace)
        #self.namespace = sys.displayhook

    def createDisplayHook(self): 
        def displayhook(value):
            pass
        return displayhook