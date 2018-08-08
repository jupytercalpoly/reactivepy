import io
import sys
import builtins as builtins_mod


class CapturedDisplayHook(object):
    def __init__(self):
        self.values = []

    def __call__(self, value=None):
        if value is None:
            return
        self.values.append(value)
        builtins_mod._ = value


class CapturedDisplayCtx(object):
    def __enter__(self):
        self.sys_displayhook = sys.displayhook

        displayhook = sys.displayhook = CapturedDisplayHook()

        return displayhook

    def __exit__(self, exc_type, exc_value, traceback):
        sys.displayhook = self.sys_displayhook
