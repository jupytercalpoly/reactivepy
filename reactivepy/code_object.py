from symtable import symtable, Symbol
import symtable as symt
import builtins as builtins_mod
from typing import List, FrozenSet
from io import StringIO
from hashlib import blake2b


class CodeObject:

    @staticmethod
    def describe_symbol(sym):
        output = StringIO()
        assert isinstance(sym, symt.Symbol)
        print("Symbol:", sym.get_name(), file=output)

        for prop in [
                'referenced', 'imported', 'parameter',
                'global', 'declared_global', 'local',
                'free', 'assigned', 'namespace']:
            if getattr(sym, 'is_' + prop)():
                print('    is', prop, file=output)

        return output.getvalue()

    @staticmethod
    def describe_symtable(st, recursive=True, indent=0, output=StringIO()):
        def print_d(s, *args, **kwargs):
            prefix = ' ' * indent
            print(prefix + s, *args, **kwargs)

        assert isinstance(st, symt.SymbolTable)
        print_d('Symtable: type=%s, id=%s, name=%s' % (
            st.get_type(), st.get_id(), st.get_name()), file=output)
        print_d('  nested:', st.is_nested(), file=output)
        print_d('  has children:', st.has_children(), file=output)
        print_d('  identifiers:', list(st.get_identifiers()), file=output)

        if recursive:
            for child_st in st.get_children():
                CodeObject.describe_symtable(
                    child_st, recursive, indent + 5, output=output)

        return output.getvalue()

    def __init__(self, code: str, key: bytes):
        self.symbol_table: symtable = symtable(code, '<string>', 'exec')
        self.code: str = code
        self.input_vars: List[SymbolWrapper] = self._find_input_variables()
        self.output_vars: FrozenSet[SymbolWrapper] = self._find_output_variables(
        )

        h = blake2b(digest_size=10, key=key)
        if len(self.output_vars) > 0:
            display_id_prefix = "+".join(map(str, self.output_vars))
            h.update(display_id_prefix.encode('utf-8'))
            self.display_id = f"{display_id_prefix}-{h.hexdigest()}"
        else:
            h.update(self.code.encode('utf-8'))
            self.display_id = h.hexdigest()

    def _find_input_variables(self):
        imports = set()
        return list(self._find_symbol_tables(self.symbol_table, imports))

    def _find_symbol_tables(self, symbols, imports):
        for sym in symbols.get_symbols():
            if sym.is_imported():
                imports.add(sym.get_name())

            if sym.is_global() and not hasattr(builtins_mod,
                                               sym.get_name()) and not sym.get_name() in imports:
                yield SymbolWrapper(sym)

        for a in symbols.get_children():
            yield from self._find_symbol_tables(a, imports)

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
