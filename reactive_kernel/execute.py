import sys
import getpass
import io
from ast import parse, AugAssign, AnnAssign, Assign
from ast import AST
import ast
from typing import List as ListType

_assign_nodes = (ast.AugAssign, ast.AnnAssign, ast.Assign)
_single_targets_nodes = (ast.AugAssign, ast.AnnAssign)


class ExecutionContext:
    def __init__(self, log_func=None):
        self.namespace = {}
        self.log = log_func
        self.excepthook = sys.excepthook

    def _run_cell(self, code):
        code_ast = ast.parse(code)
        result = self.run_ast_nodes(code_ast.body)

        return result

    def run_ast_nodes(self, nodelist):
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
            code = compile(mod, "<ast-parse>", "exec")
            if self.run_code(code):
                return True

            for i, node in enumerate(to_run_interactive):
                mod = ast.Interactive([node])
                code = compile(mod, "<ast-parse>", "single")
                if self.run_code(code):
                    return True
        except BaseException:
            return True

        return False

    def run_code(self, code_obj):
        old_excepthook, sys.excepthook = sys.excepthook, self.excepthook
        outflag = True  # happens in more places, so it's easier as default
        try:
            try:
                exec(code_obj, globals(), self.namespace)
            finally:
                # Reset our crash handler in place
                sys.excepthook = old_excepthook
        except BaseException:
            pass
        else:
            outflag = False

        return outflag
