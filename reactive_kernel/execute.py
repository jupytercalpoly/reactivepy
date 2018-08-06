import sys
import getpass
import io
from .capturedObject import CaptureObject, CapturingDisplayHook


class ExecutionContext:
    def __init__(self, log_func=None):
        self.namespace = {}
        self.log = log_func

    def exec_code(self, code):
        # possible try except
        with CaptureObject(log_func=self.log) as s:
            self.log(str(sys.displayhook))
            self.log('Before code exec')
            exec(code, globals(), self.namespace)
            self.log('After code exec')
            yield s
