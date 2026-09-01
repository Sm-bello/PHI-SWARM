"""
ZeroTwin Command Center — LIVE edition.

Same visual dashboard as observability/dashboard.py, but /api/live now
returns a real-time snapshot of an actual LiveSimulationEngine running in a
background thread inside this same process (so there is no file/IPC hop
between "the simulation" and "the page you're looking at" — just a
thread-safe in-memory read). Adds a Security & Audit panel driven by the
hash-chained audit trail.

Run:
    python -m zerotwin.observability.dashboard_live
Then open http://127.0.0.1:5000
"""

from __future__ import annotations

import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from flask import Flask, render_template_string, jsonify

from zerotwin.observability.dashboard import HTML as BASE_HTML
from zerotwin.simulation.phi_swarm_engine import PHISwarmEngine

logging.getLogger("werkzeug").setLevel(logging.ERROR)

app = Flask(__name__)
engine = PHISwarmEngine(num_nodes=5, seed=42, samples_per_node=300, round_interval=4.0)

_last_round_seen = -1
_last_agg_ts = "--"
_last_bytes = 0
_last_bytes_ts = time.time()

# ---------------------------------------------------------------------------
# Security & Audit panel: injected into the existing page (floating, so it
# never depends on the base template's internal grid layout).
# ---------------------------------------------------------------------------
AUDIT_PANEL_HTML = r"""
<div id="audit-panel" style="
  position:fixed; right:16px; bottom:70px; width:340px; max-height:46vh;
  background:#ffffff; border:1px solid #e2e8f0; border-radius:10px;
  box-shadow:0 8px 24px rgba(15,23,42,.12); z-index:200; overflow:hidden;
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <div style="padding:10px 14px; border-bottom:1px solid #e2e8f0; display:flex; justify-content:space-between; align-items:center; background:#f8fafc;">
    <strong style="font-size:12px; letter-spacing:.3px; color:#0f172a;">🔒 Security &amp; Audit Trail</strong>
    <span id="audit-verify-badge" style="font-size:10px; font-weight:700; padding:2px 8px; border-radius:999px;">…</span>
  </div>
  <div style="padding:10px 14px; font-size:11px; color:#334155; display:grid; grid-template-columns:1fr 1fr; gap:4px 10px;">
    <div>Updates accepted: <strong id="sec-accepted">0</strong></div>
    <div>Updates rejected: <strong id="sec-rejected">0</strong></div>
    <div>Encrypted msgs: <strong id="sec-encrypted">0</strong></div>
    <div>Eavesdrops blocked: <strong id="sec-blocked">0</strong></div>
    <div>Replays blocked: <strong id="sec-replay">0</strong></div>
    <div>Chain length: <strong id="sec-chainlen">0</strong></div>
  </div>
  <div id="audit-log" style="padding:6px 14px 12px; font-size:10.5px; line-height:1.5; color:#475569; max-height:22vh; overflow-y:auto; font-family:ui-monospace,SFMono-Regular,Menlo,monospace;"></div>
</div>
<script>
async function auditTick() {
  try {
    const res = await fetch('/api/audit');
    const d = await res.json();
    document.getElementById('sec-accepted').textContent = d.security.accepted_updates;
    document.getElementById('sec-rejected').textContent = d.security.rejected_updates;
    document.getElementById('sec-encrypted').textContent = d.security.encrypted_messages;
    document.getElementById('sec-blocked').textContent = d.security.eavesdrops_blocked;
    document.getElementById('sec-replay').textContent = d.security.replays_blocked;
    document.getElementById('sec-chainlen').textContent = d.chain_length;
    const badge = document.getElementById('audit-verify-badge');
    if (d.verified) {
      badge.textContent = 'CHAIN VERIFIED';
      badge.style.background = '#dcfce7'; badge.style.color = '#16a34a';
    } else {
      badge.textContent = 'TAMPER DETECTED @' + d.first_bad_seq;
      badge.style.background = '#fee2e2'; badge.style.color = '#dc2626';
    }
    const log = document.getElementById('audit-log');
    log.innerHTML = d.security.recent_events.slice().reverse().map(e => {
      const t = new Date(e.ts * 1000).toLocaleTimeString();
      return `<div>#${e.seq} ${t} <b>${e.event_type}</b></div>`;
    }).join('');
  } catch (e) { console.warn('audit poll error', e); }
}
window.addEventListener('load', () => { auditTick(); setInterval(auditTick, 1500); });
</script>
"""

FULL_HTML = BASE_HTML.replace("</body>", AUDIT_PANEL_HTML + "\n</body>")


def _enrich(state: dict) -> dict:
    """Add the display fields the existing dashboard JS expects that the
    engine itself doesn't track (system clock, derived rates, version tag)."""
    global _last_round_seen, _last_agg_ts, _last_bytes, _last_bytes_ts

    now = time.time()
    if state["fed_round"] != _last_round_seen:
        _last_round_seen = state["fed_round"]
        _last_agg_ts = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")

    dt = max(now - _last_bytes_ts, 1e-6)
    d_bytes = max(state["bytes_transferred"] - _last_bytes, 0)
    data_rate = round((d_bytes / dt) / (1024 * 1024), 3)
    _last_bytes = state["bytes_transferred"]
    _last_bytes_ts = now

    latencies = [n["latency"] for n in state["nodes"].values()] or [0]

    state["global_model"] = f"live-r{state['fed_round']}"
    state["last_agg"] = _last_agg_ts
    state["avg_latency"] = round(sum(latencies) / len(latencies))
    state["data_rate"] = data_rate
    state["system_time"] = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    state["system_date"] = datetime.now(timezone.utc).strftime("%b %d, %Y")
    return state


@app.route("/")
def index():
    return render_template_string(FULL_HTML)


@app.route("/api/live")
def api_live():
    return jsonify(_enrich(engine.get_state()))


@app.route("/api/audit")
def api_audit():
    state = engine.get_state()
    verify = engine.audit_verify()
    return jsonify({
        "verified": verify["verified"],
        "first_bad_seq": verify["first_bad_seq"],
        "chain_length": engine.ledger._seq,
        "security": state["security"],
    })


if __name__ == "__main__":
    engine.start()
    print("[*] ZeroTwin Command Center — LIVE simulation running in background")
    print(f"[*] Audit trail: {engine.ledger.path}")
    print("[*] Open http://127.0.0.1:5000")
    try:
        app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
    finally:
        engine.stop()
