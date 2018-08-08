import io
import sys
import builtins


class CapturedDisplayHook(object):
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


class CapturedDisplayCtx(object):
    def __enter__(self):
        self.sys_displayhook = sys.displayhook

        displayhook = sys.displayhook = CapturedDisplayHook()

        return displayhook

    def __exit__(self, exc_type, exc_value, traceback):
        sys.displayhook = self.sys_displayhook
