import builtins as builtins_mod


class BuiltInManager:
    def __init__(self):
        self._builtins = {}

        self._builtins['__builtins__'] = builtins_mod.__dict__

        self._current_global_ns = None
        self._current_local_ns = None

    def add_builtin(self, name, obj):
        self._builtins[name] = obj

    def update(self, *args, **kwargs):
        if self._current_local_ns is None:
            self._init_nss()

        self._current_local_ns.update(*args, **kwargs)

    @property
    def global_ns(self):
        if self._current_global_ns is None:
            self._init_nss()

        return self._current_global_ns

    @property
    def local_ns(self):
        if self._current_local_ns is None:
            self._init_nss()

        return self._current_local_ns

    def _init_nss(self):
        self._current_global_ns = {}
        self._current_global_ns.update(self._builtins)

        self._current_local_ns = {}
        # self._current_local_ns.update(self._builtins)

    def reset(self):
        self._init_nss()

    def __contains__(self, obj):
        return obj in self._builtins or obj in self._builtins['__builtins__']

