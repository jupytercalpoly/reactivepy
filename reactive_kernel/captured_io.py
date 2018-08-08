import io
import sys


class CapturedIO(object):
    def __init__(self, stdout, stderr):
        self._stdout = stdout
        self._stderr = stderr

    @property
    def stdout(self):
        if not self._stdout:
            return ''
        return self._stdout.getvalue()

    @property
    def stderr(self):
        if not self._stderr:
            return ''
        return self._stderr.getvalue()


class CapturedIOCtx(object):
    def __init__(self, capture_stdout=True, capture_stderr=True):
        self.capture_stdout = capture_stdout
        self.capture_stderr = capture_stderr

    def __enter__(self):
        self.sys_stdout = sys.stdout
        self.sys_stderr = sys.stderr

        stdout = stderr = None
        if self.capture_stdout:
            stdout = sys.stdout = io.StringIO()
        if self.capture_stderr:
            stderr = sys.stderr = io.StringIO()

        return CapturedIO(stdout, stderr)

    def __exit__(self, exc_type, exc_value, traceback):
        sys.stdout = self.sys_stdout
        sys.stderr = self.sys_stderr
