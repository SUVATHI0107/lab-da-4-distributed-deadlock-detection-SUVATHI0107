[![Review Assignment Due Date](https://classroom.github.com/assets/deadline-readme-button-22041afd0340ce965d47ae6ef1cefeee28c7c493a6346c4f15d667ab976d596c.svg)](https://classroom.github.com/a/Xdwtc3RS)
# 🔴 Distributed Deadlock Detection Simulation

> A discrete-event simulation of distributed deadlock detection using the **Wait-For Graph (WFG)** model and the **Chandy-Misra-Haas Edge-Chasing Algorithm**, built with **SimPy**, **NetworkX**, and **Streamlit**.

---

## 📋 Overview

In distributed systems, deadlocks occur when a set of processes form a circular dependency while waiting for resources held by each other. Unlike centralized systems, distributed deadlock detection is challenging because:

- No single site has a complete view of the global state
- Processes and resources span multiple sites
- Detecting cycles requires coordinated message passing

This simulation implements the **Chandy-Misra-Haas (CMH)** algorithm for distributed deadlock detection using the **edge-chasing (probe-based)** approach on a **Wait-For Graph (WFG)** model.

---

## 🧠 Algorithm: Chandy-Misra-Haas Edge-Chasing

### Core Concept

The algorithm works by injecting special **probe messages** into the network. A probe travels along the edges of the Wait-For Graph. If a probe returns to its initiator, a **cycle** has been detected — which means a **deadlock exists**.

### Probe Structure

```
Probe(i, s, r)
  i = initiator process (who started this probe)
  s = sender process    (who last forwarded this probe)
  r = receiver process  (destination of this probe)
```

### Algorithm Steps

1. **Initiation**: When process `Pᵢ` becomes blocked (waiting for some resource), it sends `probe(i, i, j)` to each process `Pⱼ` it is waiting for.

2. **Forwarding**: When process `Pₖ` receives `probe(i, s, k)`:
   - If `Pₖ` is **blocked** AND has not yet sent a probe with initiator `i`:
     - Record that probe with initiator `i` has arrived
     - For each process `Pₘ` that `Pₖ` is waiting for, forward `probe(i, k, m)`

3. **Detection**: If process `Pᵢ` (the initiator) receives `probe(i, s, i)` back, then:
   - A **cycle** has been detected → **DEADLOCK!**

### Example: 3-Site Chain Deadlock

```
Site 0      Site 1      Site 2
  P0    ──→   P3    ──→   P6
   ↑                       │
   └───────────────────────┘

P0 waits for P3 (cross-site)
P3 waits for P6 (cross-site)
P6 waits for P0 (cross-site)

Probe trace:
  probe(0, 0, 3) → probe(0, 3, 6) → probe(0, 6, 0)
  probe(6, 6, 0) → probe(6, 0, 3) → probe(6, 3, 6) ← DEADLOCK DETECTED!
```

### Properties

| Property | Value |
|---|---|
| Message Complexity | O(N²) in worst case |
| Detection Condition | Necessary and sufficient |
| False Positives | None (exact algorithm) |
| Topology Support | Arbitrary distributed graph |

---

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  Distributed System                     │
│                                                         │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐            │
│  │ Site 0  │    │ Site 1  │    │ Site 2  │            │
│  │         │    │         │    │         │            │
│  │ P0  P1  │    │ P3  P4  │    │ P6  P7  │            │
│  │    P2   │    │    P5   │    │    P8   │            │
│  │         │    │         │    │         │            │
│  │ Local   │    │ Local   │    │ Local   │            │
│  │  WFG    │    │  WFG    │    │  WFG    │            │
│  └────┬────┘    └────┬────┘    └────┬────┘            │
│       │              │              │                   │
│       └──────────────┼──────────────┘                  │
│            Probe Messages (Edge-Chasing)                │
└─────────────────────────────────────────────────────────┘
```

### Components

#### `simulation.py` — Core Engine

- **`Process`**: Dataclass representing a process with PID, site ID, blocked status, and wait-for pointer
- **`Probe`**: Dataclass for probe messages `(initiator, sender, receiver, path, timestamp)`
- **`Site`**: Represents a site with local processes, local WFG (NetworkX DiGraph), and resources
- **`DistributedDeadlockDetector`**: Main simulation class
  - `_setup_system()`: Initialize sites, processes, resources
  - `request_resource(requester, holder)`: Create wait-for edge + initiate probe
  - `_initiate_probe(initiator, waited_for)`: Start edge-chasing
  - `_receive_probe(probe)`: Handle probe reception (forward or detect)
  - `_reconstruct_cycle(probe)`: Find actual deadlock cycle from WFG
  - `resolve_deadlock(cycle)`: Abort victim process to break deadlock
  - `run_simulation(scenario, auto_resolve)`: Full simulation runner

#### `app.py` — Streamlit Frontend

- Interactive parameter controls (sites, processes, resources, seed)
- 4 scenario presets: simple, chain, complex, random
- Global and per-site WFG visualization (Plotly)
- Probe message timeline chart
- Filterable event log

---

## 🎭 Scenarios

### 1. Simple (2-process cycle)
```
P0 (Site 0) ⟷ P3 (Site 1)
```
Cross-site deadlock with minimal processes.

### 2. Chain (3-site cycle)
```
P0 (S0) → P3 (S1) → P6 (S2) → P0 (S0)
```
Classic 3-process chain deadlock spanning all sites.

### 3. Complex (multiple deadlocks)
```
Deadlock 1: P0 → P1 → P2 → P0  (Site 0)
Deadlock 2: P3 → P4 → P5 → P3  (Site 1)
```
Two simultaneous deadlocks; tests multi-cycle detection.

### 4. Random
Random wait-for edges; may or may not produce deadlocks.

---

## 🚀 Setup & Run

### Installation

```bash
git clone https://github.com/YOUR_USERNAME/distributed-deadlock-detection
cd distributed-deadlock-detection
pip install -r requirements.txt
```

### Run Streamlit App

```bash
streamlit run app.py
```

### Run CLI Demo

```bash
python simulation.py
```

### Expected Output (CLI)

```
============================================================
Distributed Deadlock Detection Simulation
Algorithm: Chandy-Misra-Haas Edge-Chasing
============================================================

--- Scenario: CHAIN ---
Processes: 9 across 3 sites
Events logged: 18
Deadlocks detected: 1
Deadlocks resolved: 1
Probe messages sent: 5
  Deadlock 1: 6 → 0 → 3 → 6
```

---

## 📊 Visualization Guide

### Global WFG Tab
- **Green nodes**: Running (not blocked)
- **Yellow nodes**: Blocked (waiting)
- **Red nodes**: In a deadlock cycle
- **Red arrows**: Deadlock cycle edges
- **Blue arrows**: Normal wait edges

### Per-Site WFGs Tab
Each site's local Wait-For Graph, showing only locally visible edges.

### Probe Trace Tab
- Timeline of all probe messages sent during detection
- **Yellow lines**: Normal probe propagation
- **Red lines**: Cycle-completing probe (deadlock detected)

### Event Log Tab
Chronological log with filters. Event types:
- `resource_request` — Process becomes blocked
- `probe_sent` — Probe message dispatched
- `probe_received` — Probe message received
- `deadlock_detected` — Cycle found (🔴)
- `deadlock_resolved` — Victim process aborted (✅)

---

## 🛠️ Technology Stack

| Component | Technology |
|---|---|
| Discrete-event simulation | SimPy 4.x |
| Graph algorithms | NetworkX 3.x |
| Web UI | Streamlit 1.32+ |
| Visualization | Plotly 5.x |
| Data manipulation | Pandas 2.x |

---

## 📚 References

1. Chandy, K. M., Misra, J., & Haas, L. M. (1983). *Distributed deadlock detection.* ACM Transactions on Computer Systems, 1(2), 144–156.
2. Tanenbaum, A. S., & Van Steen, M. (2007). *Distributed Systems: Principles and Paradigms* (2nd ed.). Prentice Hall.
3. Kshemkalyani, A. D., & Singhal, M. (2008). *Distributed Computing: Principles, Algorithms, and Systems.* Cambridge University Press.

---

## 👤 Author

Built as part of Distributed Systems coursework.  
Algorithm: Chandy-Misra-Haas (1983) · Model: Wait-For Graph