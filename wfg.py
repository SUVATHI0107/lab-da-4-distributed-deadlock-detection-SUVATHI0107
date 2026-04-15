"""
wfg.py — Wait-For Graph (WFG) Model
Handles graph construction, edge management, and cycle detection.
"""

import networkx as nx
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Resource:
    """Represents a shared resource in the distributed system."""
    resource_id: int
    site_id: int
    capacity: int = 1
    held_by: List[int] = field(default_factory=list)
    waiting_queue: List[int] = field(default_factory=list)

    @property
    def is_available(self) -> bool:
        return len(self.held_by) < self.capacity

    def acquire(self, pid: int) -> bool:
        """Try to acquire. Returns True if granted immediately."""
        if self.is_available:
            self.held_by.append(pid)
            return True
        if pid not in self.waiting_queue:
            self.waiting_queue.append(pid)
        return False

    def release(self, pid: int) -> Optional[int]:
        """Release resource. Returns next waiter PID if any, else None."""
        if pid in self.held_by:
            self.held_by.remove(pid)
        next_waiter = None
        if self.waiting_queue and self.is_available:
            next_waiter = self.waiting_queue.pop(0)
            self.held_by.append(next_waiter)
        return next_waiter


@dataclass
class Process:
    """Represents a process in the distributed system."""
    pid: int
    site_id: int
    waiting_for: Optional[int] = None
    waiting_for_resource: Optional[int] = None
    holding: List[int] = field(default_factory=list)
    blocked: bool = False
    probe_sent: "set[int]" = field(default_factory=set)


class WaitForGraph:
    """
    Manages a directed Wait-For Graph (WFG) for deadlock detection.

    Nodes represent processes; a directed edge Pi → Pj means
    'Pi is waiting for Pj to release a resource'.
    A deadlock exists iff the graph contains a directed cycle.
    """

    def __init__(self):
        self._graph: nx.DiGraph = nx.DiGraph()

    def add_node(self, pid: int) -> None:
        self._graph.add_node(pid)

    def add_edge(self, waiting: int, waited_for: int) -> None:
        """Record that `waiting` is waiting for `waited_for`."""
        self._graph.add_edge(waiting, waited_for)

    def remove_edge(self, waiting: int, waited_for: int) -> None:
        if self._graph.has_edge(waiting, waited_for):
            self._graph.remove_edge(waiting, waited_for)

    def has_edge(self, u: int, v: int) -> bool:
        return self._graph.has_edge(u, v)

    def find_cycles(self) -> List[List[int]]:
        """Return all simple cycles in the graph."""
        try:
            return list(nx.simple_cycles(self._graph))
        except Exception:
            return []

    def find_cycle_containing(self, pid: int) -> Optional[List[int]]:
        """Find a cycle containing `pid`, rotated so pid is first."""
        for cycle in self.find_cycles():
            if pid in cycle:
                idx = cycle.index(pid)
                rotated = cycle[idx:] + cycle[:idx] + [pid]
                return rotated
        return None

    @property
    def nodes(self) -> List[int]:
        return list(self._graph.nodes())

    @property
    def edges(self) -> List[tuple]:
        return list(self._graph.edges())

    @property
    def graph(self) -> nx.DiGraph:
        return self._graph


class Site:
    """Represents a distributed site with its own local WFG and resources."""

    def __init__(self, site_id: int, processes: List[Process]):
        self.site_id = site_id
        self.processes: Dict[int, Process] = {p.pid: p for p in processes}
        self.local_wfg = WaitForGraph()
        self.resources: Dict[int, Resource] = {}

        for pid in self.processes:
            self.local_wfg.add_node(pid)

    def add_wait_edge(self, waiting: int, waited_for: int) -> None:
        self.local_wfg.add_edge(waiting, waited_for)

    def remove_wait_edge(self, waiting: int, waited_for: int) -> None:
        self.local_wfg.remove_edge(waiting, waited_for)

    def get_local_cycles(self) -> List[List[int]]:
        return self.local_wfg.find_cycles()