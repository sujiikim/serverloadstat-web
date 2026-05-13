#!/usr/bin/env python3
import argparse
import json
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DATA_FILE = "data/stat_data.json"
PORT = 4000
REFRESH_SECONDS = 3

MIN_USER_CPU_UTIL_PERCENT = 10.0


def load_data():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"time": "-", "data": []}


def get_status(ratio: float):
    if ratio > 1.0:
        return "high", "HIGH"
    if ratio > 0.8:
        return "warn", "WARN"
    return "ok", "OK"


def get_d_class(d_count: int):
    if d_count >= 10:
        return "high"
    if d_count >= 3:
        return "warn"
    return "ok"


def format_top_users(top_users):
    if not top_users:
        return "-"

    parts = []
    for item in top_users:
        user = escape(str(item.get("user", "-")))
        cpu_util = float(item.get("cpu_util_percent", 0))

        if cpu_util >= MIN_USER_CPU_UTIL_PERCENT:
            parts.append(f"{user} ({cpu_util:.1f}%)")

    return "<br>".join(parts) if parts else "-"


def format_io_wait_users(io_wait_users):
    if not io_wait_users:
        return "-"

    parts = []
    for item in io_wait_users:
        user = escape(str(item.get("user", "-")))
        d_count = int(item.get("d_count", 0))
        if d_count > 0:
            parts.append(f"{user} ({d_count}D)")

    return "<br>".join(parts) if parts else "-"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        payload = load_data()
        rows = []

        for i, d in enumerate(payload.get("data", [])):
            host = escape(str(d.get("host", "-")))

            if not d.get("ok"):
                rows.append(f"""
                <tr class="down-row">
                    <td>{i}</td>
                    <td><span class="host">{host}</span></td>
                    <td><span class="badge down">DOWN</span></td>
                    <td colspan="9">{escape(str(d.get("error", "unreachable")))}</td>
                </tr>
                """)
                continue

            ratio = float(d.get("ratio", 0))
            status_class, status_text = get_status(ratio)

            cpu_util = float(d.get("cpu_util", 0))
            r_count = int(d.get("r_count", 0))
            d_count = int(d.get("d_count", 0))
            d_class = get_d_class(d_count)

            top_users_html = format_top_users(d.get("top_users", []))
            io_wait_users_html = format_io_wait_users(d.get("io_wait_users", []))

            rows.append(f"""
            <tr>
                <td>{i}</td>
                <td><span class="host">{host}</span></td>

                <td><span class="badge {status_class}">{status_text}</span></td>
                <td>{int(d["cpu"])}</td>
                <td class="{status_class}">{ratio:.2f}</td>
                <td>{float(d["l1"]):.2f}</td>
                <td>{float(d["l5"]):.2f}</td>
                <td>R:{r_count} / <span class="{d_class}">D:{d_count}</span></td>

                <td>{cpu_util:.1f}%</td>
                <td class="top-users">{top_users_html}</td>

            </tr>
            """)

        rows_html = "\n".join(rows)

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="{REFRESH_SECONDS}">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Server Load Dashboard</title>
  <style>
    :root {{
      --bg: #0b1020;
      --panel: #121933;
      --line: #2a3566;
      --text: #edf2ff;
      --muted: #a8b3d9;
      --shadow: 0 10px 30px rgba(0,0,0,0.25);
    }}

    * {{ box-sizing: border-box; }}

    body {{
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at top left, #17214a 0%, transparent 35%),
        radial-gradient(circle at top right, #12203d 0%, transparent 25%),
        var(--bg);
      color: var(--text);
    }}

    .container {{
      max-width: 1560px;
      margin: 20px auto;
      padding: 0 12px 20px;
    }}

    .header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 16px;
      margin-bottom: 12px;
    }}

    .title-wrap h1 {{
      margin: 0;
      font-size: 24px;
      font-weight: 800;
      letter-spacing: -0.03em;
    }}

    .meta-card {{
      min-width: 200px;
      background: rgba(18, 25, 51, 0.92);
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: 12px;
      padding: 10px 12px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(10px);
    }}

    .meta-label {{
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      margin-bottom: 4px;
    }}

    .meta-value {{
      font-size: 14px;
      font-weight: 700;
    }}

    .table-card {{
      background: rgba(18, 25, 51, 0.92);
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: 12px;
      overflow: hidden;
      box-shadow: var(--shadow);
      backdrop-filter: blur(10px);
    }}

    table {{
      width: 100%;
      border-collapse: collapse;
    }}

    thead {{
      background: rgba(255,255,255,0.03);
    }}

    th {{
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-weight: 700;
      padding: 10px 12px;
      text-align: left;
      vertical-align: top;
      white-space: nowrap;
      border-bottom: 1px solid var(--line);
    }}

    th.section-load {{
      color: #bfdbfe;
    }}

    th.section-cpu {{
      color: #bbf7d0;
    }}

    th.section-io {{
      color: #fde68a;
    }}

    td {{
      padding: 10px 12px;
      border-top: 1px solid var(--line);
      font-size: 13px;
      vertical-align: top;
      white-space: nowrap;
    }}

    tbody tr:hover {{
      background: rgba(255,255,255,0.03);
    }}

    .host {{
      font-weight: 700;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    }}

    .badge {{
      display: inline-flex;
      align-items: center;
      padding: 4px 8px;
      border-radius: 999px;
      font-size: 11px;
      font-weight: 800;
    }}

    .badge.ok {{
      background: rgba(34, 197, 94, 0.16);
      color: #86efac;
    }}

    .badge.warn {{
      background: rgba(245, 158, 11, 0.16);
      color: #fcd34d;
    }}

    .badge.high {{
      background: rgba(239, 68, 68, 0.16);
      color: #fca5a5;
    }}

    .badge.down {{
      background: rgba(244, 63, 94, 0.16);
      color: #fda4af;
    }}

    .ok {{ color: #86efac; font-weight: 700; }}
    .warn {{ color: #fcd34d; font-weight: 700; }}
    .high {{ color: #fca5a5; font-weight: 700; }}

    .down-row td {{
      color: #fda4af;
    }}

    .top-users, .io-users {{
      line-height: 1.45;
      min-width: 170px;
      white-space: nowrap;
    }}

    .legend {{
      display: flex;
      gap: 8px;
      margin-top: 10px;
      font-size: 12px;
      flex-wrap: wrap;
    }}

    .footer {{
      margin-top: 10px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.4;
    }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div class="title-wrap">
        <h1>Server Load Dashboard</h1>
        <div style="color:#a8b3d9; font-size:12px; margin-top:4px;">
          R = Processes waiting for CPU (Please keep under CPU count)
        </div>
        <div style="color:#a8b3d9; font-size:12px; margin-top:4px;">
          D = Disk/I/O wait (Please keep under 3, and definitely under 10)
        </div>
      </div>
      <div class="meta-card">
        <div class="meta-label">Last updated</div>
        <div class="meta-value">{escape(str(payload.get("time", "-")))}</div>
      </div>
    </div>

    <div class="table-card">
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Host</th>

            <th class="section-load">Status</th>
            <th class="section-load">CPU</th>
            <th class="section-load">Load/CPU</th>
            <th class="section-load">1m Load</th>
            <th class="section-load">5m Load</th>
            <th class="section-load">(R=CPU, D=I/O)</th>

            <th class="section-cpu">CPU Util</th>
            <th class="section-cpu">Top CPU Users (&gt;={MIN_USER_CPU_UTIL_PERCENT:.0f}%)</th>

          </tr>
        </thead>
        <tbody>
          {rows_html}
        </tbody>
      </table>
    </div>

    <div class="legend">
      <span class="badge ok">OK ≤ 0.8</span>
      <span class="badge warn">WARN &gt; 0.8</span>
      <span class="badge high">HIGH &gt; 1.0</span>
      <span class="badge down">DOWN</span>
    </div>

    <div class="footer">
      Auto-refresh every {REFRESH_SECONDS}s<br>
     </div>
  </div>
</body>
</html>
"""

        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


def parse_args():
    parser = argparse.ArgumentParser(description="Serve a server load dashboard.")
    parser.add_argument("--port", type=int, default=PORT, help="HTTP port")
    return parser.parse_args()


def main():
    global PORT

    args = parse_args()
    PORT = args.port

    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Serving on port {PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
