"""
probe.py — Chandy-Misra-Haas Edge-Chasing Algorithm
Implements probe message structure and propagation logic.

Algorithm summary:
  1. When Pi is blocked, it sends probe(i, i, j) to each Pj it waits for.
  2. When Pk receives probe(i, s, k):
       - If k == i  →  DEADLOCK DETECTED (cycle closed).
       - If Pk is blocked and hasn't forwarded for initiator i yet:
           forward probe(i, k, m) to each Pm that Pk waits for.
  3. Message complexity: O(N²) in worst case.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Callable


@dataclass
class Probe:
    """A probe message used in the Chandy-Misra-Haas edge-chasing algorithm."""
    initiator: int          # Process that started the probe
    sender: int             # Process that most recently forwarded this probe
    receiver: int           # Current destination process
    site_path: List[int] = field(default_factory=list)  # Sites visited in order
    timestamp: float = 0.0


@dataclass
class SimulationEvent:
    """Records a discrete simulation event for logging and visualization."""
    time: float
    event_type: str         # See EVENT_TYPES below
    description: str
    source: Optional[int] = None
    target: Optional[int] = None
    site: Optional[int] = None
    probe: Optional[Probe] = None
    cycle: Optional[List[int]] = None


EVENT_TYPES = {
    'resource_request',
    'resource_grant',
    'probe_sent',
    'probe_received',
    'deadlock_detected',
    'deadlock_resolved',
    'simulation_start',
    'simulation_end',
}


class ProbeEngine:
    """
    Implements probe dispatch and reception for the CMH edge-chasing algorithm.

    Dependencies are injected to keep this class decoupled from SimPy and
    Streamlit:
      - `get_process`  : pid → Process
      - `get_site_id`  : pid → int
      - `log_event`    : records SimulationEvent objects
      - `on_deadlock`  : callback(cycle) when a deadlock is detected
      - `dispatch`     : callback(probe) to schedule delivery (may add delay)
    """

    def __init__(
        self,
        get_process: Callable,
        get_site_id: Callable,
        log_event: Callable,
        on_deadlock: Callable,
        dispatch: Callable,
        now: Callable,
    ):
        self._get_process = get_process
        self._get_site_id = get_site_id
        self._log_event = log_event
        self._on_deadlock = on_deadlock
        self._dispatch = dispatch          # schedule_delivery(probe)
        self._now = now                    # returns current simulation time
        self.probe_messages: List[Probe] = []

    def initiate(self, initiator_pid: int, waited_for_pid: int) -> None:
        """
        Step 1 — Initiation.
        Called when `initiator_pid` becomes blocked waiting for `waited_for_pid`.
        Sends probe(i, i, j).
        """
        probe = Probe(
            initiator=initiator_pid,
            sender=initiator_pid,
            receiver=waited_for_pid,
            site_path=[self._get_site_id(initiator_pid)],
            timestamp=self._now(),
        )
        self.probe_messages.append(probe)
        self._get_process(initiator_pid).probe_sent.add(initiator_pid)

        self._log_event(
            'probe_sent',
            f"Probe({initiator_pid},{initiator_pid},{waited_for_pid}) sent by P{initiator_pid}",
            source=initiator_pid,
            target=waited_for_pid,
            probe=probe,
            site=self._get_site_id(initiator_pid),
        )
        self._dispatch(probe)

    def receive(self, probe: Probe) -> None:
        """
        Steps 2 & 3 — Reception and forwarding / detection.
        Called when `probe.receiver` receives the probe message.
        """
        receiver_pid = probe.receiver
        receiver = self._get_process(receiver_pid)
        current_site = self._get_site_id(receiver_pid)

        if current_site not in probe.site_path:
            probe.site_path.append(current_site)

        self._log_event(
            'probe_received',
            f"Probe({probe.initiator},{probe.sender},{probe.receiver}) received by P{receiver_pid}",
            source=probe.sender,
            target=receiver_pid,
            probe=probe,
            site=current_site,
        )

        # ── Detection: probe returned to its initiator ──────────────────────
        if receiver_pid == probe.initiator:
            self._on_deadlock(probe)
            return

        # ── Forwarding: receiver is blocked and hasn't handled this initiator
        if receiver.blocked and probe.initiator not in receiver.probe_sent:
            receiver.probe_sent.add(probe.initiator)

            if receiver.waiting_for is not None:
                forwarded = Probe(
                    initiator=probe.initiator,
                    sender=receiver_pid,
                    receiver=receiver.waiting_for,
                    site_path=probe.site_path.copy(),
                    timestamp=self._now(),
                )
                self.probe_messages.append(forwarded)

                self._log_event(
                    'probe_sent',
                    f"Probe({forwarded.initiator},{forwarded.sender},{forwarded.receiver}) forwarded by P{receiver_pid}",
                    source=receiver_pid,
                    target=receiver.waiting_for,
                    probe=forwarded,
                    site=current_site,
                )
                self._dispatch(forwarded)