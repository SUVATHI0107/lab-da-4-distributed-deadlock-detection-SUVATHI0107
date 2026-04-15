"""
simulation.py — Distributed Deadlock Detection: Core Engine
Orchestrates the SimPy event loop, site/process setup, resource allocation,
and the Chandy-Misra-Haas probe algorithm.

Imports:
  wfg.py   — Process, Resource, Site, WaitForGraph
  probe.py — Probe, ProbeEngine, SimulationEvent
"""

import simpy
import random
from typing import Dict, List, Optional

from wfg import Process, Resource, Site, WaitForGraph
from probe import Probe, ProbeEngine, SimulationEvent

# Simulated network delay between sites (simulation time units)
MESSAGE_DELAY = 1


class DistributedDeadlockDetector:
    """
    Main simulation class.

    Responsibilities:
      - Initialise sites, processes, resources (via wfg.py types)
      - Drive the SimPy event loop with realistic per-hop probe delays
      - Delegate probe logic entirely to ProbeEngine (probe.py)
      - Maintain a global WFG and per-site WFGs for visualisation
    """

    def __init__(
        self,
        num_sites: int = 3,
        processes_per_site: int = 3,
        num_resources: int = 6,
        seed: int = 42,
    ):
        self.num_sites = num_sites
        self.processes_per_site = processes_per_site
        self.num_resources = num_resources
        self.seed = seed
        random.seed(seed)

        self.env = simpy.Environment()
        self.sites: Dict[int, Site] = {}
        self.all_processes: Dict[int, Process] = {}
        self.all_resources: Dict[int, Resource] = {}
        self.global_wfg = WaitForGraph()

        self.events: List[SimulationEvent] = []
        self.detected_deadlocks: List[List[int]] = []
        self.resolved_deadlocks: int = 0

        self._setup_system()

        # Wire up the ProbeEngine with callbacks pointing back into this class
        self._probe_engine = ProbeEngine(
            get_process=lambda pid: self.all_processes[pid],
            get_site_id=lambda pid: self.all_processes[pid].site_id,
            log_event=self._log_event,
            on_deadlock=self._handle_detected_deadlock,
            dispatch=self._schedule_probe,
            now=lambda: self.env.now,
        )

    # ── Setup ─────────────────────────────────────────────────────────────────

    def _setup_system(self) -> None:
        pid = 0
        for site_id in range(self.num_sites):
            procs = [Process(pid=pid + i, site_id=site_id)
                     for i in range(self.processes_per_site)]
            for p in procs:
                self.all_processes[p.pid] = p
                self.global_wfg.add_node(p.pid)
            pid += self.processes_per_site

            site = Site(site_id, procs)

            # Distribute resources evenly across sites
            per_site = self.num_resources // self.num_sites
            for r in range(site_id * per_site, (site_id + 1) * per_site):
                res = Resource(resource_id=r, site_id=site_id)
                site.resources[r] = res
                self.all_resources[r] = res

            self.sites[site_id] = site

    # ── Logging ───────────────────────────────────────────────────────────────

    def _log_event(self, event_type: str, description: str, **kwargs) -> None:
        self.events.append(SimulationEvent(
            time=round(self.env.now, 2),
            event_type=event_type,
            description=description,
            **kwargs,
        ))

    # ── Resource management ───────────────────────────────────────────────────

    def request_resource(self, requester_pid: int, holder_pid: int) -> None:
        """
        Model a resource request: requester_pid wants something holder_pid holds.
        If the resource is unavailable, a wait-for edge is created and the
        CMH probe is initiated.
        """
        requester = self.all_processes[requester_pid]
        holder = self.all_processes[holder_pid]
        holder_site = self.sites[holder.site_id]

        # Locate (or lazily create) the resource held by holder_pid
        target: Optional[Resource] = None
        for res in holder_site.resources.values():
            if holder_pid in res.held_by:
                target = res
                break
        if target is None:
            for res in holder_site.resources.values():
                if res.is_available:
                    res.acquire(holder_pid)
                    holder.holding.append(res.resource_id)
                    target = res
                    break
        if target is None:
            target = next(iter(holder_site.resources.values()))

        requester.waiting_for_resource = target.resource_id
        granted = target.acquire(requester_pid)

        if granted:
            requester.holding.append(target.resource_id)
            self._log_event(
                'resource_grant',
                f"P{requester_pid} (Site {requester.site_id}) acquired R{target.resource_id} immediately",
                source=requester_pid, target=holder_pid, site=requester.site_id,
            )
            return

        # Resource busy → requester blocks, WFG edge created
        requester.waiting_for = holder_pid
        requester.blocked = True

        self.sites[requester.site_id].add_wait_edge(requester_pid, holder_pid)
        self.global_wfg.add_edge(requester_pid, holder_pid)

        self._log_event(
            'resource_request',
            f"P{requester_pid} (Site {requester.site_id}) → waiting for "
            f"R{target.resource_id} held by P{holder_pid} (Site {holder.site_id})",
            source=requester_pid, target=holder_pid, site=requester.site_id,
        )

        # Start CMH probe in a SimPy process (with realistic network delay)
        self.env.process(self._initiate_probe_async(requester_pid, holder_pid))

    def release_resource(self, holder_pid: int, waiter_pid: int) -> None:
        """Release a resource, promoting the next queued waiter if any."""
        holder = self.all_processes[holder_pid]
        waiter = self.all_processes[waiter_pid]

        waiter.blocked = False
        waiter.waiting_for = None
        waiter.probe_sent.clear()

        rid = waiter.waiting_for_resource
        if rid is not None and rid in self.all_resources:
            res = self.all_resources[rid]
            next_pid = res.release(waiter_pid)
            if next_pid is not None:
                nxt = self.all_processes[next_pid]
                nxt.holding.append(rid)
                nxt.blocked = False
                nxt.waiting_for = None
            for hrid in list(holder.holding):
                if hrid in self.all_resources:
                    self.all_resources[hrid].release(holder_pid)
            holder.holding.clear()

        waiter.waiting_for_resource = None

        site = self.sites[waiter.site_id]
        site.remove_wait_edge(waiter_pid, holder_pid)
        self.global_wfg.remove_edge(waiter_pid, holder_pid)

        self._log_event(
            'resource_grant',
            f"P{holder_pid} released resource → P{waiter_pid} unblocked",
            source=holder_pid, target=waiter_pid, site=holder.site_id,
        )

    # ── Probe scheduling (SimPy integration) ─────────────────────────────────

    def _schedule_probe(self, probe: Probe) -> None:
        """Dispatch probe delivery as a SimPy process with a per-hop delay."""
        self.env.process(self._deliver_probe_async(probe))

    def _initiate_probe_async(self, initiator: int, waited_for: int):
        sender_site = self.all_processes[initiator].site_id
        receiver_site = self.all_processes[waited_for].site_id
        delay = MESSAGE_DELAY if sender_site != receiver_site else 0
        yield self.env.timeout(delay)
        self._probe_engine.initiate(initiator, waited_for)

    def _deliver_probe_async(self, probe: Probe):
        sender_site = self.all_processes[probe.sender].site_id
        receiver_site = self.all_processes[probe.receiver].site_id
        delay = MESSAGE_DELAY if sender_site != receiver_site else 0
        yield self.env.timeout(delay)
        self._probe_engine.receive(probe)

    # ── Deadlock handling ─────────────────────────────────────────────────────

    def _handle_detected_deadlock(self, probe: Probe) -> None:
        """Callback invoked by ProbeEngine when a cycle is confirmed."""
        cycle = self.global_wfg.find_cycle_containing(probe.initiator) or [probe.initiator]
        self._log_event(
            'deadlock_detected',
            f"🔴 DEADLOCK DETECTED! Cycle: {' → '.join(map(str, cycle))}",
            source=probe.initiator,
            cycle=cycle,
            site=self.all_processes[probe.initiator].site_id,
        )
        if cycle not in self.detected_deadlocks:
            self.detected_deadlocks.append(cycle)

    def resolve_deadlock(self, cycle: List[int]) -> None:
        """Abort the highest-PID process in the cycle (simple victim selection)."""
        if not cycle:
            return
        victim = max(cycle[:-1]) if len(cycle) > 1 else cycle[0]
        victim_proc = self.all_processes[victim]

        if victim_proc.waiting_for is not None:
            self.release_resource(victim_proc.waiting_for, victim)

        victim_proc.blocked = False
        victim_proc.probe_sent.clear()
        self.resolved_deadlocks += 1

        self._log_event(
            'deadlock_resolved',
            f"✅ Deadlock resolved: P{victim} (Site {victim_proc.site_id}) aborted as victim",
            source=victim,
            cycle=cycle,
            site=victim_proc.site_id,
        )

    # ── Scenarios ─────────────────────────────────────────────────────────────

    def create_deadlock_scenario(self, scenario: str = "chain") -> None:
        """Set up one of four predefined deadlock scenarios."""
        pids = list(self.all_processes.keys())
        pps = self.processes_per_site

        if scenario == "simple" and self.num_sites >= 2:
            p0, p1 = pids[0], pids[pps]
            self.request_resource(p0, p1)
            self.request_resource(p1, p0)

        elif scenario == "chain" and self.num_sites >= 3:
            p0, p1, p2 = pids[0], pids[pps], pids[pps * 2]
            self.request_resource(p0, p1)
            self.request_resource(p1, p2)
            self.request_resource(p2, p0)

        elif scenario == "complex":
            n = len(pids)
            if n >= 3:
                self.request_resource(pids[0], pids[1])
                self.request_resource(pids[1], pids[2])
                self.request_resource(pids[2], pids[0])
            if n >= 6:
                self.request_resource(pids[3], pids[4])
                self.request_resource(pids[4], pids[5])
                self.request_resource(pids[5], pids[3])

        elif scenario == "random":
            for _ in range(len(pids)):
                a = random.choice(pids)
                b = random.choice([p for p in pids if p != a])
                if not self.all_processes[a].blocked:
                    self.request_resource(a, b)

    # ── Main entry point ──────────────────────────────────────────────────────

    def run_simulation(self, scenario: str = "chain", auto_resolve: bool = True) -> dict:
        """Run the complete simulation and return results for the UI."""
        self._log_event(
            'simulation_start',
            f"Simulation started: {self.num_sites} sites, "
            f"{len(self.all_processes)} processes, scenario='{scenario}'",
        )

        self.create_deadlock_scenario(scenario)
        self.env.run()  # Drive all scheduled probe deliveries

        if auto_resolve:
            for cycle in self.detected_deadlocks:
                self.resolve_deadlock(cycle)

        self._log_event(
            'simulation_end',
            f"Simulation complete (t={self.env.now}). "
            f"Deadlocks detected: {len(self.detected_deadlocks)}, "
            f"Resolved: {self.resolved_deadlocks}",
        )

        return self._build_result()

    def _build_result(self) -> dict:
        site_graphs = {
            sid: {
                'nodes': site.local_wfg.nodes,
                'edges': site.local_wfg.edges,
                'processes': list(site.processes.keys()),
            }
            for sid, site in self.sites.items()
        }

        process_states = {
            pid: {
                'pid': pid,
                'site': proc.site_id,
                'blocked': proc.blocked,
                'waiting_for': proc.waiting_for,
                'in_deadlock': any(pid in c for c in self.detected_deadlocks),
            }
            for pid, proc in self.all_processes.items()
        }

        return {
            'events': self.events,
            'site_graphs': site_graphs,
            'global_graph': {
                'nodes': self.global_wfg.nodes,
                'edges': self.global_wfg.edges,
            },
            'process_states': process_states,
            'detected_deadlocks': self.detected_deadlocks,
            'probe_messages': self._probe_engine.probe_messages,
            'resolved_deadlocks': self.resolved_deadlocks,
            'num_sites': self.num_sites,
            'num_processes': len(self.all_processes),
            'processes_per_site': self.processes_per_site,
            'resource_states': {
                rid: {
                    'resource_id': res.resource_id,
                    'site_id': res.site_id,
                    'capacity': res.capacity,
                    'held_by': list(res.held_by),
                    'waiting_queue': list(res.waiting_queue),
                }
                for rid, res in self.all_resources.items()
            },
        }


# ── CLI demo ──────────────────────────────────────────────────────────────────

def run_demo():
    print("=" * 60)
    print("Distributed Deadlock Detection Simulation")
    print("Algorithm: Chandy-Misra-Haas Edge-Chasing")
    print("=" * 60)

    for scenario in ["simple", "chain", "complex"]:
        print(f"\n--- Scenario: {scenario.upper()} ---")
        sim = DistributedDeadlockDetector(
            num_sites=3, processes_per_site=3, num_resources=6, seed=42
        )
        result = sim.run_simulation(scenario=scenario, auto_resolve=True)

        print(f"Processes: {result['num_processes']} across {result['num_sites']} sites")
        print(f"Events logged: {len(result['events'])}")
        print(f"Deadlocks detected: {len(result['detected_deadlocks'])}")
        print(f"Deadlocks resolved: {result['resolved_deadlocks']}")
        print(f"Probe messages sent: {len(result['probe_messages'])}")
        for i, cycle in enumerate(result['detected_deadlocks']):
            print(f"  Deadlock {i+1}: {' → '.join(map(str, cycle))}")

        print("\nEvent Log:")
        for e in result['events']:
            print(f"  [t={e.time}] {e.event_type}: {e.description}")


if __name__ == "__main__":
    run_demo()