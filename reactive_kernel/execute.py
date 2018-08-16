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
import inspect

_assign_nodes = (ast.AugAssign, ast.AnnAssign, ast.Assign)
_single_targets_nodes = (ast.AugAssign, ast.AnnAssign)


class LineCachingFailedException(Exception):
    """Caching the provided code in the global line cache failed"""
    pass


class IncompleteExecutionResultException(Exception):
    """The result was not completely filled with the appropriate data"""
    pass


class ExecutionResult:
    def __init__(self):
        self.stdout = None
        self.stderr = None
        self.has_output = False
        self.output = None
        self.target_id = None
        self.has_exception = False
        self.exception = None

    def is_complete(self):
        stdout_fulfilled = self.stdout is not None
        stderr_fulfilled = self.stderr is not None
        output_fulfilled = (
            self.output is not None and self.target_id is not None) if self.has_output else True
        exception_fulfilled = (self.exception is not None and len(
            self.exception) == 3) if self.has_exception else True
        return stdout_fulfilled and stderr_fulfilled and output_fulfilled and exception_fulfilled

    def capture_io(self, stdout, stderr):
        self.stdout = stdout
        self.stderr = stderr

    def displayhook(self, result=None):
        self.output = result
        if self.output is not None:
            self.has_output = True


class CapturedIOCtx(object):
    def __init__(self, container_func, capture_stdout=True,
                 capture_stderr=True):
        self.capture_stdout = capture_stdout
        self.capture_stderr = capture_stderr
        self.container_func = container_func

    def __enter__(self):
        self.sys_stdout = sys.stdout
        self.sys_stderr = sys.stderr

        stdout = stderr = None
        if self.capture_stdout:
            stdout = sys.stdout = io.StringIO()
        if self.capture_stderr:
            stderr = sys.stderr = io.StringIO()

        return self.container_func(stdout, stderr)

    def __exit__(self, exc_type, exc_value, traceback):
        sys.stdout = self.sys_stdout
        sys.stderr = self.sys_stderr


class CapturedDisplayCtx(object):
    def __init__(self, capture_func):
        self.capture_func = capture_func

    def __enter__(self):
        self.sys_displayhook = sys.displayhook

        displayhook = sys.displayhook = self.capture_func

        return displayhook

    def __exit__(self, exc_type, exc_value, traceback):
        sys.displayhook = self.sys_displayhook


class ExecutionContext:
    def __init__(self, loader: InspectLoader, loop=None):
        self.user_ns = {}
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

    async def run_cell(self, code, name):
        cache_result = linecache.lazycache(
            name, {
                '__name__': name, '__loader__': self.loader})
        if not cache_result:
            raise LineCachingFailedException()

        exec_result = ExecutionResult()

        with CapturedIOCtx(exec_result.capture_io), CapturedDisplayCtx(exec_result.displayhook):
            code_ast = ast.parse(code, filename=name, mode='exec')
            run_failed, output_name = self._run_ast_nodes(code_ast.body, name)

            exec_result.has_exception = run_failed
            exec_result.target_id = output_name

        if exec_result.output is not None and inspect.isawaitable(
                exec_result.output):
            exec_result.output = await exec_result.output
            self.user_ns[exec_result.target_id] = exec_result.output

        return exec_result

    def _run_ast_nodes(self, nodelist, name):
        output_name = None
        if not nodelist:
            return True, output_name

        if isinstance(nodelist[-1], _assign_nodes):
            asg = nodelist[-1]
            if isinstance(asg, ast.Assign) and len(asg.targets) == 1:
                target = asg.targets[0]
            elif isinstance(asg, _single_targets_nodes):
                target = asg.target
            else:
                target = None
            if isinstance(target, ast.Name):
                output_name = target.id
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
                return True, output_name

            for node in to_run_interactive:
                mod = ast.Interactive([node])
                code = compile(mod, name, 'single')
                if self._run_code(code):
                    return True, output_name
        except BaseException:
            return True, output_name

        return False, output_name

    def _run_code(self, code_obj):
        old_excepthook, sys.excepthook = sys.excepthook, self.excepthook
        outflag = True  # happens in more places, so it's easier as default
        try:
            try:
                exec(code_obj, self.user_ns, self.user_ns)
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
