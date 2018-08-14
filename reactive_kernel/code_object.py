from symtable import symtable, Symbol
import builtins as builtins_mod
from typing import List, FrozenSet
import random
import string


def generate_id(size=24, chars=(string.ascii_letters + string.digits)):
    return ''.join(random.choice(chars) for _ in range(size))


class CodeObject:
    def __init__(self, code: str):
        self.symbol_table: symtable = symtable(code, '<string>', 'exec')
        self.code: str = code
        self.input_vars: List[SymbolWrapper] = self._find_input_variables()
        self.output_vars: FrozenSet[SymbolWrapper] = self._find_output_variables(
        )
        if len(self.output_vars) > 0:
            self.display_id = "+".join(map(str, self.output_vars))
        else:
            self.display_id = generate_id()

    def _find_input_variables(self):
        return list(self._find_symbol_tables(self.symbol_table))

    def _find_symbol_tables(self, symbols):
        for sym in symbols.get_symbols():
            if sym.is_global() and not hasattr(builtins_mod, sym.get_name()):
                yield SymbolWrapper(sym)

        for a in symbols.get_children():
            yield from self._find_symbol_tables(a)

    def _find_output_variables(self):
        # return one top level defined variable, only including support for one
        # as of now
        output_vars = [SymbolWrapper(sym) for sym in self.symbol_table.get_symbols()
                       if sym.is_assigned() or sym.is_imported()]

        num_imports = sum(map(lambda sym: int(sym.is_imported()), output_vars))

        if (len(output_vars) - num_imports) > 1:
            raise MultipleDefinitionsError()
        else:
            return frozenset(output_vars)

    def __hash__(self):
        return hash(self.display_id)

    def __eq__(self, other):
        if isinstance(other, CodeObject):
            return self.display_id == other.display_id
        return False

    def __repr__(self):
        return f"<Code in:{str(self.input_vars)} out:{str(list(self.output_vars))} code:\"{self.code}\">"


class SymbolWrapper:
    """Wrapper for symtable Symbols that performs hashing and equality check by name"""

    def __init__(self, symbol: Symbol):
        self._symbol: Symbol = symbol

    def __getattr__(self, attr):
        return self._symbol.__getattribute__(attr)

    def __eq__(self, other):
        if isinstance(other, SymbolWrapper):
            return self._symbol.get_name() == other.get_name()
        return False

    def __hash__(self):
        return hash(self._symbol.get_name())

    def __repr__(self):
        return f'[{self._symbol.get_name()}]'


class MultipleDefinitionsError(Exception):
    """ Attempted to define more than one local variable
    """
    pass
