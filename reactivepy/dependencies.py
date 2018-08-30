from collections import defaultdict
from .code_object import CodeObject, SymbolWrapper
from .transactional import TransactionDict, TransactionSet
import sys
from typing import TypeVar, Set, Generic, FrozenSet, List


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


NodeT = TypeVar('NodeType')


class DependencyTracker(Generic[NodeT]):
    """Track dependencies between code objects and maintain a topological ordering of nodes

    Uses an incremental topological ordering algorithm to detect cycles and maintain order.

    Paper:
    http://www.doc.ic.ac.uk/~phjk/Publications/DynamicTopoSortAlg-JEA-07.pdf
    """

    def __init__(self):
        # exported variable(s) -> integer value denoting topological ordering
        self._ordering = TransactionDict[NodeT, int]()
        # exported variable(s)
        self._nodes = TransactionSet[NodeT]()
        # exported variable(s) -> set of descendent variable(s)
        self._edges = TransactionDict[NodeT,
                                      Set[NodeT]]()
        self._backward_edges = TransactionDict[NodeT, Set[NodeT]](
        )

    def get_nodes(self) -> Set[NodeT]:
        return set(self._nodes)

    def get_neighbors(self, node: NodeT) -> Set[NodeT]:
        return self._edges[node]

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

    def add_node(self, defined_vars: NodeT):
        """"Add a new code object to the dependency graph

        Initially this object has no dependencies
        """
        if defined_vars in self._nodes:
            raise DuplicateCodeObjectAddedException()

        self._nodes.add(defined_vars)
        self._edges[defined_vars] = set()  # No edges initially
        self._backward_edges[defined_vars] = set()

        max_order_value = max(self._ordering.values(), default=0)
        self._ordering[defined_vars] = max_order_value + 1

    def add_edge(self, from_output_vars: NodeT,
                 to_output_vars: NodeT) -> bool:
        """Add new edge to dependency graph

        Return boolean, False if edge already existed, True if edge was successfully added
        """

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

    def delete_node(self, defined_vars: NodeT):
        if defined_vars not in self._nodes:
            raise CodeObjectNotFoundException()

        for child in self._edges[defined_vars]:
            self.delete_edge(defined_vars, child)

        for parent in self._edges[defined_vars]:
            self.delete_edge(parent, defined_vars)

    def delete_edge(self, from_output_vars: NodeT,
                    to_output_vars: NodeT):
        if from_output_vars not in self._nodes or to_output_vars not in self._nodes:
            raise CodeObjectNotFoundException()

        if to_output_vars not in self._edges[from_output_vars]:
            raise EdgeNotFoundException()

        self._edges[from_output_vars].remove(to_output_vars)
        self._backward_edges[to_output_vars].remove(from_output_vars)

    def get_descendants(
            self, defined_vars: NodeT) -> List[NodeT]:
        """Get all code objects that transitively depend on the given object"""

        if defined_vars not in self._nodes:
            raise CodeObjectNotFoundException()

        visited = set()
        unique_descendants = set(
            self._get_descendants(defined_vars, visited)) - {defined_vars}

        return sorted(unique_descendants,
                      key=lambda node: self._ordering[node])

    def _get_descendants(self, output_vars, visited):
        if output_vars not in visited:
            yield output_vars

            visited.add(output_vars)

            for descendent in self._edges[output_vars]:
                yield from self._get_descendants(descendent, visited)

    def __contains__(self, defined_vars: NodeT) -> bool:
        """Test whether code object is already present in dependency tracker"""
        return defined_vars in self._nodes

    def order_nodes(self, reverse=False) -> List[NodeT]:
        return sorted(self._nodes,
                      key=lambda node: self._ordering[node.output_vars], reverse=reverse)
