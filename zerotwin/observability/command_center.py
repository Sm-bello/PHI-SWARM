#!/usr/bin/env python3
"""
PHI-SWARM Command Center — full interactive SPA.

Every nav item is an evidence-bearing view fed by the live PHISwarmEngine
and/or results JSON under zerotwin/results/.

  python -m zerotwin.observability.command_center
  → http://127.0.0.1:5000
"""

from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from flask import Flask, jsonify, render_template_string, request

from zerotwin.simulation.phi_swarm_engine import PHISwarmEngine

logging.getLogger("werkzeug").setLevel(logging.ERROR)

app = Flask(__name__)
engine = PHISwarmEngine(num_nodes=5, seed=42, samples_per_node=300, round_interval=4.0)

_last_round_seen = -1
_last_agg_ts = "--"
_last_bytes = 0
_last_bytes_ts = time.time()
RESULTS = ROOT / "zerotwin" / "results"


def _load_json(name: str):
    p = RESULTS / name
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _enrich(state: dict) -> dict:
    global _last_round_seen, _last_agg_ts, _last_bytes, _last_bytes_ts
    now = time.time()
    if state["fed_round"] != _last_round_seen:
        _last_round_seen = state["fed_round"]
        _last_agg_ts = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    dt = max(now - _last_bytes_ts, 1e-6)
    d_bytes = max(state["bytes_transferred"] - _last_bytes, 0)
    state["data_rate_mbps"] = round((d_bytes / dt) / (1024 * 1024), 4)
    _last_bytes = state["bytes_transferred"]
    _last_bytes_ts = now
    state["last_agg"] = _last_agg_ts
    state["clock"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    state["global_model"] = f"live-r{state['fed_round']}"
    return state


HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>PHI-SWARM Command Center</title>
<style>
:root {
  --bg:#f1f5f9; --card:#fff; --border:#e2e8f0; --text:#0f172a; --muted:#64748b;
  --green:#16a34a; --amber:#d97706; --red:#dc2626; --blue:#2563eb; --indigo:#4f46e5;
}
*{box-sizing:border-box} body{margin:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:var(--bg);color:var(--text)}
.shell{display:grid;grid-template-columns:220px 1fr;min-height:100vh}
.side{background:#0f172a;color:#e2e8f0;padding:16px 12px;position:sticky;top:0;height:100vh;overflow-y:auto}
.side h1{font-size:14px;margin:0 0 4px;letter-spacing:.4px;color:#fff}
.side .sub{font-size:10px;color:#94a3b8;margin-bottom:16px}
.nav a{display:block;padding:9px 12px;border-radius:8px;color:#cbd5e1;text-decoration:none;font-size:13px;margin-bottom:2px}
.nav a:hover{background:#1e293b;color:#fff}
.nav a.active{background:#2563eb;color:#fff;font-weight:600}
.main{padding:16px 20px 40px}
.topbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;flex-wrap:wrap;gap:8px}
.topbar h2{margin:0;font-size:18px}
.badge{font-size:11px;padding:3px 10px;border-radius:999px;background:#dcfce7;color:#166534;font-weight:700}
.badge.warn{background:#fef3c7;color:#92400e}
.badge.crit{background:#fee2e2;color:#991b1b}
.grid{display:grid;gap:12px}
.grid-2{grid-template-columns:repeat(auto-fit,minmax(280px,1fr))}
.grid-3{grid-template-columns:repeat(auto-fit,minmax(200px,1fr))}
.grid-4{grid-template-columns:repeat(auto-fit,minmax(160px,1fr))}
.card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:14px 16px;box-shadow:0 1px 2px rgba(15,23,42,.04)}
.card h3{margin:0 0 10px;font-size:13px;color:var(--muted);text-transform:uppercase;letter-spacing:.4px}
.kpi{font-size:26px;font-weight:700}
.kpi.sm{font-size:18px}
.muted{color:var(--muted);font-size:12px}
.table{width:100%;border-collapse:collapse;font-size:12px}
.table th,.table td{text-align:left;padding:8px 6px;border-bottom:1px solid var(--border)}
.table th{color:var(--muted);font-weight:600}
.row-click{cursor:pointer}.row-click:hover{background:#f8fafc}
.pill{display:inline-block;padding:2px 8px;border-radius:999px;font-size:10px;font-weight:700}
.pill.ok{background:#dcfce7;color:#166534}
.pill.warn{background:#fef3c7;color:#92400e}
.pill.crit{background:#fee2e2;color:#991b1b}
.pill.grey{background:#e2e8f0;color:#475569}
.spark{display:flex;align-items:flex-end;gap:2px;height:36px}
.spark i{display:block;width:4px;background:#94a3b8;border-radius:1px}
.btn{border:1px solid var(--border);background:#fff;border-radius:8px;padding:6px 12px;font-size:12px;cursor:pointer}
.btn.primary{background:var(--blue);color:#fff;border-color:var(--blue)}
.btn:hover{filter:brightness(.97)}
.modal-bg{position:fixed;inset:0;background:rgba(15,23,42,.45);display:none;align-items:center;justify-content:center;z-index:50}
.modal-bg.show{display:flex}
.modal{background:#fff;border-radius:14px;max-width:560px;width:92%;max-height:85vh;overflow:auto;padding:18px}
.modal h3{margin:0 0 12px}
.chain{font-family:ui-monospace,Menlo,monospace;font-size:11px;line-height:1.55;max-height:360px;overflow:auto;background:#f8fafc;border:1px solid var(--border);border-radius:8px;padding:10px}
.map{position:relative;height:280px;background:linear-gradient(180deg,#e0f2fe,#f8fafc);border-radius:10px;border:1px solid var(--border);overflow:hidden}
.uav-dot{position:absolute;transform:translate(-50%,-50%);cursor:pointer;text-align:center}
.uav-dot .ring{width:14px;height:14px;border-radius:50%;margin:0 auto 2px;border:2px solid #fff;box-shadow:0 0 0 2px currentColor}
.uav-dot span{font-size:10px;font-weight:700;background:rgba(255,255,255,.9);padding:1px 4px;border-radius:4px}
.bar{height:8px;background:#e2e8f0;border-radius:4px;overflow:hidden}
.bar>i{display:block;height:100%;background:var(--blue)}
.flow{display:flex;flex-wrap:wrap;gap:8px;align-items:center;font-size:12px}
.flow .step{background:#f1f5f9;border:1px solid var(--border);border-radius:8px;padding:8px 10px;min-width:90px;text-align:center}
.flow .arrow{color:var(--muted)}
.hide{display:none}
input,select{padding:6px 8px;border:1px solid var(--border);border-radius:6px;font-size:12px}
label{font-size:12px;color:var(--muted);display:block;margin-bottom:4px}
.cfg-row{margin-bottom:12px}
</style>
</head>
<body>
<div class="shell">
  <aside class="side">
    <h1>PHI-SWARM</h1>
    <div class="sub">Command Center · evidence views</div>
    <nav class="nav" id="nav">
      <a href="#dashboard" data-v="dashboard">Dashboard</a>
      <a href="#fleet" data-v="fleet">Fleet</a>
      <a href="#topology" data-v="topology">Topology</a>
      <a href="#health" data-v="health">Health</a>
      <a href="#telemetry" data-v="telemetry">Telemetry</a>
      <a href="#faults" data-v="faults">Faults</a>
      <a href="#federation" data-v="federation">Federation</a>
      <a href="#security" data-v="security">Security</a>
      <a href="#autonomy" data-v="autonomy">Autonomy</a>
      <a href="#analytics" data-v="analytics">Analytics</a>
      <a href="#alerts" data-v="alerts">Alerts</a>
      <a href="#audit" data-v="audit">Audit</a>
      <a href="#config" data-v="config">Config</a>
    </nav>
  </aside>
  <main class="main">
    <div class="topbar">
      <h2 id="page-title">Dashboard</h2>
      <div>
        <span class="badge" id="live-badge">LIVE</span>
        <span class="muted" id="clock">—</span>
      </div>
    </div>
    <div id="view"></div>
  </main>
</div>
<div class="modal-bg" id="modal-bg" onclick="if(event.target===this)closeModal()">
  <div class="modal" id="modal-body"></div>
</div>
<script>
const S = { live: null, results: {}, nodeId: null, holdUi: false };

async function fetchLive() {
  const r = await fetch('/api/live');
  S.live = await r.json();
}
async function fetchResults() {
  const r = await fetch('/api/results');
  S.results = await r.json();
}
async function fetchAudit() {
  const r = await fetch('/api/audit');
  return r.json();
}


function statusPill(s) {
  const m = {HEALTHY:'ok', WARNING:'warn', CRITICAL:'crit', 'LINK-LOST':'grey'};
  return `<span class="pill ${m[s]||'grey'}">${s}</span>`;
}

/** Human-readable one-line summary for audit / autonomy / fault events. */
function formatEvent(e) {
  const d = e.details || {};
  const t = e.event_type || 'event';
  if (t === 'autonomy_decision') {
    const nid = d.node_id != null ? d.node_id : '?';
    const health = d.health || {};
    const conf = health.confidence != null ? Number(health.confidence).toFixed(1) : '—';
    const overall = health.overall != null ? Number(health.overall).toFixed(3) : '—';
    const fault = health.fault_label != null ? health.fault_label : (health.status || '—');
    const risk = d.risk || '—';
    const ai = d.ai_action || '—';
    const final = d.final_action || '—';
    return `UAV-${nid} · risk ${risk} · AI ${ai} → <b>${final}</b> · conf ${conf}% · health ${overall} · fault ${fault}`;
  }
  if (t === 'fault_transition') {
    const nid = d.node_id != null ? d.node_id : '?';
    const fr = d.from || d.prev || '—';
    const to = d.to || d.status || d.fault || '—';
    return `UAV-${nid} · fault ${fr} → <b>${to}</b>`;
  }
  if (t === 'integrity_gate') {
    const nid = d.node_id != null ? d.node_id : '?';
    const acc = d.accepted ? 'ACCEPTED' : 'REJECTED';
    const reasons = Array.isArray(d.reasons) ? d.reasons.join(', ') : (d.reasons || '');
    return `UAV-${nid} · ${acc}${reasons ? ' · ' + reasons : ''}`;
  }
  if (t === 'swarm_directives') {
    const dirs = d.directives || [];
    const parts = dirs.map(x => `UAV-${x.node_id}:${x.role}`).join(' · ');
    return `roles · ${parts || '—'}`;
  }
  if (t === 'encrypted_message') {
    return `msg ${d.from || '?'} → ${d.to || '?'} · ${d.result || 'ok'}`;
  }
  // fallback: compact key=value, no raw braces
  const keys = Object.keys(d).slice(0, 6);
  const bits = keys.map(k => {
    let v = d[k];
    if (v != null && typeof v === 'object') v = '…';
    return `${k}=${v}`;
  });
  return bits.length ? bits.join(' · ') : '—';
}

function formatEventLine(e, opts) {
  opts = opts || {};
  const icon = opts.icon;
  const prefix = icon ? `${icon} ` : '';
  const seq = e.seq != null ? `#${e.seq} ` : '';
  const type = e.event_type ? `<b>${e.event_type}</b> · ` : '';
  return `${prefix}${seq}${type}${formatEvent(e)}`;
}
function spark(arr) {

  if (!arr || !arr.length) return '';
  const mx = Math.max(...arr, 1e-9);
  return `<div class="spark">${arr.slice(-24).map(v => {
    const h = Math.max(2, Math.round(32 * (v / mx)));
    return `<i style="height:${h}px"></i>`;
  }).join('')}</div>`;
}
function nodesArr() {
  const n = S.live?.nodes || {};
  return Object.values(n);
}
function openModal(html) {
  document.getElementById('modal-body').innerHTML = html + '<p style="margin-top:14px"><button class="btn" onclick="closeModal()">Close</button></p>';
  document.getElementById('modal-bg').classList.add('show');
}
function closeModal(){ document.getElementById('modal-bg').classList.remove('show'); }

function nodeDetail(id) {
  const n = S.live.nodes[id];
  if (!n) return;
  const trust = (S.live.trust || {})[id] || (S.live.trust || {})[String(id)] || {};
  const dec = (S.live.decisions || []).find(d => d.node_id == id);
  const dir = (S.live.directives || []).find(d => d.node_id == id);
  openModal(`
    <h3>${n.name} · ${n.loc}</h3>
    <div class="grid grid-2">
      <div><div class="muted">Status</div>${statusPill(n.status)}</div>
      <div><div class="muted">Fault</div><b>${n.fault_type}</b></div>
      <div><div class="muted">Confidence</div><b>${n.confidence}%</b></div>
      <div><div class="muted">Trust</div><b>${trust.score != null ? Number(trust.score).toFixed(3) : '—'}</b>
        ${trust.quarantined ? ' <span class="pill crit">QUARANTINE</span>' : ''}</div>
      <div><div class="muted">Vibration</div>${n.vib} g</div>
      <div><div class="muted">Temp / Volt</div>${n.temp} °C · ${n.volt} V</div>
      <div><div class="muted">Flight / Dist</div>${n.flight_time} · ${n.distance} km</div>
      <div><div class="muted">Latency</div>${n.latency} ms</div>
    </div>
    <h4 style="margin:14px 0 6px;font-size:13px">Telemetry history (node-local sim)</h4>
    <div class="grid grid-3">
      <div class="card"><div class="muted">Vibration</div>${spark(n.vib_hist)}</div>
      <div class="card"><div class="muted">Temperature</div>${spark(n.temp_hist)}</div>
      <div class="card"><div class="muted">Voltage</div>${spark(n.volt_hist)}</div>
    </div>
    <h4 style="margin:14px 0 6px;font-size:13px">Autonomy</h4>
    <div class="muted">AI / Final: <b>${dec?.ai_action || '—'} → ${dec?.final_action || '—'}</b>
      · Risk ${dec?.risk || '—'} · Role <b>${dir?.role || '—'}</b> ${dir?.note ? '('+dir.note+')' : ''}</div>
    <p class="muted" style="margin-top:10px">Raw telemetry is not federated — only signed model updates leave the node.</p>
  `);
}

/* ---------- VIEWS ---------- */
function viewDashboard() {
  const L = S.live;
  const nodes = nodesArr();
  return `
  <div class="grid grid-4" style="margin-bottom:12px">
    <div class="card"><h3>Healthy</h3><div class="kpi" style="color:var(--green)">${L.healthy}</div></div>
    <div class="card"><h3>Warning</h3><div class="kpi" style="color:var(--amber)">${L.warning}</div></div>
    <div class="card"><h3>Critical</h3><div class="kpi" style="color:var(--red)">${L.critical}</div></div>
    <div class="card"><h3>Fed round</h3><div class="kpi sm">${L.fed_round}</div><div class="muted">acc ${L.global_accuracy}</div></div>
  </div>
  <div class="card" style="margin-bottom:12px">
    <h3>Cross-border swarm topology</h3>
    <div class="map" id="mini-map"></div>
    <div class="muted" style="margin-top:6px">Click a node for mission & health profile · locations are illustrative</div>
  </div>
  <div class="grid grid-3">
    ${nodes.map(n => `
      <div class="card row-click" onclick="nodeDetail(${n.id})">
        <div style="display:flex;justify-content:space-between"><b>${n.name}</b>${statusPill(n.status)}</div>
        <div class="muted">${n.loc} · ${n.fault_type}</div>
        <div style="margin-top:8px">${spark(n.vib_hist)}</div>
        <div class="muted" style="margin-top:6px">conf ${n.confidence}% · ${n.vib}g · ${n.temp}°C</div>
      </div>`).join('')}
  </div>`;
}

function viewFleet() {
  const nodes = nodesArr();
  const dirs = S.live.directives || [];
  const role = id => (dirs.find(d => d.node_id == id) || {}).role || '—';
  return `
  <div class="grid grid-4" style="margin-bottom:12px">
    <div class="card"><h3>Fleet size</h3><div class="kpi sm">${nodes.length}</div></div>
    <div class="card"><h3>Connected</h3><div class="kpi sm">${S.live.participants}</div></div>
    <div class="card"><h3>Avg confidence</h3><div class="kpi sm">${Math.round(nodes.reduce((a,n)=>a+n.confidence,0)/(nodes.length||1))}%</div></div>
    <div class="card"><h3>Bytes xfer</h3><div class="kpi sm">${(S.live.bytes_transferred||0).toLocaleString()}</div></div>
  </div>
  <div class="card">
    <h3>Fleet command</h3>
    <table class="table">
      <thead><tr><th>UAV</th><th>Location</th><th>Status</th><th>Fault</th><th>Conf</th><th>Role</th><th></th></tr></thead>
      <tbody>
      ${nodes.map(n => `<tr class="row-click" onclick="nodeDetail(${n.id})">
        <td><b>${n.name}</b></td><td>${n.loc}</td><td>${statusPill(n.status)}</td>
        <td>${n.fault_type}</td><td>${n.confidence}%</td><td>${role(n.id)}</td>
        <td><button class="btn" onclick="event.stopPropagation();nodeDetail(${n.id})">Profile</button></td>
      </tr>`).join('')}
      </tbody>
    </table>
  </div>`;
}

function viewTopology() {
  return `<div class="card"><h3>Swarm topology</h3><div class="map" id="topo-map" style="height:360px"></div>
  <div class="muted" style="margin-top:8px">Illustrative geo placement · click node for detail. Link transport is assumed intermittent IP; FL exchanges signed ΔW only.</div></div>`;
}

function viewHealth() {
  const nodes = nodesArr();
  const faults = S.live.faults || [];
  return `
  <div class="grid grid-2">
    <div class="card">
      <h3>Fleet health snapshot</h3>
      <table class="table"><thead><tr><th>UAV</th><th>Status</th><th>Conf</th><th>Vib</th><th>Temp</th><th>Volt</th></tr></thead>
      <tbody>${nodes.map(n=>`<tr class="row-click" onclick="nodeDetail(${n.id})"><td>${n.name}</td><td>${statusPill(n.status)}</td><td>${n.confidence}%</td><td>${n.vib}</td><td>${n.temp}</td><td>${n.volt}</td></tr>`).join('')}</tbody></table>
    </div>
    <div class="card">
      <h3>Fault distribution</h3>
      ${faults.map(([k,v,p]) => `<div style="margin-bottom:8px"><div style="display:flex;justify-content:space-between"><span>${k}</span><span>${v} (${p}%)</span></div><div class="bar"><i style="width:${p}%"></i></div></div>`).join('') || '<div class="muted">No data</div>'}
      <p class="muted" style="margin-top:12px">PHM classes from physics-hybrid engines (rotor, thermal, bearing, voltage).</p>
    </div>
  </div>`;
}

function viewTelemetry() {
  const nodes = nodesArr();
  if (!nodes.length) return '<div class="card">No nodes</div>';
  // Keep the user's choice; only default once
  if (S.nodeId == null) S.nodeId = nodes[0].id;
  let n = nodes.find(x => x.id == S.nodeId);
  if (!n) { S.nodeId = nodes[0].id; n = nodes[0]; }
  const trust = (S.live.trust || {})[n.id] || (S.live.trust || {})[String(n.id)] || {};
  const dec = (S.live.decisions || []).find(d => d.node_id == n.id);
  const dir = (S.live.directives || []).find(d => d.node_id == n.id);
  return `
  <div class="card" style="margin-bottom:12px">
    <label>UAV</label>
    <select id="uav-select"
      onfocus="S.holdUi=true"
      onmousedown="S.holdUi=true"
      onblur="setTimeout(()=>{S.holdUi=false}, 200)"
      onchange="S.nodeId=+this.value; S.holdUi=false; route()">
      ${nodes.map(x => `<option value="${x.id}" ${x.id==n.id?'selected':''}>${x.name} · ${x.loc} · ${x.status}</option>`).join('')}
    </select>
    <p class="muted" style="margin-top:8px">Node-local simulation telemetry — not a claim that raw streams are federated. Dropdown stays open until you pick; live refresh pauses while you choose.</p>
  </div>
  <div class="grid grid-4" style="margin-bottom:12px">
    <div class="card"><h3>Status</h3><div class="kpi sm">${statusPill(n.status)}</div></div>
    <div class="card"><h3>Confidence</h3><div class="kpi sm">${n.confidence}%</div></div>
    <div class="card"><h3>Fault</h3><div class="kpi sm" style="font-size:14px">${n.fault_type || '—'}</div></div>
    <div class="card"><h3>Trust</h3><div class="kpi sm">${trust.score != null ? Number(trust.score).toFixed(3) : '—'}${trust.quarantined ? ' <span class="pill crit">Q</span>' : ''}</div></div>
  </div>
  <div class="grid grid-3" style="margin-bottom:12px">
    <div class="card"><h3>Vibration</h3><div class="kpi sm" id="tel-vib">${n.vib} g</div>${spark(n.vib_hist)}</div>
    <div class="card"><h3>Temperature</h3><div class="kpi sm" id="tel-temp">${n.temp} °C</div>${spark(n.temp_hist)}</div>
    <div class="card"><h3>Voltage</h3><div class="kpi sm" id="tel-volt">${n.volt} V</div>${spark(n.volt_hist)}</div>
  </div>
  <div class="grid grid-3">
    <div class="card"><h3>Latency</h3><div class="kpi sm">${n.latency != null ? n.latency + ' ms' : '—'}</div></div>
    <div class="card"><h3>Flight / distance</h3><div class="kpi sm" style="font-size:14px">${n.flight_time || '—'} · ${n.distance != null ? n.distance + ' km' : '—'}</div></div>
    <div class="card"><h3>Autonomy</h3><div class="kpi sm" style="font-size:13px">${dec ? (dec.ai_action + ' → <b>' + dec.final_action + '</b>') : '—'}
      <div class="muted">risk ${dec?.risk || '—'} · role ${dir?.role || '—'}</div></div></div>
  </div>`;
}

function viewFaults() {
  const events = (S.live.security?.recent_events || []).filter(e => e.event_type === 'fault_transition' || e.event_type === 'autonomy_decision');
  const nodes = nodesArr().filter(n => n.status !== 'HEALTHY');
  return `
  <div class="card" style="margin-bottom:12px">
    <h3>Active non-healthy nodes</h3>
    <table class="table"><thead><tr><th>UAV</th><th>Status</th><th>Fault</th><th>Conf</th></tr></thead>
    <tbody>${nodes.map(n=>`<tr class="row-click" onclick="nodeDetail(${n.id})"><td>${n.name}</td><td>${statusPill(n.status)}</td><td>${n.fault_type}</td><td>${n.confidence}%</td></tr>`).join('') || '<tr><td colspan=4 class="muted">All healthy</td></tr>'}</tbody></table>
  </div>
  <div class="card">
    <h3>Recent fault / autonomy events</h3>
    <div class="chain">${events.slice().reverse().map(e => formatEventLine(e)).join('<br>') || '—'}</div>
  </div>`;
}

function viewFederation() {
  const L = S.live;
  const im = S.results.integrity_metrics || {};
  return `
  <div class="grid grid-4" style="margin-bottom:12px">
    <div class="card"><h3>Round</h3><div class="kpi sm">${L.fed_round}</div></div>
    <div class="card"><h3>Global acc</h3><div class="kpi sm">${L.global_accuracy}</div></div>
    <div class="card"><h3>Participants</h3><div class="kpi sm">${L.participants}</div></div>
    <div class="card"><h3>Model</h3><div class="kpi sm" style="font-size:14px">${L.global_model}</div><div class="muted">${L.model_parameters?.toLocaleString?.() || L.model_parameters} params</div></div>
  </div>
  <div class="grid grid-2">
    <div class="card">
      <h3>Paper baselines (integrity experiment)</h3>
      <table class="table">
        <tr><td>Centralized</td><td><b>${im.centralized_accuracy ?? im.centralized ?? '—'}</b></td></tr>
        <tr><td>Isolated mean</td><td><b>${im.isolated_mean_accuracy ?? im.isolated_mean ?? '—'}</b></td></tr>
        <tr><td>Federated</td><td><b>${im.federated_accuracy ?? im.zerotwin_accuracy ?? '—'}</b></td></tr>
      </table>
      <p class="muted">From zerotwin/results/integrity_metrics.json — re-run experiment to refresh.</p>
    </div>
    <div class="card">
      <h3>Live integrity counters</h3>
      <div>Accepted: <b>${L.security?.accepted_updates ?? 0}</b></div>
      <div>Rejected: <b>${L.security?.rejected_updates ?? 0}</b></div>
      <div>Bytes: <b>${(L.bytes_transferred||0).toLocaleString()}</b></div>
      <div>Last agg: <b>${L.last_agg}</b></div>
      <p class="muted" style="margin-top:8px">Cross-silo traffic = signed weight deltas only.</p>
    </div>
  </div>`;
}

function viewSecurity() {
  const L = S.live;
  const sec = L.security || {};
  const trust = L.trust || {};
  const adv = S.results.adversarial_validation || {};
  return `
  <div class="grid grid-3" style="margin-bottom:12px">
    <div class="card"><h3>Accepted</h3><div class="kpi sm">${sec.accepted_updates||0}</div></div>
    <div class="card"><h3>Rejected</h3><div class="kpi sm">${sec.rejected_updates||0}</div></div>
    <div class="card"><h3>Replays blocked</h3><div class="kpi sm">${sec.replays_blocked||0}</div></div>
  </div>
  <div class="grid grid-2">
    <div class="card">
      <h3>Security fabric</h3>
      <div>✓ Cryptographic verification (Ed25519)</div>
      <div>✓ Replay / stale-round protection</div>
      <div>✓ Update-norm anomaly detection</div>
      <div>✓ Physics-consistency scoring</div>
      <div>✓ Trust-modulated aggregation</div>
      <div>✓ Hash-chained audit ledger</div>
      <p class="muted" style="margin-top:8px">Authentication ≠ behavioral trust.</p>
    </div>
    <div class="card">
      <h3>Trust graph</h3>
      <table class="table"><thead><tr><th>Node</th><th>Score</th><th>Accepts</th><th>Rejects</th><th>Q</th></tr></thead>
      <tbody>${Object.entries(trust).map(([id,t]) => `<tr><td>UAV-${id}</td><td>${Number(t.score).toFixed(3)}</td><td>${t.accepts}</td><td>${t.rejects}</td><td>${t.quarantined?'YES':'no'}</td></tr>`).join('') || '<tr><td colspan=5 class="muted">Warming up…</td></tr>'}</tbody></table>
    </div>
  </div>
  <div class="card" style="margin-top:12px">
    <h3>Adversarial suite (offline validation)</h3>
    <div>all_pass: <b>${adv.all_pass === true ? 'TRUE' : adv.all_pass === false ? 'FALSE' : '—'}</b></div>
    <div class="chain" style="margin-top:8px">${(adv.tests||[]).map(t => {
      const r = t.reasons || t.replay_reasons || t.detail || '';
      const extra = Array.isArray(r) ? r.join(', ') : (typeof r === 'object' ? '' : String(r));
      return `${t.pass?'PASS':'FAIL'} · ${t.test}${extra ? ' · ' + extra : ''}`;
    }).join('<br>') || 'Run scripts/run_adversarial_validation.py'}</div>
  </div>`;
}

function viewAutonomy() {
  const decs = S.live.decisions || [];
  const dirs = S.live.directives || [];
  const auto = S.results.autonomy_validation || {};
  return `
  <div class="card" style="margin-bottom:12px">
    <h3>Decision pipeline</h3>
    <div class="flow">
      <div class="step">Health</div><span class="arrow">→</span>
      <div class="step">Risk</div><span class="arrow">→</span>
      <div class="step">AI recommend</div><span class="arrow">→</span>
      <div class="step">Safety governor</div><span class="arrow">→</span>
      <div class="step">Final action</div><span class="arrow">→</span>
      <div class="step">Swarm role</div>
    </div>
    <p class="muted" style="margin-top:8px">AI proposes; safety constraints dispose.</p>
  </div>
  <div class="card" style="margin-bottom:12px">
    <h3>Live decisions</h3>
    <table class="table"><thead><tr><th>UAV</th><th>Risk</th><th>AI</th><th>Final</th><th>Role</th></tr></thead>
    <tbody>${decs.map(d => {
      const role = (dirs.find(x => x.node_id == d.node_id)||{}).role || '—';
      return `<tr><td>UAV-${d.node_id}</td><td>${d.risk}</td><td>${d.ai_action}</td><td><b>${d.final_action}</b></td><td>${role}</td></tr>`;
    }).join('') || '<tr><td colspan=5 class="muted">Awaiting FL rounds…</td></tr>'}</tbody></table>
  </div>
  <div class="card">
    <h3>Autonomy validation suite</h3>
    <div>all_pass: <b>${auto.all_pass === true ? 'TRUE' : '—'}</b></div>
    <div class="chain">${(auto.tests||[]).map(t => `${t.pass?'PASS':'FAIL'} ${t.test}`).join('<br>') || 'Run scripts/run_autonomy_validation.py'}</div>
  </div>`;
}

function viewAnalytics() {
  const im = S.results.integrity_metrics || {};
  const seed = S.results.seed_sweep || {};
  const res = S.results.resilience_results || {};
  const edge = S.results.edge_benchmark || {};
  const camp = S.results.campaign_results || {};
  const rows = camp.rows || [];
  const per = seed.per_seed || [];
  const summary = seed.summary || {};

  const num = (v, d=3) => (v == null || v === '' || Number.isNaN(Number(v))) ? '—' : Number(v).toFixed(d);
  const pct = (v) => (v == null || Number.isNaN(Number(v))) ? '—' : (Number(v) * 100).toFixed(1) + '%';

  // Integrity headline numbers
  const cent = im.accuracy_centralized ?? im.centralized;
  const isol = im.accuracy_isolated_mean ?? im.isolated_mean;
  const fed  = im.accuracy_federated ?? im.zerotwin_accuracy;
  const gain = im.federation_gain_over_isolated != null ? im.federation_gain_over_isolated
             : (fed != null && isol != null ? Number(fed) - Number(isol) : null);
  const gap  = im.gap_to_centralized != null ? im.gap_to_centralized
             : (cent != null && fed != null ? Number(cent) - Number(fed) : null);
  const gate = im.integrity_gate || {};
  const hist = (im.history && im.history.global_acc) || [];

  // Seed-sweep aggregates
  let fedMean = summary.federated_mean, fedStd = summary.federated_std;
  let isolMean = summary.isolated_mean, centMean = summary.centralized_mean;
  if (per.length && fedMean == null) {
    const f = per.map(p => p.accuracy_federated).filter(x => x != null);
    const i = per.map(p => p.accuracy_isolated_mean).filter(x => x != null);
    const c = per.map(p => p.accuracy_centralized).filter(x => x != null);
    const mean = a => a.length ? a.reduce((s,x)=>s+x,0)/a.length : null;
    const std = a => { if (a.length < 2) return null; const m = mean(a); return Math.sqrt(a.reduce((s,x)=>s+(x-m)*(x-m),0)/(a.length-1)); };
    fedMean = mean(f); fedStd = std(f); isolMean = mean(i); centMean = mean(c);
  }
  const worse = per.filter(p => p.accuracy_federated != null && p.accuracy_isolated_mean != null
    && p.accuracy_federated < p.accuracy_isolated_mean - 0.05).length;

  // Campaign highlights
  const bySc = Object.fromEntries(rows.map(r => [r.scenario, r]));
  const hl = camp.highlights || {};
  const baseAtk = hl.baseline_attack_acceptance_rate ?? bySc.attack_baseline?.attack_acceptance_rate;
  const phiAtk  = hl.phi_attack_acceptance_rate ?? bySc.attack_phi?.attack_acceptance_rate;
  const phiReduces = hl.phi_reduces_attack_acceptance ?? (baseAtk != null && phiAtk != null && Number(phiAtk) < Number(baseAtk));

  // Resilience curve
  const curve = res.curve || [];

  return `
  <div class="grid grid-2" style="margin-bottom:12px">
    <div class="card">
      <h3>Integrity experiment</h3>
      <table class="table">
        <tr><td>Centralized</td><td><b>${pct(cent)}</b></td></tr>
        <tr><td>Isolated mean</td><td><b>${pct(isol)}</b></td></tr>
        <tr><td>Federated (ZeroTwin)</td><td><b>${pct(fed)}</b></td></tr>
        <tr><td>Gain over isolated</td><td><b>${gain == null ? '—' : (gain >= 0 ? '+' : '') + num(gain, 3)}</b></td></tr>
        <tr><td>Gap to centralized</td><td><b>${num(gap, 3)}</b></td></tr>
        <tr><td>Gate accepted / rejected</td><td><b>${gate.accepted ?? '—'} / ${gate.rejected ?? '—'}</b></td></tr>
        <tr><td>Attack rate</td><td>${im.attack_rate ?? 0}</td></tr>
        <tr><td>Param bytes moved</td><td>${(im.approx_param_bytes_total||0).toLocaleString?.() || im.approx_param_bytes_total || '—'}</td></tr>
      </table>
      ${hist.length ? `<p class="muted" style="margin-top:8px">Global acc by round: ${hist.map(a => num(a,2)).join(' → ')}</p>` : ''}
      <p class="muted">${im.claim_note || 'Federated path exchanges signed weight deltas only.'}</p>
    </div>
    <div class="card">
      <h3>Campaign highlights</h3>
      <table class="table">
        <tr><td>Baseline attack accept rate</td><td><b>${baseAtk == null ? '—' : pct(baseAtk)}</b></td></tr>
        <tr><td>PHI-SWARM attack accept rate</td><td><b>${phiAtk == null ? '—' : pct(phiAtk)}</b></td></tr>
        <tr><td>PHI reduces attack acceptance</td><td><b>${phiReduces === true ? 'YES' : phiReduces === false ? 'NO' : '—'}</b></td></tr>
        <tr><td>Failure → escort assigned</td><td>${hl.failure_escort_assigned === true ? 'YES' : hl.failure_escort_assigned === false ? 'NO' : (bySc.failure_phi ? 'see rows' : '—')}</td></tr>
        <tr><td>Failure → LAND/RTB</td><td>${hl.failure_land_or_rtb === true ? 'YES' : hl.failure_land_or_rtb === false ? 'NO' : '—'}</td></tr>
      </table>
      ${rows.length ? `
      <table class="table" style="margin-top:10px">
        <thead><tr><th>Scenario</th><th>Acc</th><th>Accept</th><th>Reject</th><th>Atk rate</th></tr></thead>
        <tbody>${rows.map(r => `<tr>
          <td>${r.scenario}</td>
          <td>${pct(r.global_accuracy)}</td>
          <td>${r.accepted ?? '—'}</td>
          <td>${r.rejected ?? '—'}</td>
          <td>${r.attack_acceptance_rate == null ? '—' : pct(r.attack_acceptance_rate)}</td>
        </tr>`).join('')}</tbody>
      </table>` : '<p class="muted">Run scripts/run_campaign.py to populate.</p>'}
    </div>
  </div>
  <div class="grid grid-2">
    <div class="card">
      <h3>Seed sweep</h3>
      <table class="table">
        <tr><td>Seeds</td><td><b>${seed.n_seeds ?? per.length ?? '—'}</b></td></tr>
        <tr><td>Federated mean ± std</td><td><b>${fedMean == null ? '—' : num(fedMean,3)}${fedStd != null ? ' ± ' + num(fedStd,3) : ''}</b></td></tr>
        <tr><td>Isolated mean</td><td><b>${num(isolMean,3)}</b></td></tr>
        <tr><td>Centralized mean</td><td><b>${num(centMean,3)}</b></td></tr>
        <tr><td>Seeds where fed &lt; isol − 0.05</td><td><b>${per.length ? worse + ' / ' + per.length : '—'}</b></td></tr>
        <tr><td>Elapsed</td><td>${seed.elapsed_seconds != null ? Number(seed.elapsed_seconds).toFixed(0) + 's' : '—'}</td></tr>
        <tr><td>Attack rate</td><td>${seed.config?.attack_rate ?? '—'}</td></tr>
      </table>
      <p class="muted" style="margin-top:8px">Under attack the win is not uniform — report mean ± std, not only seed 42.</p>
    </div>
    <div class="card">
      <h3>Resilience / Edge</h3>
      ${curve.length ? `
      <table class="table">
        <thead><tr><th>Link-loss rounds</th><th>Final accuracy</th></tr></thead>
        <tbody>${curve.map(c => `<tr><td>${c.link_loss_rounds}</td><td><b>${pct(c.final_accuracy)}</b></td></tr>`).join('')}</tbody>
      </table>` : '<p class="muted">Run scripts/run_link_loss_sweep.py</p>'}
      <div style="margin-top:12px">
        <div class="muted">Edge model</div>
        <div>${edge.model?.parameters != null ? Number(edge.model.parameters).toLocaleString() + ' params' : '—'} · ${edge.model?.saved_state_dict_MB != null ? num(edge.model.saved_state_dict_MB,2) + ' MB' : ''}</div>
        <div class="muted" style="margin-top:6px">Inference (batch 1)</div>
        <div>${edge.inference?.[0] ? num(edge.inference[0].mean_ms,2) + ' ms mean · ' + num(edge.inference[0].throughput_windows_per_sec,0) + ' win/s' : '—'}</div>
        <p class="muted" style="margin-top:8px">${edge.hardware?.note || 'Laptop CPU benchmark — not Jetson/RPi class.'}</p>
      </div>
    </div>
  </div>
  <p class="muted" style="margin-top:8px">Refresh after re-running experiments. Export CSV/PNG: <code>python scripts/export_paper_artifacts.py</code></p>`;
}

function viewAlerts() {
  const ev = (S.live.security?.recent_events || []).slice().reverse();
  return `<div class="card"><h3>Operational event stream</h3>
  <div class="chain">${ev.map(e => {
    const icon = (e.event_type||'').includes('reject') || (e.event_type||'').includes('fault') ? '🟠' :
      (e.event_type||'').includes('eavesdrop') || (e.event_type||'').includes('tamper') ? '🔴' : '🟢';
    return formatEventLine(e, {icon});
  }).join('<br>') || '—'}</div></div>`;
}

async function viewAudit() {
  const a = await fetchAudit();
  return `
  <div class="grid grid-3" style="margin-bottom:12px">
    <div class="card"><h3>Chain</h3><div class="kpi sm">${a.verified ? 'VERIFIED' : 'FAIL'}</div></div>
    <div class="card"><h3>Entries</h3><div class="kpi sm">${a.chain_length}</div></div>
    <div class="card"><h3>First bad</h3><div class="kpi sm">${a.first_bad_seq ?? 'NONE'}</div></div>
  </div>
  <div class="card"><h3>Audit ledger (recent)</h3>
  <div class="chain">${(a.security?.recent_events||[]).slice().reverse().map(e =>
    formatEventLine(e)
  ).join('<br>') || '—'}</div>
  <p class="muted" style="margin-top:8px">Hash-chained JSONL · no private keys or raw secrets in entries.</p>
  </div>`;
}

function viewConfig() {
  return `
  <div class="card" style="max-width:480px">
    <h3>Simulation config (display)</h3>
    <p class="muted">Engine started with defaults. Restart process to change seed/nodes. Attack rate is internal to PHISwarmEngine.</p>
    <div class="cfg-row"><label>Nodes</label><input value="5" disabled/></div>
    <div class="cfg-row"><label>Round interval (s)</label><input value="4" disabled/></div>
    <div class="cfg-row"><label>Samples / node</label><input value="300" disabled/></div>
    <div class="cfg-row"><label>Seed</label><input value="42" disabled/></div>
    <button class="btn primary" onclick="location.reload()">Reload UI</button>
    <p class="muted" style="margin-top:12px">For scenario campaigns use CLI: run_campaign.py, run_adversarial_validation.py, run_phi_swarm.py</p>
  </div>`;
}

const VIEWS = {
  dashboard: viewDashboard, fleet: viewFleet, topology: viewTopology, health: viewHealth,
  telemetry: viewTelemetry, faults: viewFaults, federation: viewFederation, security: viewSecurity,
  autonomy: viewAutonomy, analytics: viewAnalytics, alerts: viewAlerts, audit: viewAudit, config: viewConfig,
};
const TITLES = {
  dashboard:'Dashboard', fleet:'Fleet', topology:'Topology', health:'Health', telemetry:'Telemetry',
  faults:'Faults', federation:'Federation', security:'Security', autonomy:'Autonomy',
  analytics:'Analytics', alerts:'Alerts', audit:'Audit Ledger', config:'Config',
};

function paintMap(elId) {
  const el = document.getElementById(elId);
  if (!el || !S.live) return;
  const nodes = nodesArr();
  // simple lat/lon project
  const lats = nodes.map(n => n.lat), lons = nodes.map(n => n.lon);
  const minLa = Math.min(...lats)-5, maxLa = Math.max(...lats)+5;
  const minLo = Math.min(...lons)-5, maxLo = Math.max(...lons)+5;
  el.innerHTML = nodes.map(n => {
    const x = ((n.lon - minLo) / (maxLo - minLo)) * 100;
    const y = (1 - (n.lat - minLa) / (maxLa - minLa)) * 100;
    const col = n.status==='CRITICAL'?'#dc2626':n.status==='WARNING'?'#d97706':n.status==='LINK-LOST'?'#64748b':'#16a34a';
    return `<div class="uav-dot" style="left:${x}%;top:${y}%;color:${col}" onclick="nodeDetail(${n.id})">
      <div class="ring" style="background:${col}"></div><span>${n.name}</span></div>`;
  }).join('');
}

async function route() {
  const name = (location.hash || '#dashboard').slice(1) || 'dashboard';
  document.querySelectorAll('.nav a').forEach(a => a.classList.toggle('active', a.dataset.v === name));
  document.getElementById('page-title').textContent = TITLES[name] || name;
  const fn = VIEWS[name] || viewDashboard;
  const html = fn.constructor.name === 'AsyncFunction' ? await fn() : fn();
  document.getElementById('view').innerHTML = html;
  if (name === 'dashboard') paintMap('mini-map');
  if (name === 'topology') paintMap('topo-map');
  if (S.live) {
    document.getElementById('clock').textContent = S.live.clock || '';
    const crit = S.live.critical > 0;
    const badge = document.getElementById('live-badge');
    badge.textContent = crit ? 'LIVE · CRITICAL' : 'LIVE';
    badge.className = 'badge' + (crit ? ' crit' : '');
  }
}

async function tick() {
  try {
    await fetchLive();
    const ae = document.activeElement;
    const tag = ae && ae.tagName;
    const interacting = S.holdUi
      || tag === 'SELECT' || tag === 'INPUT' || tag === 'TEXTAREA'
      || (document.getElementById('modal-bg') && document.getElementById('modal-bg').classList.contains('show'));
    if (interacting) {
      // Keep dropdown/modal usable — only refresh clock/badge
      if (S.live) {
        const clock = document.getElementById('clock');
        if (clock) clock.textContent = S.live.clock || '';
        const badge = document.getElementById('live-badge');
        if (badge) {
          const crit = S.live.critical > 0;
          badge.textContent = crit ? 'LIVE · CRITICAL' : 'LIVE';
          badge.className = 'badge' + (crit ? ' crit' : '');
        }
      }
      return;
    }
    await route();
  } catch (e) { console.warn(e); }
}

window.addEventListener('hashchange', () => route());
window.addEventListener('load', async () => {
  await fetchResults();
  engineStart();
  await tick();
  setInterval(tick, 1500);
});
function engineStart(){ /* server starts engine */ }
</script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/api/live")
def api_live():
    state = engine.get_state()
    return jsonify(_enrich(state))


@app.route("/api/audit")
def api_audit():
    state = engine.get_state()
    v = engine.audit_verify()
    recent = state.get("security", {}).get("recent_events", [])
    return jsonify({
        "verified": v.get("verified"),
        "first_bad_seq": v.get("first_bad_seq"),
        "path": v.get("path"),
        "chain_length": len(recent) if recent else engine.ledger._seq,
        "security": state.get("security", {}),
    })


@app.route("/api/results")
def api_results():
    return jsonify({
        "integrity_metrics": _load_json("integrity_metrics.json"),
        "adversarial_validation": _load_json("adversarial_validation.json"),
        "autonomy_validation": _load_json("autonomy_validation.json"),
        "campaign_results": _load_json("campaign_results.json"),
        "seed_sweep": _load_json("seed_sweep.json"),
        "resilience_results": _load_json("resilience_results.json"),
        "edge_benchmark": _load_json("edge_benchmark.json"),
        "phi_swarm_summary": _load_json("phi_swarm_summary.json"),
    })


def main():
    print("PHI-SWARM Command Center → http://127.0.0.1:5000")
    print("Starting live engine in background…")
    engine.start()
    try:
        app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
    finally:
        engine.stop()


if __name__ == "__main__":
    main()
