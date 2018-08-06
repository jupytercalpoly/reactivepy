import io
import sys


class CapturedIO(object):
    def __init__(self, log_func, stdout, stderr, outputs):
        self._stdout = stdout
        self._stderr = stderr
        self._outputs = outputs
        self.log = log_func

    @property
    def stdout(self):
        if not self._stdout:
            return ''
        return self._stdout.getvalue()

    def __str__(self):
        return self.stdout

    @property
    def stderr(self):
        if not self._stderr:
            return ''
        return self._stderr.getvalue()

    @property
    def outputs(self):
        return [repr(kargs) for kargs in self._outputs]


class CapturingDisplayHook(object):
    def __init__(self, outputs=None, log_func=None):
        if outputs is None:
            outputs = []
        self.outputs = outputs
        self.log = log_func

    def __call__(self, result=None):
        self.log('Capture displayhook called')
        self.log(repr(self))
        if result is None:
            self.log("Called with None result")
        else:
            self.log(repr(result))
            self.outputs.append({'data': repr(result), 'metadata': {}})


class CaptureObject(object):
    def __init__(self, log_func=None, stdout=True, stderr=True):
        self.stdout = stdout
        self.stderr = stderr
        self.log = log_func

    def __enter__(self):
        self.log('Entering capture context')
        self.sys_stdout = sys.stdout
        self.sys_stderr = sys.stderr

        stdout = stderr = None
        outputs = []
        if self.stdout:
            stdout = sys.stdout = io.StringIO()
        if self.stderr:
            stderr = sys.stderr = io.StringIO()

        return CapturedIO(self.log, stdout, stderr, outputs)

    def __exit__(self, exc_type, exc_value, traceback):
        sys.stdout = self.sys_stdout
        sys.stderr = self.sys_stderr
        # sys.displayhook = self.save_display_hook
        self.log('Exiting capture context')
