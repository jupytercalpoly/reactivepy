import io
import sys
import builtins


class CapturedDisplayHook(object):
    def __init__(self, displayhook, outputs, log_func=None):
        self._outputs = outputs
        self.log = log_func

    def __call__(self, value=None):
        if value is None:
            return
        # Set '_' to None to avoid recursion
        builtins._ = None
        text = repr(value)
        try:
            sys.stdout.write(text)
        except UnicodeEncodeError:
            bytes = text.encode(sys.stdout.encoding, 'backslashreplace')
            if hasattr(sys.stdout, 'buffer'):
                sys.stdout.buffer.write(bytes)
            else:
                text = bytes.decode(sys.stdout.encoding, 'strict')
                sys.stdout.write(text)
        sys.stdout.write("\n")
        builtins._ = value

    @property
    def outputs(self):
        return [repr(kargs) for kargs in self._outputs]


class CaptureDisplay(object):
    def __init__(self, log_func=None, displayhook=True):
        self.displayhook = displayhook
        self.log = log_func

    def __enter__(self):
        # self.log('Entering capture context')
        self.displayhook = sys.displayhook

        displayhook = None
        outputs = []
        if self.displayhook:
            displayhook = sys.displayhook = CapturedDisplayHook(
                displayhook, outputs, self.log)

        return displayhook

    def __exit__(self, exc_type, exc_value, traceback):
        sys.displayhook = self.displayhook
        #self.log('Exiting capture context')
