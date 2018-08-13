import sys
import getpass
import io
from ast import parse, AugAssign, AnnAssign, Assign
from ast import AST
import ast
from typing import List as ListType
import traceback
from IPython.core.ultratb import ListTB
import IPython.core.ultratb as ultratb
# from IPython.core.compilerop import CachingCompiler, check_linecache_ipython
import linecache
import time


_assign_nodes = (ast.AugAssign, ast.AnnAssign, ast.Assign)
_single_targets_nodes = (ast.AugAssign, ast.AnnAssign)


class ExecutionContext:
    def __init__(self, log_func=None):
        self.namespace = {}
        self.log = log_func
        self.excepthook = sys.excepthook
        self.InteractiveTB = ultratb.AutoFormattedTB(mode='Plain',
                                                     color_scheme='LightBG',
                                                     tb_offset=1,
                                                     check_cache=self.check_internal_cache,
                                                     debugger_cls=None)
        self.SyntaxTB = ultratb.SyntaxTB(color_scheme='NoColor')
        self.cache = {}
        self.saved_getline = linecache.getline
        self.saved_getlines = linecache.getlines

        def wrapped_getline(*args, **kwargs):
            result = self.saved_getline(*args, **kwargs)
            if result is None or len(result) == 0:
                filename, lineno = args
                return self.cache[filename][2][lineno - 1]
            return result

        def wrapped_getlines(*args, **kwargs):
            result = self.saved_getlines(*args, **kwargs)
            if result is None or len(result) == 0:
                return self.cache[args[0]][2]
            return result

        linecache.getline = wrapped_getline
        linecache.getlines = wrapped_getlines

    def run_cell(self, code, name):
        entry = (len(code), time.time(),
                 [line+'\n' for line in code.splitlines()], name)
        linecache.cache[name] = entry
        self.cache[name] = entry
        code_ast = ast.parse(code, filename=name, mode='exec')
        result = self._run_ast_nodes(code_ast.body, name)

        return result

    def _run_ast_nodes(self, nodelist, name):
        if not nodelist:
            return

        if isinstance(nodelist[-1], _assign_nodes):
            asg = nodelist[-1]
            if isinstance(asg, ast.Assign) and len(asg.targets) == 1:
                target = asg.targets[0]
            elif isinstance(asg, _single_targets_nodes):
                target = asg.target
            else:
                target = None
            if isinstance(target, ast.Name):
                nnode = ast.Expr(ast.Name(target.id, ast.Load()))
                ast.fix_missing_locations(nnode)
                nodelist.append(nnode)

        if isinstance(nodelist[-1], ast.Expr):
            to_run_exec, to_run_interactive = nodelist[:-1], nodelist[-1:]
        else:
            to_run_exec, to_run_interactive = nodelist, []

        try:
            mod = ast.Module(to_run_exec)
            code = compile(mod, name, 'exec')
            if self._run_code(code):
                return True

            for i, node in enumerate(to_run_interactive):
                mod = ast.Interactive([node])
                code = compile(mod, name, 'single')
                if self._run_code(code):
                    return True
        except BaseException:
            return True

        return False

    def _run_code(self, code_obj):
        old_excepthook, sys.excepthook = sys.excepthook, self.excepthook
        outflag = True  # happens in more places, so it's easier as default
        try:
            try:
                exec(code_obj, globals(), self.namespace)
            finally:
                # Reset our crash handler in place
                sys.excepthook = old_excepthook
        except BaseException:
            try:
                etype, value, tb = sys.exc_info()
                stb = self.InteractiveTB.structured_traceback(
                    etype, value, tb
                )

                if issubclass(etype, SyntaxError):
                    # If the error occurred when executing compiled code, we should provide full stacktrace
                    elist = traceback.extract_tb(tb)
                    stb = self.SyntaxTB.structured_traceback(
                        etype, value, elist)
                    print(self.InteractiveTB.stb2text(stb), file=sys.stderr)
                else:

                    # Actually show the traceback
                    print(self.InteractiveTB.stb2text(stb), file=sys.stderr)

            # traceback.print_exception(etype, value, tb)
            except BaseException as e:
                print(e)
        else:
            outflag = False

        return outflag

    def check_internal_cache(self, *args):
        linecache.checkcache(*args)
        linecache.cache.update(self.cache)
