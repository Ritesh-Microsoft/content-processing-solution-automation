#!/usr/bin/env python3
"""
Generate a self-contained HTML dashboard for GitHub Issue Tracking.

Usage:
    python generate_dashboard.py

Environment variables:
    GITHUB_TOKEN   – GitHub PAT or app token (optional but recommended)
    STATE_FILE     – Path to tracked_issues_state.json
    OUTPUT_HTML    – Where to write the dashboard (default: dashboard.html in same dir)
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

# ─── configuration ────────────────────────────────────────────────────────────

IST = timezone(timedelta(hours=5, minutes=30))

REPOS = [
    {"name": "Customer Chatbot", "owner": "microsoft", "repo": "customer-chatbot-solution-accelerator", "primary": "Ajit Padhi", "secondary": "Prajwal D C"},
    {"name": "Code Modernization", "owner": "microsoft", "repo": "Modernize-your-code-solution-accelerator", "primary": "Priyanka Singhal", "secondary": "Shreyas Waikar"},
    {"name": "Container Migration", "owner": "microsoft", "repo": "Container-Migration-Solution-Accelerator", "primary": "Shreyas Waikar", "secondary": "Priyanka Singhal"},
    {"name": "Content Generation", "owner": "microsoft", "repo": "content-generation-solution-accelerator", "primary": "Ragini Chauragade", "secondary": "Pavan Kumar"},
    {"name": "Content Processing", "owner": "microsoft", "repo": "content-processing-solution-accelerator", "primary": "Shreyas Waikar", "secondary": "Ajit Padhi"},
    {"name": "CWYD", "owner": "Azure-Samples", "repo": "chat-with-your-data-solution-accelerator", "primary": "Ajit Padhi", "secondary": "Priyanka Singhal"},
    {"name": "Data & Agent Governance", "owner": "microsoft", "repo": "Data-and-Agent-Governance-and-Security-Accelerator", "primary": "Saswato Chatterjee", "secondary": "Yamini"},
    {"name": "Deploy AI App", "owner": "microsoft", "repo": "Deploy-Your-AI-Application-In-Production", "primary": "Saswato Chatterjee", "secondary": "Yamini"},
    {"name": "DKM", "owner": "microsoft", "repo": "Document-Knowledge-Mining-Solution-Accelerator", "primary": "Priyanka Singhal", "secondary": "Ajit Padhi"},
    {"name": "Agentic App", "owner": "microsoft", "repo": "agentic-applications-for-unified-data-foundation-solution-accelerator", "primary": "Ragini Chauragade", "secondary": "Pavan Kumar"},
    {"name": "KM Generic", "owner": "microsoft", "repo": "Conversation-Knowledge-Mining-Solution-Accelerator", "primary": "Pavan Kumar", "secondary": "Avijit Ghorui"},
    {"name": "UDF", "owner": "microsoft", "repo": "unified-data-foundation-with-fabric-solution-accelerator", "primary": "Saswato Chatterjee", "secondary": "Yamini"},
    {"name": "MACAE", "owner": "microsoft", "repo": "Multi-Agent-Custom-Automation-Engine-Solution-Accelerator", "primary": "Dhruvkumar Babariya", "secondary": "Abdul Mujeeb T A"},
    {"name": "RTI", "owner": "microsoft", "repo": "real-time-intelligence-operations-solution-accelerator", "primary": "Saswato Chatterjee", "secondary": "Yamini"},
]

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.environ.get("STATE_FILE", os.path.join(SCRIPT_DIR, "..", "tracked_issues_state.json"))
OUTPUT_HTML = os.environ.get("OUTPUT_HTML", os.path.join(SCRIPT_DIR, "dashboard.html"))

# ─── github helpers ───────────────────────────────────────────────────────────

def _gh_headers():
    token = os.environ.get("GITHUB_TOKEN", "")
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch_open_issues(owner: str, repo: str, retries: int = 3) -> list[dict]:
    """Fetch all open issues (excluding PRs) with pagination and retry."""
    all_issues: list[dict] = []
    page = 1
    while True:
        url = f"https://api.github.com/repos/{owner}/{repo}/issues"
        params = {"state": "open", "per_page": 100, "page": page}
        data = None
        for attempt in range(1, retries + 1):
            try:
                resp = requests.get(url, headers=_gh_headers(), params=params, timeout=30)
                if resp.status_code == 403 and "rate limit" in resp.text.lower():
                    wait = 5 * attempt
                    print(f"  ⚠ Rate-limited, waiting {wait}s (attempt {attempt}/{retries})…")
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                data = resp.json()
                break
            except (requests.RequestException, ValueError) as exc:
                wait = 5 * attempt
                print(f"  ⚠ Error fetching {owner}/{repo} page {page} (attempt {attempt}/{retries}): {exc}")
                if attempt < retries:
                    time.sleep(wait)
                else:
                    print(f"  ✗ Gave up on {owner}/{repo} page {page}")
                    return all_issues
        if data is None:
            break
        # filter out pull requests
        issues = [i for i in data if "pull_request" not in i]
        all_issues.extend(issues)
        if len(data) < 100:
            break
        page += 1
    return all_issues

# ─── state file helpers ───────────────────────────────────────────────────────

def load_state() -> dict:
    path = STATE_FILE
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            print(f"⚠ Could not read state file {path}: {exc}")
    else:
        print(f"ℹ State file not found at {path}; overdue data will be empty.")
    return {}


def count_overdue(state: dict, owner: str, repo: str) -> int:
    """Count issues where followup_found=False and age >= 2 days."""
    now = datetime.now(timezone.utc)
    key = f"{owner}/{repo}"
    repo_state = state.get(key, {})
    details = repo_state.get("issue_details", {})
    overdue = 0
    for _num, det in details.items():
        if det.get("followup_found", False):
            continue
        first_seen_str = det.get("first_seen", "")
        if not first_seen_str:
            continue
        try:
            first_seen = datetime.fromisoformat(first_seen_str)
            if first_seen.tzinfo is None:
                first_seen = first_seen.replace(tzinfo=timezone.utc)
            if (now - first_seen).total_seconds() >= 2 * 86400:
                overdue += 1
        except ValueError:
            pass
    return overdue

# ─── data aggregation ─────────────────────────────────────────────────────────

def _classify_issue(issue: dict) -> str:
    labels = [lbl["name"].lower() for lbl in issue.get("labels", [])]
    if "bug" in labels:
        return "bug"
    if "enhancement" in labels:
        return "enhancement"
    return "other"


def _age_days(created_at: str) -> int:
    created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - created).days


def aggregate(repos_data: list[dict], state: dict) -> dict:
    """Build all aggregate structures for the dashboard."""
    total_issues = 0
    total_bugs = 0
    total_enhancements = 0
    total_other = 0
    total_overdue = 0

    repo_summaries: list[dict] = []
    owner_counts: dict[str, int] = {}
    all_issues_flat: list[dict] = []

    for entry in repos_data:
        cfg = entry["config"]
        issues = entry["issues"]
        n_bugs = sum(1 for i in issues if _classify_issue(i) == "bug")
        n_enh = sum(1 for i in issues if _classify_issue(i) == "enhancement")
        n_other = len(issues) - n_bugs - n_enh
        overdue = count_overdue(state, cfg["owner"], cfg["repo"])

        oldest_age = max((_age_days(i["created_at"]) for i in issues), default=0)

        total_issues += len(issues)
        total_bugs += n_bugs
        total_enhancements += n_enh
        total_other += n_other
        total_overdue += overdue

        repo_summaries.append({
            "name": cfg["name"],
            "owner": cfg["owner"],
            "repo": cfg["repo"],
            "open": len(issues),
            "bugs": n_bugs,
            "enhancements": n_enh,
            "other": n_other,
            "overdue": overdue,
            "oldest_age": oldest_age,
            "primary": cfg["primary"],
            "secondary": cfg["secondary"],
        })

        owner_counts[cfg["primary"]] = owner_counts.get(cfg["primary"], 0) + len(issues)

        for iss in issues:
            all_issues_flat.append({
                "number": iss["number"],
                "html_url": iss["html_url"],
                "title": iss["title"],
                "user": iss.get("user", {}).get("login", "unknown"),
                "labels": iss.get("labels", []),
                "created_at": iss["created_at"],
                "age": _age_days(iss["created_at"]),
                "kind": _classify_issue(iss),
                "accelerator": cfg["name"],
                "repo_owner": cfg["owner"],
                "repo_name": cfg["repo"],
            })

    all_issues_flat.sort(key=lambda x: x["age"], reverse=True)

    return {
        "total_issues": total_issues,
        "total_bugs": total_bugs,
        "total_enhancements": total_enhancements,
        "total_other": total_other,
        "total_overdue": total_overdue,
        "repo_summaries": repo_summaries,
        "owner_counts": owner_counts,
        "all_issues": all_issues_flat[:50],
    }

# ─── HTML generation ──────────────────────────────────────────────────────────

def _label_badge(label: dict) -> str:
    name = label.get("name", "")
    color = label.get("color", "cccccc")
    # determine text colour from background brightness
    try:
        r, g, b = int(color[:2], 16), int(color[2:4], 16), int(color[4:6], 16)
        text_color = "#fff" if (r * 0.299 + g * 0.587 + b * 0.114) < 160 else "#000"
    except (ValueError, IndexError):
        text_color = "#000"
        color = "cccccc"
    from html import escape
    return (
        f'<span style="background:#{color};color:{text_color};padding:2px 8px;'
        f'border-radius:12px;font-size:0.75rem;margin-right:3px;white-space:nowrap">'
        f'{escape(name)}</span>'
    )


def _kind_badge(kind: str) -> str:
    colors = {"bug": "#d32f2f", "enhancement": "#2e7d32", "other": "#757575"}
    bg = colors.get(kind, "#757575")
    from html import escape
    return (
        f'<span style="background:{bg};color:#fff;padding:2px 8px;'
        f'border-radius:12px;font-size:0.75rem">{escape(kind.title())}</span>'
    )


def _age_badge(days: int) -> str:
    if days > 7:
        bg = "#d32f2f"
    elif days > 2:
        bg = "#f9a825"
    else:
        bg = "#2e7d32"
    return (
        f'<span style="background:{bg};color:#fff;padding:2px 8px;'
        f'border-radius:12px;font-size:0.75rem">{days}d</span>'
    )


def generate_html(agg: dict) -> str:
    now_ist = datetime.now(IST).strftime("%d %b %Y, %I:%M %p IST")
    repo_count = len(REPOS)

    # chart data
    repo_names_js = json.dumps([r["name"] for r in agg["repo_summaries"]])
    bugs_js = json.dumps([r["bugs"] for r in agg["repo_summaries"]])
    enh_js = json.dumps([r["enhancements"] for r in agg["repo_summaries"]])
    other_js = json.dumps([r["other"] for r in agg["repo_summaries"]])

    # repo summary rows
    repo_rows = ""
    for r in agg["repo_summaries"]:
        issues_url = f"https://github.com/{r['owner']}/{r['repo']}/issues"
        overdue_badge = (
            f'<span style="background:#d32f2f;color:#fff;padding:2px 8px;border-radius:12px;font-size:0.8rem">{r["overdue"]}</span>'
            if r["overdue"] > 0
            else '<span style="background:#2e7d32;color:#fff;padding:2px 8px;border-radius:12px;font-size:0.8rem">0</span>'
        )
        repo_rows += f"""<tr>
  <td><a href="{issues_url}" target="_blank" style="color:#0078D4;text-decoration:none;font-weight:600">{r["name"]}</a></td>
  <td style="text-align:center"><span style="background:#0078D4;color:#fff;padding:2px 10px;border-radius:12px;font-size:0.85rem">{r["open"]}</span></td>
  <td style="text-align:center">{r["bugs"]}</td>
  <td style="text-align:center">{r["enhancements"]}</td>
  <td style="text-align:center">{r["other"]}</td>
  <td style="text-align:center">{overdue_badge}</td>
  <td style="text-align:center">{r["oldest_age"]}d</td>
  <td>{r["primary"]}</td>
  <td>{r["secondary"]}</td>
</tr>\n"""

    # owner workload rows
    max_owner_count = max(agg["owner_counts"].values()) if agg["owner_counts"] else 1
    owner_rows = ""
    for owner_name, cnt in sorted(agg["owner_counts"].items(), key=lambda x: x[1], reverse=True):
        bar_pct = int(cnt / max_owner_count * 100) if max_owner_count else 0
        owner_rows += f"""<tr>
  <td style="font-weight:600">{owner_name}</td>
  <td style="text-align:center">{cnt}</td>
  <td><div style="background:#e3f2fd;border-radius:4px;overflow:hidden"><div style="width:{bar_pct}%;background:#0078D4;height:20px;border-radius:4px"></div></div></td>
</tr>\n"""

    # all issues rows
    from html import escape as html_escape
    issue_rows = ""
    for iss in agg["all_issues"]:
        title_trunc = iss["title"][:80] + ("…" if len(iss["title"]) > 80 else "")
        labels_html = " ".join(_label_badge(lbl) for lbl in iss["labels"]) if iss["labels"] else _kind_badge(iss["kind"])
        issue_rows += f"""<tr>
  <td><a href="{iss["html_url"]}" target="_blank" style="color:#0078D4;text-decoration:none">#{iss["number"]}</a></td>
  <td>{html_escape(iss["accelerator"])}</td>
  <td title="{html_escape(iss["title"])}">{html_escape(title_trunc)}</td>
  <td>{html_escape(iss["user"])}</td>
  <td>{labels_html}</td>
  <td style="text-align:center">{_age_badge(iss["age"])}</td>
</tr>\n"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GitHub Issue Tracker Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
  * {{{{ box-sizing: border-box; margin: 0; padding: 0; }}}}
  body {{{{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f0f2f5; color: #333; }}}}
  .header {{{{ background: linear-gradient(135deg, #0078D4, #005a9e); color: #fff; padding: 32px 24px; text-align: center; }}}}
  .header h1 {{{{ font-size: 1.8rem; font-weight: 700; margin-bottom: 6px; }}}}
  .header p {{{{ font-size: 0.95rem; opacity: 0.9; }}}}
  .container {{{{ max-width: 1400px; margin: 0 auto; padding: 24px 16px; }}}}
  .kpi-grid {{{{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin-bottom: 28px; }}}}
  .kpi-card {{{{ background: #fff; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); padding: 20px; text-align: center; }}}}
  .kpi-card .value {{{{ font-size: 2rem; font-weight: 700; }}}}
  .kpi-card .label {{{{ font-size: 0.85rem; color: #666; margin-top: 4px; }}}}
  .card {{{{ background: #fff; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); padding: 20px; margin-bottom: 24px; }}}}
  .card h2 {{{{ font-size: 1.15rem; font-weight: 600; margin-bottom: 16px; color: #0078D4; }}}}
  .charts-grid {{{{ display: grid; grid-template-columns: 2fr 1fr; gap: 24px; margin-bottom: 24px; }}}}
  @media (max-width: 900px) {{{{ .charts-grid {{{{ grid-template-columns: 1fr; }}}} }}}}
  table {{{{ width: 100%; border-collapse: collapse; font-size: 0.88rem; }}}}
  thead th {{{{ position: sticky; top: 0; background: #f5f5f5; text-align: left; padding: 10px 8px; border-bottom: 2px solid #ddd; font-weight: 600; white-space: nowrap; }}}}
  tbody td {{{{ padding: 8px; border-bottom: 1px solid #eee; vertical-align: middle; }}}}
  tbody tr:hover {{{{ background: #f7fbff; }}}}
  .table-scroll {{{{ overflow-x: auto; }}}}
  .footer {{{{ text-align: center; color: #888; font-size: 0.8rem; padding: 24px 0; }}}}
</style>
</head>
<body>

<div class="header">
  <h1>GitHub Issue Tracker Dashboard</h1>
  <p>Tracking {repo_count} repositories &bull; Generated {now_ist}</p>
</div>

<div class="container">

<!-- KPI Cards -->
<div class="kpi-grid">
  <div class="kpi-card"><div class="value" style="color:#0078D4">{agg["total_issues"]}</div><div class="label">Total Open Issues</div></div>
  <div class="kpi-card"><div class="value" style="color:#d32f2f">{agg["total_bugs"]}</div><div class="label">Bugs</div></div>
  <div class="kpi-card"><div class="value" style="color:#2e7d32">{agg["total_enhancements"]}</div><div class="label">Enhancements</div></div>
  <div class="kpi-card"><div class="value" style="color:#7b1fa2">{agg["total_other"]}</div><div class="label">Other / Unlabeled</div></div>
  <div class="kpi-card"><div class="value" style="color:#e65100">{agg["total_overdue"]}</div><div class="label">Overdue Follow-ups</div></div>
  <div class="kpi-card"><div class="value" style="color:#0078D4">{repo_count}</div><div class="label">Repos Tracked</div></div>
</div>

<!-- Charts -->
<div class="charts-grid">
  <div class="card">
    <h2>Issues by Repository</h2>
    <canvas id="repoChart"></canvas>
  </div>
  <div class="card">
    <h2>Issue Type Distribution</h2>
    <canvas id="typeChart"></canvas>
  </div>
</div>

<!-- Repo Summary -->
<div class="card">
  <h2>Repository Summary</h2>
  <div class="table-scroll">
  <table>
    <thead><tr>
      <th>Accelerator</th><th style="text-align:center">Open</th><th style="text-align:center">Bugs</th>
      <th style="text-align:center">Enh.</th><th style="text-align:center">Other</th>
      <th style="text-align:center">Overdue</th><th style="text-align:center">Oldest</th>
      <th>Primary Owner</th><th>Secondary Owner</th>
    </tr></thead>
    <tbody>{repo_rows}</tbody>
  </table>
  </div>
</div>

<!-- Owner Workload -->
<div class="card">
  <h2>Owner Workload</h2>
  <table>
    <thead><tr><th>Owner</th><th style="text-align:center">Issues</th><th>Workload</th></tr></thead>
    <tbody>{owner_rows}</tbody>
  </table>
</div>

<!-- All Open Issues (top 50) -->
<div class="card">
  <h2>All Open Issues (Top 50 by Age)</h2>
  <div class="table-scroll">
  <table>
    <thead><tr>
      <th>Issue #</th><th>Accelerator</th><th>Title</th><th>Reported By</th><th>Labels</th><th style="text-align:center">Age</th>
    </tr></thead>
    <tbody>{issue_rows}</tbody>
  </table>
  </div>
</div>

</div><!-- /container -->

<div class="footer">Dashboard generated on {now_ist}</div>

<script>
// Stacked bar chart
new Chart(document.getElementById('repoChart'), {{{{
  type: 'bar',
  data: {{{{
    labels: {repo_names_js},
    datasets: [
      {{{{ label: 'Bugs', data: {bugs_js}, backgroundColor: '#d32f2f' }}}},
      {{{{ label: 'Enhancements', data: {enh_js}, backgroundColor: '#2e7d32' }}}},
      {{{{ label: 'Other', data: {other_js}, backgroundColor: '#757575' }}}}
    ]
  }}}},
  options: {{{{
    responsive: true,
    plugins: {{{{ legend: {{{{ position: 'top' }}}} }}}},
    scales: {{{{
      x: {{{{ stacked: true, ticks: {{{{ maxRotation: 45, minRotation: 25 }}}} }}}},
      y: {{{{ stacked: true, beginAtZero: true, ticks: {{{{ stepSize: 1 }}}} }}}}
    }}}}
  }}}}
}}}});
// Doughnut chart
new Chart(document.getElementById('typeChart'), {{{{
  type: 'doughnut',
  data: {{{{
    labels: ['Bugs', 'Enhancements', 'Other'],
    datasets: [{{{{
      data: [{agg["total_bugs"]}, {agg["total_enhancements"]}, {agg["total_other"]}],
      backgroundColor: ['#d32f2f', '#2e7d32', '#757575']
    }}}}]
  }}}},
  options: {{{{
    responsive: true,
    plugins: {{{{ legend: {{{{ position: 'bottom' }}}} }}}}
  }}}}
}}}});
</script>
</body>
</html>"""
    return html

# ─── main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  GitHub Issue Tracker – Dashboard Generator")
    print("=" * 60)

    # load state
    print(f"\n📂 Loading state file: {STATE_FILE}")
    state = load_state()

    # fetch issues from every repo
    repos_data: list[dict] = []
    for idx, cfg in enumerate(REPOS, 1):
        print(f"\n[{idx}/{len(REPOS)}] Fetching {cfg['owner']}/{cfg['repo']}…", end=" ", flush=True)
        issues = fetch_open_issues(cfg["owner"], cfg["repo"])
        print(f"→ {len(issues)} open issues")
        repos_data.append({"config": cfg, "issues": issues})

    # aggregate
    print("\n📊 Aggregating data…")
    agg = aggregate(repos_data, state)

    # generate HTML
    print("🖌  Generating HTML dashboard…")
    html = generate_html(agg)

    out_path = OUTPUT_HTML
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html)

    size_kb = os.path.getsize(out_path) / 1024
    print(f"\n✅ Dashboard written to {out_path} ({size_kb:.1f} KB)")
    print(f"   Total issues: {agg['total_issues']}  |  Bugs: {agg['total_bugs']}  |  Enhancements: {agg['total_enhancements']}  |  Overdue: {agg['total_overdue']}")
    now_ist = datetime.now(IST).strftime("%d %b %Y, %I:%M %p IST")
    print(f"   Generated at: {now_ist}")


if __name__ == "__main__":
    main()
