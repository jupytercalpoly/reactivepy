from symtable import symtable


class CodeObject:
    def __init__(self, code):
        self.symbol_table = symtable(code, '<string>', 'exec')
        self.code = code
        self.input_vars = self._find_input_variables()
        self.output_vars = self._find_output_variables()

    def _find_input_variables(self):
        return frozenset(self._find_symbol_tables(self.symbol_table))

    def _find_symbol_tables(self, symbols):
        for sym in symbols.get_symbols():
            if sym.is_global():
                yield sym

        for a in symbols.get_children():
            yield from self._find_symbol_tables(a)

    def _find_output_variables(self):
        # return one top level defined variable, only including support for one
        # as of now
        output_vars = [sym for sym in self.symbol_table.get_symbols()
                       if sym.is_assigned()]

        if len(output_vars) > 1:
            raise MultipleDefinitionsError()
        else:
            return output_vars

    def __hash__(self):
        return hash(self.input_vars)

    def __eq__(self, other):
        return self.input_vars == other.input_vars


class MultipleDefinitionsError(Exception):
    """ Attempted to define more than one local variable
    """
    pass
