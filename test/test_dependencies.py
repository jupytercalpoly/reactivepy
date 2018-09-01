import asyncio as aio
from reactivepy.dependencies import DependencyLock, DependencyTracker
import pytest


@pytest.fixture
def empty_dep_tracker():
    return DependencyTracker()


@pytest.fixture
def dep_tracker():
    tracker = DependencyTracker()
    for x in range(1, 8):
        tracker.add_node(x)

    return tracker


@pytest.fixture
def dep_tracker_2():
    tracker = DependencyTracker()
    for x in range(1, 8):
        tracker.add_node(x)

    tracker.add_edge(1, 3)
    tracker.add_edge(3, 5)
    tracker.add_edge(5, 7)
    tracker.add_edge(4, 6)
    tracker.add_edge(6, 2)
    tracker.add_edge(2, 1)

    return tracker


@pytest.fixture
def dep_tracker_3():
    tracker = DependencyTracker()
    for x in range(1, 8):
        tracker.add_node(x)

    tracker.add_edge(1, 3)
    tracker.add_edge(2, 3)
    tracker.add_edge(3, 4)
    tracker.add_edge(3, 5)
    tracker.add_edge(3, 6)
    tracker.add_edge(5, 7)
    tracker.add_edge(6, 7)

    return tracker


@pytest.fixture
def dep_lock(dep_tracker_3, event_loop):
    return DependencyLock(dep_tracker_3, loop=event_loop)


class TestDependencyTracker(object):
    def test_add_nodes(self, empty_dep_tracker):
        empty_dep_tracker.add_node(1)
        empty_dep_tracker.add_node(2)
        empty_dep_tracker.add_node(3)
        empty_dep_tracker.add_node(4)

        assert all([x in empty_dep_tracker for x in range(1, 5)])

    def test_delete_nodes(self, dep_tracker):
        dep_tracker.delete_node(1)

        assert all([x in dep_tracker for x in range(2, 8)])

    def test_simple_insert_ordering(self, dep_tracker):
        assert dep_tracker.order_nodes() == list(range(1, 8))

    def test_add_edge_no_reorder(self, dep_tracker):
        dep_tracker.add_edge(1, 7)
        dep_tracker.add_edge(2, 6)
        dep_tracker.add_edge(3, 5)

        assert dep_tracker.order_nodes() == [1, 2, 3, 4, 5, 6, 7]

    def test_add_edge_reorder(self, dep_tracker):
        dep_tracker.add_edge(7, 1)
        dep_tracker.add_edge(6, 2)

        assert dep_tracker.order_nodes() == [7, 6, 3, 4, 5, 2, 1]

    def test_add_edge_reorder_2(self, dep_tracker):
        assert dep_tracker.order_nodes() == [1, 2, 3, 4, 5, 6, 7]

        dep_tracker.add_edge(1, 3)
        dep_tracker.add_edge(3, 5)
        dep_tracker.add_edge(5, 7)

        assert dep_tracker.order_nodes() == [1, 2, 3, 4, 5, 6, 7]

        dep_tracker.add_edge(4, 6)
        dep_tracker.add_edge(6, 2)

        assert dep_tracker.order_nodes() == [1, 4, 3, 6, 5, 2, 7]

        dep_tracker.add_edge(2, 1)

        assert dep_tracker.order_nodes() == [4, 6, 2, 1, 3, 5, 7]

    def test_remove_edge(self, dep_tracker_2):
        dep_tracker_2.delete_edge(2, 1)

        assert dep_tracker_2.order_nodes() == [4, 6, 2, 1, 3, 5, 7]

    def test_get_descendants(self, dep_tracker_2):
        assert dep_tracker_2.get_descendants(4) == [6, 2, 1, 3, 5, 7]
        assert dep_tracker_2.get_descendants(1) == [3, 5, 7]

    def test_get_descendants_3(self, dep_tracker_3):
        assert dep_tracker_3.order_nodes() == [1, 2, 3, 4, 5, 6, 7]

        assert dep_tracker_3.get_descendants(1) == [3, 4, 5, 6, 7]
        assert dep_tracker_3.get_descendants(2) == [3, 4, 5, 6, 7]
        assert dep_tracker_3.get_descendants(3) == [4, 5, 6, 7]
        assert dep_tracker_3.get_descendants(4) == []
        assert dep_tracker_3.get_descendants(5) == [7]
        assert dep_tracker_3.get_descendants(6) == [7]
        assert dep_tracker_3.get_descendants(7) == []


class TestDependencyLock(object):
    def test_create_lock(self, dep_tracker, event_loop):
        lock = DependencyLock(dep_tracker, loop=event_loop)

        assert not lock.locked(1)

    @pytest.mark.asyncio
    async def test_acquire_node(self, dep_lock, event_loop):
        await dep_lock.acquire(3)

        assert dep_lock.locked(3)
        assert dep_lock.would_lock(4)
        assert dep_lock.would_lock(5)
        assert dep_lock.would_lock(6)
        assert dep_lock.would_lock(7)

        dep_lock.release(3)

        assert not dep_lock.locked(3)
        assert not dep_lock.would_lock(4)
        assert not dep_lock.would_lock(5)
        assert not dep_lock.would_lock(6)
        assert not dep_lock.would_lock(7)

    @pytest.mark.asyncio
    async def test_acquire_node_disjoint(self, dep_lock, event_loop):
        await dep_lock.acquire(4)
        assert dep_lock.locked(4)
        assert not dep_lock.would_lock(5)
        await dep_lock.acquire(5)
        assert dep_lock.locked(5)

        dep_lock.release(4)
        assert not dep_lock.locked(4)

        dep_lock.release(5)
        assert not dep_lock.locked(5)

    def test_acquire_node_ordering(self, dep_lock, event_loop):
        order = []

        async def thread_1():
            order.append(1)
            await dep_lock.acquire(1)
            order.append(2)
            assert dep_lock.locked(1)
            assert dep_lock.would_lock(2)

            order.append(3)
            await aio.sleep(1)
            order.append(5)

            dep_lock.release(1)
            order.append(6)

        async def thread_2():
            order.append(4)
            assert dep_lock.would_lock(2)
            await dep_lock.acquire(2)
            order.append(7)
            assert dep_lock.locked(2)

            dep_lock.release(2)
            order.append(8)

            event_loop.stop()

        t1 = event_loop.create_task(thread_1())
        assert not t1.done()

        t2 = event_loop.create_task(thread_2())
        assert not t2.done()

        event_loop.run_forever()

        assert order == [1, 2, 3, 4, 5, 6, 7, 8]
