from symtable import symtable

class CodeObject:
    def __init__(self, code):
        self.input_vars = self._find_input_variables(code)
        self.output_vars = self._find_output_variables(code)
        self.code = code

    def _find_input_variables(self, code):
        input_vars = []
        symbols = symtable(code, '<string>', 'exec')
        input_vars = self._find_symbol_tables(symbols, input_vars)
        return input_vars

    
    def _find_symbol_tables(self, symbols, input_vars):
        for i in symbols.get_symbols():
            if i.is_global() :
                input_vars.append(i)
        for a in symbols.get_children() :
            self._find_symbol_tables(a, input_vars)
        else :
            return input_vars
            

    def _find_output_variables(self, code):
        #return one top level defined variable, only including support for one as of now 
        output_vars = []
        symbols = symtable(code, '<string>', 'exec')
        for i in symbols.get_symbols() :
            if i.is_assigned() :
                output_vars.append(i)
        if len(output_vars) == 0:
            return
        if len(output_vars) == 1:
            return output_vars[0]
        raise MultipleDefinitionsError()

class MultipleDefinitionsError(Exception):
    """ Attempted to define more than one local variable
    """
    pass