from symtable import symtable, Symbol


class CodeObject:
    def __init__(self, code):
        self.symbol_table = symtable(code, '<string>', 'exec')
        self.code = code
        self.input_vars = self._find_input_variables()
        self.output_vars = self._find_output_variables()

    def _find_input_variables(self):
        return list(self._find_symbol_tables(self.symbol_table))

    def _find_symbol_tables(self, symbols):
        for sym in symbols.get_symbols():
            if sym.is_global():
                yield SymbolWrapper(sym)

        for a in symbols.get_children():
            yield from self._find_symbol_tables(a)

    def _find_output_variables(self):
        # return one top level defined variable, only including support for one
        # as of now
        output_vars = [SymbolWrapper(sym) for sym in self.symbol_table.get_symbols()
                       if sym.is_assigned()]

        if len(output_vars) > 1:
            raise MultipleDefinitionsError()
        else:
            return frozenset(output_vars)

    def __hash__(self):
        return hash(self.input_vars)

    def __eq__(self, other):
        if isinstance(other, CodeObject):
            return self.input_vars == other.input_vars
        return False

    def __repr__(self):
        return f"<Code in:{str(self.input_vars)} out:{str(list(self.output_vars))} code:\"{self.code}\">"


class SymbolWrapper:
    """Wrapper for symtable Symbols that performs hashing and equality check by name"""

    def __init__(self, symbol):
        self._symbol = symbol

    def __getattr__(self, attr):
        return self._symbol.__getattribute__(attr)

    def __eq__(self, other):
        if isinstance(other, SymbolWrapper):
            return self._symbol.get_name() == other.get_name()
        return False

    def __hash__(self):
        return hash(self._symbol.get_name())

    def __repr__(self):
        return f'<{self._symbol.get_name()}>'


class MultipleDefinitionsError(Exception):
    """ Attempted to define more than one local variable
    """
    pass
