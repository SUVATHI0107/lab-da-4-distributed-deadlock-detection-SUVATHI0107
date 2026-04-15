"""
app.py — Streamlit App: Distributed Deadlock Detection Simulation
Visualizes the Chandy-Misra-Haas Edge-Chasing Algorithm.

Imports simulation logic from:
  simulation.py  (orchestration + SimPy)
  wfg.py         (graph types — indirectly via simulation)
  probe.py       (probe types — SimulationEvent used for typing)
"""

import streamlit as st
import networkx as nx
import plotly.graph_objects as go
import pandas as pd
import math

from simulation import DistributedDeadlockDetector
from probe import SimulationEvent

# ─── Page Config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Distributed Deadlock Detector",
    page_icon="🔴",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Custom CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Space+Grotesk:wght@300;400;600;700&display=swap');

  html, body, [class*="css"] { font-family: 'Space Grotesk', sans-serif; }
  .main { background: #0a0e1a; }
  h1, h2, h3 { font-family: 'JetBrains Mono', monospace !important; color: #e2e8f0 !important; }
  .stApp { background: #0a0e1a; }

  .metric-card {
    background: linear-gradient(135deg, #1a2035 0%, #0f1929 100%);
    border: 1px solid #2d3748; border-radius: 12px;
    padding: 20px; text-align: center; margin: 6px 0;
  }
  .metric-value { font-family: 'JetBrains Mono', monospace; font-size: 2.5rem; font-weight: 700; margin: 0; }
  .metric-label { font-size: 0.8rem; color: #718096; text-transform: uppercase; letter-spacing: 0.1em; margin-top: 4px; }

  .event-card {
    font-family: 'JetBrains Mono', monospace; font-size: 0.78rem;
    padding: 8px 12px; margin: 3px 0; border-radius: 6px; border-left: 3px solid;
  }
  .event-deadlock_detected  { background: rgba(239,68,68,0.1);   border-color: #ef4444; color: #fca5a5; }
  .event-deadlock_resolved  { background: rgba(34,197,94,0.1);   border-color: #22c55e; color: #86efac; }
  .event-probe_sent         { background: rgba(251,191,36,0.08); border-color: #fbbf24; color: #fde68a; }
  .event-probe_received     { background: rgba(251,191,36,0.05); border-color: #d97706; color: #fcd34d; }
  .event-resource_request   { background: rgba(96,165,250,0.08); border-color: #60a5fa; color: #bfdbfe; }
  .event-resource_grant     { background: rgba(52,211,153,0.08); border-color: #34d399; color: #a7f3d0; }
  .event-simulation_start, .event-simulation_end { background: rgba(139,92,246,0.08); border-color: #8b5cf6; color: #c4b5fd; }

  .algo-box {
    background: #0f1929; border: 1px solid #2d3748; border-radius: 10px;
    padding: 16px 20px; font-family: 'JetBrains Mono', monospace;
    font-size: 0.82rem; color: #94a3b8; line-height: 1.7;
  }
  .site-header { font-family: 'JetBrains Mono', monospace; font-size: 0.9rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.15em; margin-bottom: 8px; }
  .stSelectbox label, .stSlider label, .stCheckbox label { color: #94a3b8 !important; font-size: 0.85rem; }
  div[data-testid="stSidebar"] { background: #0d1424 !important; border-right: 1px solid #1e293b; }

  .stButton > button {
    background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%);
    color: white; border: none; border-radius: 8px;
    font-family: 'JetBrains Mono', monospace; font-weight: 600;
    font-size: 0.9rem; padding: 10px 24px; transition: all 0.2s; width: 100%;
  }
  .stButton > button:hover {
    background: linear-gradient(135deg, #60a5fa 0%, #3b82f6 100%);
    box-shadow: 0 0 20px rgba(59,130,246,0.4);
  }
  .banner {
    background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #0f172a 100%);
    border: 1px solid #312e81; border-radius: 16px; padding: 28px 36px; margin-bottom: 24px;
  }
  .banner h1 {
    font-size: 1.8rem !important;
    background: linear-gradient(90deg, #60a5fa, #a78bfa, #f472b6);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin: 0 !important;
  }
  .banner p { color: #64748b; font-size: 0.88rem; margin: 6px 0 0 0; }
  .process-pill { display: inline-block; padding: 3px 10px; border-radius: 20px; font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; font-weight: 600; margin: 2px; }
</style>
""", unsafe_allow_html=True)

# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Simulation Config")
    st.markdown("---")

    num_sites       = st.slider("Number of Sites",       2,  5, 3)
    procs_per_site  = st.slider("Processes per Site",    2,  5, 3)
    num_resources   = st.slider("Total Resources",       4, 12, 6)
    seed            = st.slider("Random Seed",           0, 100, 42)

    st.markdown("---")
    scenario = st.selectbox(
        "Deadlock Scenario",
        ["simple", "chain", "complex", "random"],
        index=1,
        format_func=lambda x: {
            "simple":  "🔴 Simple (2-process cycle)",
            "chain":   "🔗 Chain (3-site cycle)",
            "complex": "🕸️ Complex (multiple deadlocks)",
            "random":  "🎲 Random",
        }[x],
    )
    auto_resolve = st.checkbox("Auto-resolve deadlocks", value=True)

    st.markdown("---")
    run_btn = st.button("▶ RUN SIMULATION", use_container_width=True)

    st.markdown("---")
    st.markdown("""
    <div class="algo-box">
    <b style="color:#a78bfa">CMH Algorithm:</b><br><br>
    1. Pi blocked → sends<br>
       probe(i, i, j) to Pj<br><br>
    2. Pk receives probe(i,s,k):<br>
       • If k == i → DEADLOCK<br>
       • If Pk blocked &amp; new i:<br>
         forward probe(i,k,m)<br>
         for each Pm Pk waits for<br><br>
    <b style="color:#34d399">Complexity:</b> O(N²) messages
    </div>
    """, unsafe_allow_html=True)


# ─── Banner ───────────────────────────────────────────────────────────────────
st.markdown("""
<div class="banner">
  <h1>🔴 Distributed Deadlock Detector</h1>
  <p>Chandy-Misra-Haas Edge-Chasing Algorithm · Wait-For Graph Model · SimPy Discrete-Event Simulation</p>
</div>
""", unsafe_allow_html=True)


# ─── Run simulation ───────────────────────────────────────────────────────────
if 'result' not in st.session_state or run_btn:
    sim = DistributedDeadlockDetector(
        num_sites=num_sites,
        processes_per_site=procs_per_site,
        num_resources=num_resources,
        seed=seed,
    )
    st.session_state.result   = sim.run_simulation(scenario=scenario, auto_resolve=auto_resolve)
    st.session_state.scenario = scenario

result    = st.session_state.result
events    = result['events']
deadlocks = result['detected_deadlocks']
probes    = result['probe_messages']


# ─── Metrics ──────────────────────────────────────────────────────────────────
c1, c2, c3, c4, c5 = st.columns(5)
metrics = [
    (c1, result['num_sites'],          "#60a5fa", "Sites"),
    (c2, result['num_processes'],      "#a78bfa", "Processes"),
    (c3, len(probes),                  "#fbbf24", "Probes Sent"),
    (c4, len(deadlocks),               "#ef4444" if deadlocks else "#22c55e", "Deadlocks Found"),
    (c5, result['resolved_deadlocks'], "#34d399", "Resolved"),
]
for col, val, color, label in metrics:
    with col:
        st.markdown(f"""
        <div class="metric-card">
          <p class="metric-value" style="color:{color}">{val}</p>
          <p class="metric-label">{label}</p>
        </div>""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)


# ─── WFG Figure helper ────────────────────────────────────────────────────────
def make_wfg_figure(nodes, edges, process_states, title, highlight_cycles=None, size=(700, 400)):
    G = nx.DiGraph()
    G.add_nodes_from(nodes)
    G.add_edges_from(edges)

    if not nodes:
        fig = go.Figure()
        fig.add_annotation(text="No processes", x=0.5, y=0.5, showarrow=False, font=dict(color="#64748b"))
        fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        return fig

    pos = nx.circular_layout(G) if len(nodes) <= 6 else nx.spring_layout(G, seed=42, k=2)

    deadlocked = set(pid for cycle in (highlight_cycles or []) for pid in cycle)

    # Edge trace (lines only; arrows added via annotations)
    ex, ey = [], []
    for u, v in G.edges():
        x0, y0 = pos[u]; x1, y1 = pos[v]
        mx, my = (x0+x1)/2, (y0+y1)/2
        ex += [x0, mx, x1, None]; ey += [y0, my, y1, None]

    edge_trace = go.Scatter(x=ex, y=ey, mode='lines',
                            line=dict(color='#475569', width=2), hoverinfo='none')

    annotations = []
    for u, v in G.edges():
        x0, y0 = pos[u]; x1, y1 = pos[v]
        color = '#ef4444' if (u in deadlocked and v in deadlocked) else '#60a5fa'
        annotations.append(dict(
            x=x1, y=y1, ax=x0, ay=y0,
            xref='x', yref='y', axref='x', ayref='y',
            showarrow=True, arrowhead=2, arrowsize=1.5, arrowwidth=2, arrowcolor=color,
        ))

    nx_list = list(G.nodes())
    node_colors, node_sizes, node_text, node_hover = [], [], [], []
    for n in nx_list:
        s = process_states.get(n, {})
        blocked, dl = s.get('blocked', False), n in deadlocked
        node_colors.append('#ef4444' if dl else ('#f59e0b' if blocked else '#22c55e'))
        node_sizes.append(28 if dl else (22 if blocked else 20))
        node_text.append(f"P{n}")
        status = '🔴 DEADLOCKED' if dl else ('⚠️ Blocked' if blocked else '✅ Running')
        tip = f"<b>P{n}</b><br>Site: {s.get('site','?')}<br>Status: {status}"
        if s.get('waiting_for') is not None:
            tip += f"<br>Waiting for: P{s['waiting_for']}"
        node_hover.append(tip)

    node_trace = go.Scatter(
        x=[pos[n][0] for n in nx_list], y=[pos[n][1] for n in nx_list],
        mode='markers+text', hoverinfo='text', hovertext=node_hover,
        text=node_text, textposition='middle center',
        textfont=dict(size=11, color='white', family='JetBrains Mono'),
        marker=dict(size=node_sizes, color=node_colors,
                    line=dict(width=2, color='#1e293b'), opacity=0.92),
    )

    return go.Figure(
        data=[edge_trace, node_trace],
        layout=go.Layout(
            title=dict(text=title, font=dict(color='#94a3b8', size=13, family='JetBrains Mono')),
            showlegend=False, hovermode='closest',
            margin=dict(b=10, l=10, r=10, t=40),
            annotations=annotations,
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            paper_bgcolor='rgba(15,25,41,0.8)', plot_bgcolor='rgba(15,25,41,0.8)',
            height=size[1],
        ),
    )


# ─── Tabs ─────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs([
    "🌐 Global Wait-For Graph",
    "🏗️ Per-Site WFGs",
    "📡 Probe Trace",
    "📋 Event Log",
])

# Tab 1 — Global WFG
with tab1:
    st.markdown("#### Global Wait-For Graph")
    st.caption("Aggregated cross-site view — red nodes are in detected deadlock cycles")
    gg = result['global_graph']
    fig = make_wfg_figure(gg['nodes'], gg['edges'], result['process_states'],
                          "Global WFG", deadlocks, (900, 480))
    st.plotly_chart(fig, use_container_width=True)

    if deadlocks:
        st.markdown("##### 🔴 Detected Deadlock Cycles")
        for i, cycle in enumerate(deadlocks):
            pills = " → ".join(
                f'<span class="process-pill" style="background:rgba(239,68,68,0.2);'
                f'color:#fca5a5;border:1px solid #ef4444">P{p} (S{result["process_states"][p]["site"]})</span>'
                for p in cycle
            )
            st.markdown(f"**Cycle {i+1}:** {pills}", unsafe_allow_html=True)
    else:
        st.info("No deadlocks detected in this run.")


# Tab 2 — Per-Site WFGs
with tab2:
    st.markdown("#### Local Wait-For Graphs per Site")
    st.caption("Each site maintains an independent local WFG — probes cross site boundaries")
    site_cols = st.columns(min(result['num_sites'], 3))
    palette = ['#3b82f6', '#8b5cf6', '#ec4899', '#10b981', '#f59e0b']

    for sid in range(result['num_sites']):
        with site_cols[sid % 3]:
            sd    = result['site_graphs'][sid]
            color = palette[sid % len(palette)]
            st.markdown(f'<p class="site-header" style="color:{color}">◆ Site {sid} · {len(sd["processes"])} processes</p>',
                        unsafe_allow_html=True)
            fig = make_wfg_figure(sd['nodes'], sd['edges'], result['process_states'],
                                  f"Site {sid} Local WFG", deadlocks, (400, 280))
            st.plotly_chart(fig, use_container_width=True)
            for pid in sd['processes']:
                ps = result['process_states'].get(pid, {})
                dl, bl = ps.get('in_deadlock', False), ps.get('blocked', False)
                status = "🔴 DEADLOCKED" if dl else ("⚠️ blocked" if bl else "✅ running")
                wf = f" → P{ps['waiting_for']}" if ps.get('waiting_for') is not None else ""
                st.markdown(f'<span style="font-family:JetBrains Mono;font-size:0.78rem;color:#64748b">P{pid}{wf} — {status}</span>',
                            unsafe_allow_html=True)


# Tab 3 — Probe Trace
with tab3:
    st.markdown("#### Probe Message Trace")
    st.caption("Edge-chasing probes: Probe(initiator, sender, receiver) propagate through blocked processes")

    if probes:
        probe_data = [{
            'Probe #':      i + 1,
            'Initiator':    f"P{p.initiator}",
            'Sender':       f"P{p.sender}",
            'Receiver':     f"P{p.receiver}",
            'Notation':     f"probe({p.initiator},{p.sender},{p.receiver})",
            'Sites Crossed': len(set(p.site_path)),
            'Path':         ' → '.join(f'S{s}' for s in p.site_path),
        } for i, p in enumerate(probes)]

        # Timeline figure
        unique_procs = sorted(set(p.sender for p in probes) | set(p.receiver for p in probes))
        proc_y = {pid: i for i, pid in enumerate(unique_procs)}
        fig2 = go.Figure()

        for i, p in enumerate(probes):
            is_return = (p.receiver == p.initiator)
            color = '#ef4444' if is_return else '#fbbf24'
            label = f"probe({p.initiator},{p.sender},{p.receiver})"
            fig2.add_trace(go.Scatter(
                x=[i, i + 0.8], y=[proc_y[p.sender], proc_y[p.receiver]],
                mode='lines+markers',
                line=dict(color=color, width=2),
                marker=dict(size=[8, 12], color=color, symbol=['circle', 'arrow-bar-up']),
                name=label, hovertemplate=f"{label}<extra></extra>", showlegend=False,
            ))
            fig2.add_annotation(
                x=(i + i + 0.8) / 2, y=(proc_y[p.sender] + proc_y[p.receiver]) / 2,
                text=f"({p.initiator},{p.sender},{p.receiver})",
                font=dict(size=9, color='#94a3b8', family='JetBrains Mono'), showarrow=False,
            )

        fig2.update_layout(
            yaxis=dict(tickvals=list(proc_y.values()),
                       ticktext=[f"P{pid}" for pid in proc_y.keys()],
                       showgrid=True, gridcolor='#1e293b',
                       tickfont=dict(family='JetBrains Mono', color='#94a3b8')),
            xaxis=dict(title='Probe Sequence', showgrid=False,
                       tickfont=dict(family='JetBrains Mono', color='#64748b')),
            paper_bgcolor='rgba(15,25,41,0.8)', plot_bgcolor='rgba(15,25,41,0.8)',
            height=350,
            title=dict(text="Probe Propagation Timeline (red = cycle-completing probe)",
                       font=dict(color='#94a3b8', size=12, family='JetBrains Mono')),
        )
        st.plotly_chart(fig2, use_container_width=True)
        st.markdown("##### All Probes")
        st.dataframe(pd.DataFrame(probe_data), use_container_width=True, hide_index=True,
                     column_config={'Notation': st.column_config.TextColumn('Notation', width='medium')})
    else:
        st.info("No probes sent in this simulation.")


# Tab 4 — Event Log
with tab4:
    st.markdown("#### Simulation Event Log")
    filter_opts = ['resource_request', 'resource_grant', 'probe_sent', 'probe_received',
                   'deadlock_detected', 'deadlock_resolved', 'simulation_start', 'simulation_end']
    selected = st.multiselect("Filter by event type", options=filter_opts,
                              default=['resource_request', 'probe_sent', 'deadlock_detected',
                                       'deadlock_resolved', 'simulation_start', 'simulation_end'])
    icons = {
        'resource_request': '📥', 'resource_grant': '✅',
        'probe_sent': '📡', 'probe_received': '📨',
        'deadlock_detected': '🔴', 'deadlock_resolved': '🟢',
        'simulation_start': '▶️', 'simulation_end': '⏹️',
    }
    for e in events:
        if e.event_type not in selected:
            continue
        st.markdown(
            f'<div class="event-card event-{e.event_type}">'
            f'[t={e.time:.2f}] {icons.get(e.event_type,"•")} <b>{e.event_type}</b> — {e.description}'
            f'</div>',
            unsafe_allow_html=True,
        )


# ─── Footer ───────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("""
<div style="text-align:center;color:#334155;font-size:0.8rem;font-family:'JetBrains Mono',monospace;padding:16px">
  Distributed Deadlock Detection · Chandy-Misra-Haas Algorithm · SimPy + NetworkX + Streamlit<br>
  Wait-For Graph Model · Edge-Chasing Probes · O(N²) Message Complexity
</div>
""", unsafe_allow_html=True)