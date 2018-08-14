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
import linecache
import time
from tornado.ioloop import IOLoop
from importlib.abc import InspectLoader

_assign_nodes = (ast.AugAssign, ast.AnnAssign, ast.Assign)
_single_targets_nodes = (ast.AugAssign, ast.AnnAssign)


class LineCachingFailedException(Exception):
    """Caching the provided code in the global line cache failed"""
    pass


class ExecutionContext:
    def __init__(self, loader: InspectLoader, loop=None):
        self.user_ns = {}
        self.global_ns = {}
        if loop is None:
            loop = IOLoop.current()
        self.loop = loop
        self.loader = loader
        self.excepthook = sys.excepthook
        self.InteractiveTB = ultratb.AutoFormattedTB(mode='Plain',
                                                     color_scheme='LightBG',
                                                     tb_offset=1,
                                                     debugger_cls=None)
        self.SyntaxTB = ultratb.SyntaxTB(color_scheme='NoColor')

    def run_cell(self, code, name):
        result = linecache.lazycache(
            name, {
                '__name__': name, '__loader__': self.loader})
        if not result:
            raise LineCachingFailedException()

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

            for node in to_run_interactive:
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
                exec(code_obj, self.global_ns, self.user_ns)
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
                    # If the error occurred when executing compiled code, we
                    # should provide full stacktrace
                    elist = traceback.extract_tb(tb)
                    stb = self.SyntaxTB.structured_traceback(
                        etype, value, elist)
                    print(self.InteractiveTB.stb2text(stb), file=sys.stderr)
                else:
                    # Actually show the traceback
                    print(self.InteractiveTB.stb2text(stb), file=sys.stderr)

            except BaseException as e:
                print(e)
        else:
            outflag = False

        return outflag
