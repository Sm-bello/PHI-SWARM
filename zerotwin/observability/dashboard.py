"""ZeroTwin Command Center — visual face of the integrity testbed.

Scientific claims live in docs/ and scripts/run_integrity_experiment.py.
This dashboard is for qualitative inspection of the swarm twin narrative.
"""
from flask import Flask, render_template_string, jsonify
import math
import random
import time
from datetime import datetime, timezone
from pathlib import Path
import logging

logging.getLogger("werkzeug").setLevel(logging.ERROR)

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Simulated live state (self-contained so the UI works without full FL stack)
# ---------------------------------------------------------------------------

NODE_META = {
    1: {"name": "UAV-1", "loc": "Lagos, Nigeria",   "lat": 6.52,  "lon": 3.38,  "base_status": "HEALTHY",  "base_conf": 92},
    2: {"name": "UAV-2", "loc": "Beijing, China",   "lat": 39.90, "lon": 116.4, "base_status": "WARNING",  "base_conf": 76},
    3: {"name": "UAV-3", "loc": "Shanghai, China",  "lat": 31.23, "lon": 121.5, "base_status": "CRITICAL", "base_conf": 48},
    4: {"name": "UAV-4", "loc": "Tokyo, Japan",     "lat": 35.68, "lon": 139.7, "base_status": "WARNING",  "base_conf": 68},
    5: {"name": "UAV-5", "loc": "Seoul, South Korea","lat": 37.57, "lon": 126.9, "base_status": "HEALTHY",  "base_conf": 89},
}

FAULT_TYPES = [
    ("Rotor Imbalance", 6, 26.1),
    ("Thermal Runaway", 5, 21.7),
    ("Bearing Faults", 4, 17.4),
    ("Health Sag", 5, 21.7),
    ("Voltage Sag", 3, 13.0),
]

# Rolling history buffers for sparklines (last ~40 points)
history = {i: {"vib": [], "temp": [], "volt": []} for i in range(1, 6)}
start_ts = time.time()


def _jitter(base, scale):
    return round(base + random.gauss(0, scale), 3)


def generate_live_state():
    """Produce a realistic snapshot that matches the mockup numbers."""
    now = time.time()
    elapsed = now - start_ts
    nodes = {}
    critical = warning = healthy = 0

    for nid, meta in NODE_META.items():
        status = meta["base_status"]
        conf = meta["base_conf"] + random.randint(-2, 2)
        conf = max(30, min(99, conf))

        if status == "HEALTHY":
            vib_b, temp_b, volt_b = 0.032, 34.1, 15.62
            healthy += 1
            accent = "#16a34a"
            pulse = "green"
        elif status == "WARNING":
            vib_b, temp_b, volt_b = (0.068 if nid == 2 else 0.071), (41.7 if nid == 2 else 43.2), (15.21 if nid == 2 else 15.33)
            warning += 1
            accent = "#d97706"
            pulse = "amber"
        else:  # CRITICAL
            vib_b, temp_b, volt_b = 0.126, 58.3, 14.18
            critical += 1
            accent = "#dc2626"
            pulse = "red"

        vib = _jitter(vib_b, 0.004)
        temp = _jitter(temp_b, 0.25)
        volt = _jitter(volt_b, 0.04)

        # Keep rolling history
        for key, val in (("vib", vib), ("temp", temp), ("volt", volt)):
            history[nid][key].append(val)
            if len(history[nid][key]) > 40:
                history[nid][key].pop(0)

        # Flight time / distance (slowly incrementing)
        ft_sec = int(elapsed * (0.9 + nid * 0.05)) + {1: 854, 2: 7757, 3: 6475, 4: 7421, 5: 8209}[nid]
        h, rem = divmod(ft_sec, 3600)
        m, s = divmod(rem, 60)
        flight_time = f"{h:02d}:{m:02d}:{s:02d}"
        distance = round(100 + nid * 8 + elapsed * 0.015, 1)

        # Latency shown on map
        latency = {1: 82, 2: 128, 3: 156, 4: 98, 5: 74}[nid] + random.randint(-4, 4)

        nodes[nid] = {
            "id": nid,
            "name": meta["name"],
            "loc": meta["loc"],
            "status": status,
            "confidence": conf,
            "accent": accent,
            "pulse": pulse,
            "vib": vib,
            "temp": round(temp, 1),
            "volt": round(volt, 2),
            "flight_time": flight_time,
            "distance": distance,
            "latency": latency,
            "vib_hist": history[nid]["vib"][-30:],
            "temp_hist": history[nid]["temp"][-30:],
            "volt_hist": history[nid]["volt"][-30:],
        }

    # Federation counters
    fed_round = 127 + int(elapsed // 45)
    last_agg = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    avg_latency = 96 + random.randint(-6, 6)
    data_rate = round(1.24 + random.uniform(-0.05, 0.05), 2)

    return {
        "nodes": nodes,
        "critical": critical,
        "warning": warning,
        "healthy": healthy,
        "total_faults": 23,
        "faults": FAULT_TYPES,
        "fed_round": fed_round,
        "global_model": "v2.7.3",
        "participants": "5 / 5",
        "last_agg": last_agg,
        "avg_latency": avg_latency,
        "data_rate": data_rate,
        "system_time": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
        "system_date": "May 22, 2025",
    }


# ---------------------------------------------------------------------------
# HTML — high-fidelity recreation of the mockup
# ---------------------------------------------------------------------------

HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ZeroTwin Command Center</title>
<style>
  :root {
    --bg: #f1f5f9;
    --card: #ffffff;
    --border: #e2e8f0;
    --text: #0f172a;
    --muted: #64748b;
    --blue: #0284c7;
    --green: #16a34a;
    --amber: #d97706;
    --red: #dc2626;
    --sidebar-w: 200px;
  }
  * { margin:0; padding:0; box-sizing:border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
    background: var(--bg);
    color: var(--text);
    height: 100vh;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }

  /* ===== TOP NAV ===== */
  .topnav {
    height: 52px;
    background: var(--card);
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    padding: 0 20px;
    gap: 28px;
    flex-shrink: 0;
    z-index: 50;
  }
  .logo {
    display: flex;
    align-items: center;
    gap: 10px;
    font-weight: 800;
    font-size: 15px;
    letter-spacing: 0.3px;
    color: var(--text);
  }
  .logo-icon {
    width: 28px; height: 28px;
    background: linear-gradient(135deg, #0ea5e9, #0284c7);
    border-radius: 8px;
    display: flex; align-items: center; justify-content: center;
    color: white; font-size: 14px;
  }
  .nav-links { display: flex; gap: 4px; }
  .nav-links a {
    text-decoration: none;
    color: var(--muted);
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.4px;
    padding: 6px 12px;
    border-radius: 6px;
    transition: all .15s;
  }
  .nav-links a.active, .nav-links a:hover {
    color: var(--blue);
    background: #e0f2fe;
  }
  .top-right {
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: 14px;
  }
  .sys-online {
    display: flex; align-items: center; gap: 6px;
    background: #dcfce7; color: var(--green);
    font-size: 11px; font-weight: 700;
    padding: 5px 12px; border-radius: 999px;
  }
  .sys-online .dot { width:8px; height:8px; background:var(--green); border-radius:50%; }
  .icon-btn {
    width: 32px; height: 32px; border-radius: 8px;
    border: 1px solid var(--border); background: var(--card);
    display: flex; align-items: center; justify-content: center;
    cursor: pointer; position: relative; color: var(--muted);
  }
  .badge-notif {
    position: absolute; top: -4px; right: -4px;
    background: var(--red); color: white;
    font-size: 9px; font-weight: 700;
    width: 16px; height: 16px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
  }
  .clock {
    font-size: 12px; color: var(--muted); font-weight: 500;
    text-align: right; line-height: 1.3;
  }
  .clock strong { color: var(--text); display:block; }

  /* ===== LAYOUT ===== */
  .main-wrap {
    display: flex;
    flex: 1;
    overflow: hidden;
  }

  /* ===== SIDEBAR ===== */
  .sidebar {
    width: var(--sidebar-w);
    background: var(--card);
    border-right: 1px solid var(--border);
    padding: 16px 12px;
    display: flex;
    flex-direction: column;
    flex-shrink: 0;
  }
  .side-item {
    display: flex; align-items: center; gap: 10px;
    padding: 10px 12px;
    border-radius: 8px;
    font-size: 13px; font-weight: 600;
    color: var(--muted);
    cursor: pointer;
    transition: all .15s;
    margin-bottom: 2px;
  }
  .side-item:hover { background: #f1f5f9; color: var(--text); }
  .side-item.active {
    background: #e0f2fe;
    color: var(--blue);
  }
  .side-item svg { width: 16px; height: 16px; flex-shrink: 0; }
  .side-bottom {
    margin-top: auto;
    padding-top: 16px;
    border-top: 1px solid var(--border);
  }
  .lab-logo {
    display: flex; align-items: center; gap: 8px;
    font-size: 11px; color: var(--muted);
  }
  .lab-logo strong { color: var(--text); display:block; font-size: 12px; }
  .version { font-size: 10px; color: #94a3b8; margin-top: 6px; }

  /* ===== CONTENT ===== */
  .content {
    flex: 1;
    overflow-y: auto;
    padding: 18px 20px 10px;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  /* ===== RADAR / MAP ===== */
  .radar-card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 16px 20px 12px;
    position: relative;
    box-shadow: 0 1px 3px rgba(0,0,0,.04);
  }
  .radar-header {
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 8px;
  }
  .radar-title { font-size: 13px; font-weight: 700; letter-spacing: .3px; }
  .radar-sub { font-size: 11px; color: var(--muted); margin-top: 2px; }
  .legend {
    display: flex; gap: 14px; font-size: 11px; font-weight: 600;
  }
  .legend span { display:flex; align-items:center; gap:5px; }
  .legend .d { width:8px; height:8px; border-radius:50%; }
  .map-area {
    position: relative;
    height: 280px;
    background: linear-gradient(180deg, #e0f2fe 0%, #f0f9ff 40%, #f8fafc 100%);
    border-radius: 10px;
    overflow: hidden;
    border: 1px solid #e0f2fe;
  }
  /* Stylized world map (dotted continents approximation via CSS) */
  .map-bg {
    position: absolute; inset: 0;
    background-image:
      radial-gradient(circle at 18% 48%, #bae6fd 1.5px, transparent 1.6px),
      radial-gradient(circle at 22% 52%, #bae6fd 1.2px, transparent 1.3px),
      radial-gradient(circle at 48% 38%, #bae6fd 1.5px, transparent 1.6px),
      radial-gradient(circle at 52% 42%, #bae6fd 1.3px, transparent 1.4px),
      radial-gradient(circle at 55% 48%, #bae6fd 1.4px, transparent 1.5px),
      radial-gradient(circle at 72% 40%, #bae6fd 1.5px, transparent 1.6px),
      radial-gradient(circle at 78% 45%, #bae6fd 1.3px, transparent 1.4px),
      radial-gradient(circle at 82% 50%, #bae6fd 1.2px, transparent 1.3px);
    background-size: 100% 100%;
    opacity: 0.7;
  }
  .map-grid {
    position: absolute; inset: 0;
    background-image:
      linear-gradient(rgba(148,163,184,.12) 1px, transparent 1px),
      linear-gradient(90deg, rgba(148,163,184,.12) 1px, transparent 1px);
    background-size: 40px 40px;
  }
  /* Connection lines (SVG overlay) */
  .conn-svg {
    position: absolute; inset: 0; width: 100%; height: 100%;
    pointer-events: none; z-index: 2;
  }
  /* UAV nodes on map */
  .uav-node {
    position: absolute;
    transform: translate(-50%, -50%);
    z-index: 5;
    display: flex; flex-direction: column; align-items: center;
    cursor: default;
  }
  .uav-ring {
    width: 44px; height: 44px;
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    position: relative;
    color: white; font-size: 18px;
  }
  .uav-ring::before {
    content: '';
    position: absolute; inset: -6px;
    border-radius: 50%;
    border: 2px solid currentColor;
    opacity: 0.35;
  }
  .uav-ring::after {
    content: '';
    position: absolute; inset: -14px;
    border-radius: 50%;
    border: 1.5px solid currentColor;
    opacity: 0.18;
    animation: pulse-ring 2s ease-out infinite;
  }
  @keyframes pulse-ring {
    0% { transform: scale(0.85); opacity: 0.25; }
    70% { transform: scale(1.15); opacity: 0; }
    100% { transform: scale(1.15); opacity: 0; }
  }
  .ring-green { background: var(--green); color: var(--green); }
  .ring-amber { background: var(--amber); color: var(--amber); }
  .ring-red   { background: var(--red);   color: var(--red); }
  .uav-ring svg { color: white; width: 20px; height: 20px; }
  .uav-label {
    margin-top: 8px;
    background: white;
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 5px 10px;
    box-shadow: 0 2px 6px rgba(0,0,0,.06);
    text-align: center;
    min-width: 110px;
  }
  .uav-label .name { font-size: 12px; font-weight: 700; }
  .uav-label .loc  { font-size: 10px; color: var(--muted); }
  .uav-label .lat  { font-size: 10px; font-weight: 600; margin-top: 2px; }
  .lat-green { color: var(--green); }
  .lat-amber { color: var(--amber); }
  .lat-red   { color: var(--red); }

  /* zoom controls */
  .map-controls {
    position: absolute; bottom: 12px; left: 12px;
    display: flex; flex-direction: column; gap: 4px; z-index: 10;
  }
  .map-controls button {
    width: 28px; height: 28px; border-radius: 6px;
    border: 1px solid var(--border); background: white;
    font-size: 14px; cursor: pointer; color: var(--muted);
  }
  .time-range {
    position: absolute; bottom: 12px; right: 12px;
    display: flex; gap: 4px; z-index: 10;
  }
  .time-range button {
    padding: 4px 10px; border-radius: 6px;
    border: 1px solid var(--border); background: white;
    font-size: 11px; font-weight: 600; color: var(--muted); cursor: pointer;
  }
  .time-range button.active { background: #e0f2fe; color: var(--blue); border-color: #bae6fd; }

  /* ===== BOTTOM GRID ===== */
  .bottom-grid {
    display: grid;
    grid-template-columns: 1fr 280px;
    gap: 16px;
    flex: 1;
    min-height: 0;
  }

  /* Per-node cards */
  .nodes-row {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 12px;
  }
  .section-title {
    font-size: 12px; font-weight: 700; letter-spacing: .4px;
    color: var(--muted); text-transform: uppercase;
    margin-bottom: 10px;
  }
  .node-card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 12px;
    box-shadow: 0 1px 2px rgba(0,0,0,.03);
    display: flex; flex-direction: column;
  }
  .nc-head {
    display: flex; justify-content: space-between; align-items: flex-start;
    margin-bottom: 8px;
  }
  .nc-name { font-size: 13px; font-weight: 700; }
  .nc-loc  { font-size: 10px; color: var(--muted); }
  .nc-badge {
    font-size: 9px; font-weight: 800; letter-spacing: .3px;
    padding: 3px 7px; border-radius: 4px;
  }
  .badge-healthy  { background: #dcfce7; color: var(--green); }
  .badge-warning  { background: #fef3c7; color: var(--amber); }
  .badge-critical { background: #fee2e2; color: var(--red); }

  .conf-wrap { display: flex; align-items: center; gap: 10px; margin: 6px 0 8px; }
  .conf-ring {
    width: 48px; height: 48px; position: relative; flex-shrink: 0;
  }
  .conf-ring svg { transform: rotate(-90deg); }
  .conf-ring .pct {
    position: absolute; inset: 0;
    display: flex; align-items: center; justify-content: center;
    font-size: 12px; font-weight: 800;
  }
  .conf-label { font-size: 10px; color: var(--muted); line-height: 1.3; }

  .meta-row {
    display: flex; justify-content: space-between;
    font-size: 10px; margin-bottom: 6px;
  }
  .meta-row span:first-child { color: var(--muted); }
  .meta-row span:last-child { font-weight: 700; }

  .spark-block { margin-top: 4px; }
  .spark-label {
    display: flex; justify-content: space-between;
    font-size: 10px; margin-bottom: 2px;
  }
  .spark-label span:first-child { color: var(--muted); }
  .spark-label span:last-child { font-weight: 700; }
  .spark-canvas {
    width: 100%; height: 22px;
    display: block;
  }
  .view-link {
    margin-top: auto; padding-top: 8px;
    font-size: 11px; color: var(--blue); font-weight: 600;
    text-decoration: none;
  }

  /* Right column */
  .right-col { display: flex; flex-direction: column; gap: 12px; }

  .fault-card, .alert-card, .status-card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 14px;
    box-shadow: 0 1px 2px rgba(0,0,0,.03);
  }
  .donut-wrap {
    display: flex; align-items: center; gap: 14px;
  }
  .donut {
    width: 90px; height: 90px; position: relative; flex-shrink: 0;
  }
  .donut svg { transform: rotate(-90deg); }
  .donut-center {
    position: absolute; inset: 0;
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
  }
  .donut-center .num { font-size: 18px; font-weight: 800; }
  .donut-center .lbl { font-size: 9px; color: var(--muted); font-weight: 600; }
  .fault-list { font-size: 11px; flex: 1; }
  .fault-item {
    display: flex; align-items: center; gap: 6px;
    margin-bottom: 5px;
  }
  .fault-item .swatch { width: 8px; height: 8px; border-radius: 2px; flex-shrink: 0; }
  .fault-item .name { flex: 1; color: var(--muted); }
  .fault-item .val { font-weight: 700; }

  .alert-row {
    display: flex; gap: 8px; margin-top: 8px;
  }
  .alert-box {
    flex: 1; text-align: center;
    border-radius: 8px; padding: 10px 6px;
  }
  .alert-box .num { font-size: 20px; font-weight: 800; }
  .alert-box .lbl { font-size: 9px; font-weight: 700; margin-top: 2px; letter-spacing: .3px; }
  .alert-crit { background: #fee2e2; color: var(--red); }
  .alert-warn { background: #fef3c7; color: var(--amber); }
  .alert-ok   { background: #dcfce7; color: var(--green); }

  .status-grid {
    display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 8px;
  }
  .st-item {
    font-size: 11px;
  }
  .st-item .k { color: var(--muted); }
  .st-item .v { font-weight: 700; display: flex; align-items: center; gap: 4px; margin-top: 2px; }
  .st-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--green); }

  /* ===== FOOTER STATUS BAR ===== */
  .footer {
    height: 36px;
    background: var(--card);
    border-top: 1px solid var(--border);
    display: flex; align-items: center;
    padding: 0 16px; gap: 18px;
    font-size: 11px; color: var(--muted);
    flex-shrink: 0;
  }
  .footer strong { color: var(--text); font-weight: 600; }
  .footer .sep { width: 1px; height: 14px; background: var(--border); }
  .footer-item { display: flex; align-items: center; gap: 5px; }
</style>
</head>
<body>

<!-- TOP NAV -->
<header class="topnav">
  <div class="logo">
    <div class="logo-icon">◈</div>
    <div style="line-height:1.15"><div style="font-weight:800;font-size:14px;letter-spacing:.3px">ZERO TWIN</div>
    <div style="font-size:9px;font-weight:600;color:var(--muted);letter-spacing:1px">COMMAND CENTER</div></div>
  </div>
  <nav class="nav-links">
    <a href="#" class="active">DASHBOARD</a>
    <a href="#">FLEET</a>
    <a href="#">TELEMETRY</a>
    <a href="#">ANALYTICS</a>
    <a href="#">ALERTS</a>
    <a href="#">CONFIG</a>
  </nav>
  <div class="top-right">
    <div class="sys-online"><span class="dot"></span> SYSTEM ONLINE</div>
    <div class="icon-btn">🔔<span class="badge-notif">3</span></div>
    <div class="icon-btn">⚙</div>
    <div class="clock"><strong id="sys-time">--:--:-- UTC</strong><span id="sys-date">May 22, 2025</span></div>
  </div>
</header>

<div class="main-wrap">
  <!-- SIDEBAR -->
  <aside class="sidebar">
    <div class="side-item active">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>
      OVERVIEW
    </div>
    <div class="side-item">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M12 2v4M12 18v4M4.9 4.9l2.8 2.8M16.3 16.3l2.8 2.8M2 12h4M18 12h4M4.9 19.1l2.8-2.8M16.3 7.7l2.8-2.8"/></svg>
      TOPOLOGY
    </div>
    <div class="side-item">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.6l-1-1a5.5 5.5 0 0 0-7.8 7.8l1 1L12 21l7.8-7.8 1-1a5.5 5.5 0 0 0 0-7.8z"/></svg>
      HEALTH
    </div>
    <div class="side-item">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
      TELEMETRY
    </div>
    <div class="side-item">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.3 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v10.3"/><path d="M14 14h.01"/><path d="M17 17h.01"/><path d="M20 20h.01"/></svg>
      FAULTS
    </div>
    <div class="side-item">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M8 12h8M12 8v8"/></svg>
      FEDERATION
    </div>
    <div class="side-item">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
      REPORTS
    </div>
    <div class="side-item">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
      SYSTEM
    </div>

    <div class="side-bottom">
      <div class="lab-logo">
        <div style="width:28px;height:28px;border-radius:50%;background:linear-gradient(135deg,#0ea5e9,#0284c7);display:flex;align-items:center;justify-content:center;color:white;font-size:12px">◈</div>
        <div><strong>PHI LAB</strong>Penelope Inc.</div>
      </div>
      <div class="version">ZeroTwin v1.0.0<br>Build: 2025.05.22</div>
    </div>
  </aside>

  <!-- MAIN CONTENT -->
  <main class="content">
    <!-- RADAR -->
    <section class="radar-card">
      <div class="radar-header">
        <div>
          <div class="radar-title">CROSS-BORDER SWARM TOPOLOGY RADAR</div>
          <div class="radar-sub">Real-Time Global View</div>
        </div>
        <div class="legend">
          <span><span class="d" style="background:var(--green)"></span> HEALTHY</span>
          <span><span class="d" style="background:var(--amber)"></span> WARNING</span>
          <span><span class="d" style="background:var(--red)"></span> CRITICAL</span>
        </div>
      </div>
      <div class="map-area" id="map-area">
        <div class="map-bg"></div>
        <div class="map-grid"></div>
        <svg class="conn-svg" id="conn-svg"></svg>
        <!-- UAV nodes positioned to approximate the mockup geo layout -->
        <div class="uav-node" id="uav-1" style="left:18%; top:55%">
          <div class="uav-ring ring-green" id="ring-1">
            <svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2L8 8h3v6h2V8h3L12 2zM5 18l-1 4h4l-1-2h4l-1 2h4l-1-4H5z"/></svg>
          </div>
          <div class="uav-label">
            <div class="name">UAV-1</div>
            <div class="loc">Lagos, Nigeria</div>
            <div class="lat lat-green" id="lat-1">● 82 ms</div>
          </div>
        </div>
        <div class="uav-node" id="uav-2" style="left:52%; top:28%">
          <div class="uav-ring ring-amber" id="ring-2">
            <svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2L8 8h3v6h2V8h3L12 2zM5 18l-1 4h4l-1-2h4l-1 2h4l-1-4H5z"/></svg>
          </div>
          <div class="uav-label">
            <div class="name">UAV-2</div>
            <div class="loc">Beijing, China</div>
            <div class="lat lat-amber" id="lat-2">● 128 ms</div>
          </div>
        </div>
        <div class="uav-node" id="uav-3" style="left:55%; top:58%">
          <div class="uav-ring ring-red" id="ring-3">
            <svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2L8 8h3v6h2V8h3L12 2zM5 18l-1 4h4l-1-2h4l-1 2h4l-1-4H5z"/></svg>
          </div>
          <div class="uav-label">
            <div class="name">UAV-3</div>
            <div class="loc">Shanghai, China</div>
            <div class="lat lat-red" id="lat-3">● 156 ms</div>
          </div>
        </div>
        <div class="uav-node" id="uav-4" style="left:72%; top:35%">
          <div class="uav-ring ring-amber" id="ring-4">
            <svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2L8 8h3v6h2V8h3L12 2zM5 18l-1 4h4l-1-2h4l-1 2h4l-1-4H5z"/></svg>
          </div>
          <div class="uav-label">
            <div class="name">UAV-4</div>
            <div class="loc">Tokyo, Japan</div>
            <div class="lat lat-amber" id="lat-4">● 98 ms</div>
          </div>
        </div>
        <div class="uav-node" id="uav-5" style="left:85%; top:48%">
          <div class="uav-ring ring-green" id="ring-5">
            <svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2L8 8h3v6h2V8h3L12 2zM5 18l-1 4h4l-1-2h4l-1 2h4l-1-4H5z"/></svg>
          </div>
          <div class="uav-label">
            <div class="name">UAV-5</div>
            <div class="loc">Seoul, South Korea</div>
            <div class="lat lat-green" id="lat-5">● 74 ms</div>
          </div>
        </div>

        <div class="map-controls">
          <button>+</button><button>−</button><button>⛶</button>
        </div>
        <div class="time-range">
          <button class="active">1H</button>
          <button>6H</button>
          <button>24H</button>
          <button>7D</button>
          <button>↻</button>
        </div>
      </div>
    </section>

    <!-- BOTTOM -->
    <div class="bottom-grid">
      <div>
        <div class="section-title">PER-NODE DIAGNOSTIC HEALTH OVERVIEW</div>
        <div class="nodes-row" id="nodes-row">
          <!-- filled by JS -->
        </div>
      </div>

      <div class="right-col">
        <div class="fault-card">
          <div class="section-title">FLEET FAULT DISTRIBUTION</div>
          <div class="donut-wrap">
            <div class="donut">
              <svg width="90" height="90" viewBox="0 0 90 90">
                <circle cx="45" cy="45" r="36" fill="none" stroke="#f1f5f9" stroke-width="12"/>
                <!-- segments drawn by JS -->
                <g id="donut-segs"></g>
              </svg>
              <div class="donut-center">
                <div class="num" id="total-faults">23</div>
                <div class="lbl">TOTAL<br>FAULTS</div>
              </div>
            </div>
            <div class="fault-list" id="fault-list"></div>
          </div>
        </div>

        <div class="alert-card">
          <div class="section-title">ALERT SUMMARY</div>
          <div class="alert-row">
            <div class="alert-box alert-crit">
              <div class="num" id="a-crit">2</div>
              <div class="lbl">CRITICAL<br>Immediate Action</div>
            </div>
            <div class="alert-box alert-warn">
              <div class="num" id="a-warn">3</div>
              <div class="lbl">WARNING<br>Monitor Closely</div>
            </div>
            <div class="alert-box alert-ok">
              <div class="num" id="a-ok">5</div>
              <div class="lbl">HEALTHY<br>All Systems Nominal</div>
            </div>
          </div>
        </div>

        <div class="status-card">
          <div class="section-title">SYSTEM STATUS</div>
          <div class="status-grid">
            <div class="st-item"><div class="k">Federation</div><div class="v"><span class="st-dot"></span> Online</div></div>
            <div class="st-item"><div class="k">DAG Network</div><div class="v"><span class="st-dot"></span> Healthy</div></div>
            <div class="st-item"><div class="k">Data Pipeline</div><div class="v"><span class="st-dot"></span> Online</div></div>
            <div class="st-item"><div class="k">Storage</div><div class="v"><span class="st-dot"></span> Synced</div></div>
          </div>
        </div>
      </div>
    </div>
  </main>
</div>

<!-- FOOTER -->
<footer class="footer">
  <div class="footer-item">◈ Federation Round: <strong id="f-round">127</strong></div>
  <div class="sep"></div>
  <div class="footer-item">▣ Global Model: <strong id="f-model">v2.7.3</strong></div>
  <div class="sep"></div>
  <div class="footer-item">👥 Participants: <strong id="f-part">5 / 5</strong></div>
  <div class="sep"></div>
  <div class="footer-item">⏱ Last Aggregation: <strong id="f-agg">--</strong></div>
  <div class="sep"></div>
  <div class="footer-item">∿ Latency (Avg): <strong id="f-lat">96 ms</strong></div>
  <div class="sep"></div>
  <div class="footer-item">⇅ Data Rate: <strong id="f-rate">1.24 MB/s</strong></div>
  <div class="sep"></div>
  <div class="footer-item">🔒 Secure Channel: <strong>TLS 1.3</strong></div>
</footer>

<script>
/* ---------- helpers ---------- */
function sparkline(canvas, data, color) {
  if (!canvas || !data || data.length < 2) return;
  const ctx = canvas.getContext('2d');
  const w = canvas.width = canvas.offsetWidth * 2;
  const h = canvas.height = canvas.offsetHeight * 2;
  ctx.clearRect(0, 0, w, h);
  const min = Math.min(...data), max = Math.max(...data);
  const range = max - min || 1;
  ctx.beginPath();
  ctx.strokeStyle = color;
  ctx.lineWidth = 2.5;
  ctx.lineJoin = 'round';
  data.forEach((v, i) => {
    const x = (i / (data.length - 1)) * w;
    const y = h - ((v - min) / range) * (h - 4) - 2;
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });
  ctx.stroke();
}

function confRing(svgEl, pct, color) {
  const r = 20, c = 2 * Math.PI * r;
  const offset = c - (pct / 100) * c;
  svgEl.innerHTML = `
    <circle cx="24" cy="24" r="${r}" fill="none" stroke="#f1f5f9" stroke-width="5"/>
    <circle cx="24" cy="24" r="${r}" fill="none" stroke="${color}" stroke-width="5"
      stroke-dasharray="${c}" stroke-dashoffset="${offset}" stroke-linecap="round"/>
  `;
}

function drawDonut(faults) {
  const colors = ['#dc2626','#d97706','#f59e0b','#16a34a','#0284c7'];
  const total = faults.reduce((s, f) => s + f[1], 0) || 1;
  let angle = 0;
  const segs = document.getElementById('donut-segs');
  segs.innerHTML = '';
  const r = 36, cx = 45, cy = 45;
  faults.forEach((f, i) => {
    const sweep = (f[1] / total) * 360;
    const a1 = angle * Math.PI / 180;
    const a2 = (angle + sweep) * Math.PI / 180;
    const x1 = cx + r * Math.cos(a1), y1 = cy + r * Math.sin(a1);
    const x2 = cx + r * Math.cos(a2), y2 = cy + r * Math.sin(a2);
    const large = sweep > 180 ? 1 : 0;
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', `M ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2}`);
    path.setAttribute('fill', 'none');
    path.setAttribute('stroke', colors[i % colors.length]);
    path.setAttribute('stroke-width', '12');
    segs.appendChild(path);
    angle += sweep;
  });
  // legend
  const list = document.getElementById('fault-list');
  list.innerHTML = faults.map((f, i) => `
    <div class="fault-item">
      <span class="swatch" style="background:${colors[i]}"></span>
      <span class="name">${f[0]}</span>
      <span class="val">${f[1]} (${f[2]}%)</span>
    </div>
  `).join('');
}

function drawConnections() {
  const svg = document.getElementById('conn-svg');
  const area = document.getElementById('map-area');
  const positions = [1,2,3,4,5].map(i => {
    const el = document.getElementById('uav-' + i);
    return {
      x: el.offsetLeft + el.offsetWidth / 2,
      y: el.offsetTop + 22
    };
  });
  // mesh: 1-2, 1-3, 2-3, 2-4, 3-4, 4-5, 3-5
  const edges = [[0,1],[0,2],[1,2],[1,3],[2,3],[3,4],[2,4]];
  let html = '';
  edges.forEach(([a,b]) => {
    const p1 = positions[a], p2 = positions[b];
    html += `<line x1="${p1.x}" y1="${p1.y}" x2="${p2.x}" y2="${p2.y}"
      stroke="#94a3b8" stroke-width="1.5" stroke-dasharray="5,4" opacity="0.55"/>`;
  });
  svg.innerHTML = html;
}

function renderNodes(nodes) {
  const row = document.getElementById('nodes-row');
  let html = '';
  for (let i = 1; i <= 5; i++) {
    const n = nodes[i];
    const badgeCls = n.status === 'HEALTHY' ? 'badge-healthy' :
                     n.status === 'WARNING' ? 'badge-warning' : 'badge-critical';
    const color = n.accent;
    html += `
      <div class="node-card">
        <div class="nc-head">
          <div>
            <div class="nc-name">◈ ${n.name}</div>
            <div class="nc-loc">${n.loc}</div>
          </div>
          <span class="nc-badge ${badgeCls}">${n.status}</span>
        </div>
        <div class="conf-wrap">
          <div class="conf-ring">
            <svg width="48" height="48" viewBox="0 0 48 48" id="cring-${i}"></svg>
            <div class="pct" style="color:${color}">${n.confidence}%</div>
          </div>
          <div class="conf-label">Health<br>Confidence</div>
        </div>
        <div class="meta-row"><span>Flight Time</span><span>${n.flight_time}</span></div>
        <div class="meta-row"><span>Distance</span><span>${n.distance} km</span></div>
        <div class="spark-block">
          <div class="spark-label"><span>Vibration (g)</span><span style="color:${color}">${n.vib.toFixed(3)} g</span></div>
          <canvas class="spark-canvas" id="spark-vib-${i}"></canvas>
        </div>
        <div class="spark-block">
          <div class="spark-label"><span>Temperature (°C)</span><span style="color:${color}">${n.temp} °C</span></div>
          <canvas class="spark-canvas" id="spark-temp-${i}"></canvas>
        </div>
        <div class="spark-block">
          <div class="spark-label"><span>Voltage (V)</span><span style="color:${color}">${n.volt} V</span></div>
          <canvas class="spark-canvas" id="spark-volt-${i}"></canvas>
        </div>
        <a class="view-link" href="#">View Details →</a>
      </div>`;
  }
  row.innerHTML = html;

  // draw rings + sparklines after DOM insert
  for (let i = 1; i <= 5; i++) {
    const n = nodes[i];
    confRing(document.getElementById('cring-' + i), n.confidence, n.accent);
    sparkline(document.getElementById('spark-vib-' + i), n.vib_hist, n.accent);
    sparkline(document.getElementById('spark-temp-' + i), n.temp_hist, n.accent);
    sparkline(document.getElementById('spark-volt-' + i), n.volt_hist, n.accent);
  }
}

async function tick() {
  try {
    const res = await fetch('/api/live');
    const d = await res.json();

    // map labels + rings
    for (let i = 1; i <= 5; i++) {
      const n = d.nodes[i];
      const ring = document.getElementById('ring-' + i);
      ring.className = 'uav-ring ring-' + n.pulse;
      const latEl = document.getElementById('lat-' + i);
      latEl.textContent = '● ' + n.latency + ' ms';
      latEl.className = 'lat lat-' + n.pulse;
    }

    renderNodes(d.nodes);
    drawDonut(d.faults);
    document.getElementById('total-faults').textContent = d.total_faults;
    document.getElementById('a-crit').textContent = d.critical;
    document.getElementById('a-warn').textContent = d.warning;
    document.getElementById('a-ok').textContent = d.healthy;

    document.getElementById('f-round').textContent = d.fed_round;
    document.getElementById('f-model').textContent = d.global_model;
    document.getElementById('f-part').textContent = d.participants;
    document.getElementById('f-agg').textContent = d.last_agg;
    document.getElementById('f-lat').textContent = d.avg_latency + ' ms';
    document.getElementById('f-rate').textContent = d.data_rate + ' MB/s';
    document.getElementById('sys-time').textContent = d.system_time;
    document.getElementById('sys-date').textContent = d.system_date;

    drawConnections();
  } catch (e) {
    console.warn('poll error', e);
  }
}

window.addEventListener('load', () => {
  drawConnections();
  tick();
  setInterval(tick, 800);
});
window.addEventListener('resize', drawConnections);
</script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/api/live")
def api_live():
    return jsonify(generate_live_state())


if __name__ == "__main__":
    print("[*] ZeroTwin Command Center")
    print("[*] Open http://127.0.0.1:5000")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
