from collections import defaultdict
from .code_object import CodeObject
import sys
from collections import UserDict
import copy


class DuplicateCodeObjectAddedException(Exception):
    """Dependency graph already contains this code object

    Code object identity is determined by a tuple of its exported variables
    """
    pass


class DuplicateEdgeAddedException(Exception):
    """Dependency graph already contains given edge"""
    pass


class CodeObjectNotFoundException(Exception):
    """Code object is missing from dependency tracker"""
    pass


class EdgeNotFoundException(Exception):
    """Edge is missing from dependency tracker"""
    pass


class CyclicDependencyIntroducedException(Exception):
    """Added edge introduces a cycle to the dependency graph

    Cycles are currently not supported in the reactive programming model
    """
    pass


class CommitNeverStartedException(Exception):
    """Commit was never started"""
    pass


class TransactionDict(UserDict):
    _tombstone = object()

    def __init__(self, *args, **kwargs):
        super(TransactionDict, self).__init__(*args, **kwargs)

        self._dirty_values = dict()
        self._started_commit = False

    def __getitem__(self, key):
        if key in self._dirty_values:
            return self._dirty_values[key]

        if key in self.data:
            if self._started_commit:
                self._dirty_values[key] = copy.copy(self.data[key])
                return self._dirty_values[key]
            else:
                return self.data[key]

        raise KeyError(key)

    def __setitem__(self, key, item):
        if self._started_commit:
            self._dirty_values[key] = item
        else:
            self.data[key] = item

    def __contains__(self, key):
        return key in self._dirty_values or key in self.data

    def __delitem__(self, key):
        if self._started_commit:
            self._dirty_values[key] = TransactionDict._tombstone
        else:
            del self.data[key]

    def __iter__(self):
        return iter(set(self.data.keys()) | set(self._dirty_values.keys()))

    def __len__(self):
        return len(set(self._dirty_values.keys()) |
                   set(self._dirty_values.keys()))

    def __repr__(self):
        temp_dict = dict()

        temp_dict.update(self.data)
        temp_dict.update(self._dirty_values)

        return repr(temp_dict)

    def start_transaction(self):
        self._started_commit = True

    def commit(self):
        if not self._started_commit:
            raise CommitNeverStartedException()
        for key in self._dirty_values:
            if self._dirty_values[key] == TransactionDict._tombstone:
                del self.data[key]
            else:
                self.data[key] = self._dirty_values[key]

        self._dirty_values.clear()
        self._started_commit = False

    def rollback(self):
        self._dirty_values.clear()
        self._started_commit = False


class DependencyTracker:
    """Track dependencies between code objects and maintain a topological ordering of nodes

    Uses an incremental topological ordering algorithm to detect cycles and maintain order.

    Paper:
    http://www.doc.ic.ac.uk/~phjk/Publications/DynamicTopoSortAlg-JEA-07.pdf
    """

    def __init__(self):
        # exported variable(s) -> integer value denoting topological ordering
        self._ordering = TransactionDict()
        # exported variable(s) -> code object node
        self._nodes = TransactionDict()
        # exported variable(s) -> set of descendent variable(s)
        self._edges = TransactionDict()
        self._backward_edges = TransactionDict()
        # variable -> code object that defines it
        self._symbol_definitions = TransactionDict()

    def start_transaction(self):
        self._ordering.start_transaction()
        self._nodes.start_transaction()
        self._edges.start_transaction()
        self._backward_edges.start_transaction()

    def commit(self):
        self._ordering.commit()
        self._nodes.commit()
        self._edges.commit()
        self._backward_edges.commit()

    def rollback(self):
        self._ordering.rollback()
        self._nodes.rollback()
        self._edges.rollback()
        self._backward_edges.rollback()

    def add_node(self, code):
        """"Add a new code object to the dependency graph

        Initially this object has no dependencies
        """
        output_vars = code.output_vars
        if output_vars in self._nodes:
            raise DuplicateCodeObjectAddedException()

        self._nodes[output_vars] = code
        for sym in code.output_vars:
            self._symbol_definitions[sym] = code
        self._edges[output_vars] = set()  # No edges initially
        self._backward_edges[output_vars] = set()

        max_order_value = max(self._ordering.values(), default=0)
        self._ordering[output_vars] = max_order_value + 1

    def replace_node(self, code):
        """Replace node with the same output variables with a new node"""
        output_vars = code.output_vars
        if output_vars not in self._nodes:
            raise CodeObjectNotFoundException()

        self._nodes[output_vars] = code

    def add_edge(self, from_code, to_code):
        """Add new edge to dependency graph

        Return boolean, False if edge already existed, True if edge was successfully added
        """
        from_output_vars = from_code.output_vars
        to_output_vars = to_code.output_vars

        if from_output_vars not in self._nodes or to_output_vars not in self._nodes:
            raise CodeObjectNotFoundException()

        if to_output_vars in self._edges[from_output_vars]:
            return False

        # Actually add edge to both collections
        self._edges[from_output_vars].add(to_output_vars)
        self._backward_edges[to_output_vars].add(from_output_vars)

        upper_bound = self._ordering[from_output_vars]
        lower_bound = self._ordering[to_output_vars]

        # If the affected area, then update topological ordering
        if lower_bound < upper_bound:
            change_forward = set()
            change_backward = set()
            visited = defaultdict(lambda: False)

            self._dfs_forward(
                to_output_vars, visited, change_forward, upper_bound)
            self._dfs_backward(
                from_output_vars, visited, change_backward, lower_bound)

            self._reorder(change_forward, change_backward)

        return True

    def _dfs_forward(self, node,
                     visited, output, upper_bound):
        visited[node] = True
        output.add(node)

        for child in self._edges[node]:
            order_value = self._ordering[child]
            if order_value == upper_bound:
                raise CyclicDependencyIntroducedException()

            if not visited[child] and order_value < upper_bound:
                self._dfs_forward(child, visited, output, upper_bound)

    def _dfs_backward(self, node, visited, output, lower_bound):
        visited[node] = True
        output.add(node)

        for parent in self._backward_edges[node]:
            order_value = self._ordering[parent]

            if not visited[parent] and lower_bound < order_value:
                self._dfs_backward(parent, visited, output, lower_bound)

    def _reorder(self, change_forward, change_backward):
        change_forward = sorted(list(change_forward),
                                key=lambda code: self._ordering[code])
        change_backward = sorted(list(change_backward),
                                 key=lambda code: self._ordering[code])

        L = list()
        R = list()

        for node in change_backward:
            L.append(node)
            R.append(self._ordering[node])

        for node in change_forward:
            L.append(node)
            R.append(self._ordering[node])

        R = sorted(R)

        for (node, order_value) in zip(L, R):
            self._ordering[node] = order_value

    def delete_edge(self, from_code, to_code):
        from_output_vars = from_code.output_vars
        to_output_vars = to_code.output_vars

        if from_output_vars not in self._nodes or to_output_vars not in self._nodes:
            raise CodeObjectNotFoundException()

        if to_output_vars not in self._edges[from_output_vars]:
            raise EdgeNotFoundException()

        self._edges[from_output_vars].remove(to_output_vars)
        self._backward_edges[to_output_vars].remove(from_output_vars)

    def get_children(self, node):
        """Get directly dependent objects for given object"""
        output_vars = node.output_vars

        if output_vars not in self._nodes:
            raise CodeObjectNotFoundException()

        return list(
            map(lambda child: self._nodes[child], self._edges[output_vars]))

    def get_descendants(self, node):
        """Get all code objects that transitively depend on the given object"""
        output_vars = node.output_vars

        if output_vars not in self._nodes:
            raise CodeObjectNotFoundException()

        unique_descendants = set(self._get_descendants(output_vars))

        return sorted(unique_descendants,
                      key=lambda node: self._ordering[node.output_vars])[1:]

    def _get_descendants(self, output_vars):
        yield self._nodes[output_vars]

        for descendent in self._edges[output_vars]:
            yield from self._get_descendants(descendent)

    def __contains__(self, code):
        """Test whether code object is already present in dependency tracker"""
        return code.output_vars in self._nodes

    def __getitem__(self, code):
        return self._nodes[code.output_vars]

    def order_nodes(self, reverse=False):
        return sorted(self._nodes.values(),
                      key=lambda node: self._ordering[node.output_vars], reverse=reverse)

    def get_code_defining_symbol(self, symbol):
        return self._symbol_definitions[symbol]
