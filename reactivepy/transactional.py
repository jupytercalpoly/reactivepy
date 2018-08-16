from collections import UserDict
import copy
from abc import ABC, abstractmethod
from typing import TypeVar, Dict, MutableSet


class TransactionalABC(ABC):
    @abstractmethod
    def start_transaction(self):
        pass

    @abstractmethod
    def commit(self):
        pass

    @abstractmethod
    def rollback(self):
        pass


class CommitNeverStartedException(Exception):
    """Commit was never started"""
    pass


KT = TypeVar('KT')
VT = TypeVar('VT')


class TransactionDict(TransactionalABC, UserDict, Dict[KT, VT]):
    _tombstone = object()

    def __init__(self, *args, **kwargs):
        super(TransactionDict, self).__init__(*args, **kwargs)

        self._dirty_values: Dict[KT, VT] = dict()
        self._started_commit: bool = False

    def __getitem__(self, key: KT) -> VT:
        if key in self._dirty_values:
            data = self._dirty_values[key]
            if data != TransactionDict._tombstone:
                return data

        if key in self.data:
            if self._started_commit:
                self._dirty_values[key] = copy.copy(self.data[key])
                return self._dirty_values[key]
            else:
                return self.data[key]

        raise KeyError(key)

    def values(self):
        return self.data.values()

    def __setitem__(self, key: KT, item: VT):
        if self._started_commit:
            self._dirty_values[key] = item
        else:
            self.data[key] = item

    def __contains__(self, key: KT):
        return key in self._dirty_values or key in self.data

    def __delitem__(self, key: KT):
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


class TransactionSet(TransactionalABC, MutableSet[VT]):
    def __init__(self, *args, **kwargs):
        super(TransactionSet, self).__init__(*args, **kwargs)

        self._inner_set: MutableSet[VT] = set()

    def __contains__(self, value: VT):
        return value in self._inner_set

    def __iter__(self):
        return iter(self._inner_set)

    def __len__(self):
        return len(self._inner_set)

    def add(self, item: VT):
        self._inner_set.add(item)

    def discard(self, item: VT):
        self._inner_set.discard(item)

    def start_transaction(self):
        self._initial_set = copy.copy(self._inner_set)

    def commit(self):
        self._initial_set = None

    def rollback(self):
        self._inner_set = self._initial_set
        self._initial_set = None
