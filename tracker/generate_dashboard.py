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
        open_badge = f'<span class="badge badge-blue">{r["open"]}</span>' if r["open"] > 0 else '<span class="badge badge-green">0</span>'
        overdue_badge = (
            f'<span class="badge badge-red">{r["overdue"]}</span>'
            if r["overdue"] > 0
            else '<span class="badge badge-green">0</span>'
        )
        oldest_cls = "badge badge-red" if r["oldest_age"] > 30 else ("badge badge-orange" if r["oldest_age"] > 7 else "badge badge-gray")
        repo_rows += f"""<tr>
  <td><a href="{issues_url}" target="_blank">{r["name"]}</a></td>
  <td style="text-align:center">{open_badge}</td>
  <td style="text-align:center">{r["bugs"]}</td>
  <td style="text-align:center">{r["enhancements"]}</td>
  <td style="text-align:center">{r["other"]}</td>
  <td style="text-align:center">{overdue_badge}</td>
  <td style="text-align:center"><span class="{oldest_cls}">{r["oldest_age"]}d</span></td>
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
  <td style="text-align:center"><span class="badge badge-blue">{cnt}</span></td>
  <td><div class="bar-track"><div class="bar-fill" style="width:{max(bar_pct, 8)}%">{cnt}</div></div></td>
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
<title>GitHub Issue Tracker Dashboard — CSA Solutioning</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
  :root {{{{
    --blue: #0078D4; --blue-dark: #005a9e; --blue-light: #e8f4fd;
    --red: #D83B01; --red-bg: #FDE7E9;
    --green: #107C10; --green-bg: #DFF6DD;
    --orange: #FF8C00; --orange-bg: #FFF4CE;
    --purple: #8661C5; --purple-bg: #F3EFFC;
    --gray: #6B7280; --gray-bg: #F3F4F6;
    --bg: #F0F2F5; --card: #FFFFFF;
    --shadow: 0 1px 3px rgba(0,0,0,0.08), 0 4px 12px rgba(0,0,0,0.04);
    --shadow-hover: 0 4px 16px rgba(0,0,0,0.12);
    --radius: 12px;
  }}}}
  * {{{{ box-sizing: border-box; margin: 0; padding: 0; }}}}
  body {{{{ font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif; background: var(--bg); color: #1F2937; line-height: 1.5; }}}}

  /* ── Header ── */
  .header {{{{
    background: linear-gradient(135deg, #0078D4 0%, #005a9e 50%, #003d73 100%);
    color: white; padding: 36px 32px 28px; position: relative; overflow: hidden;
  }}}}
  .header::before {{{{
    content: ''; position: absolute; top: -50%; right: -20%; width: 500px; height: 500px;
    background: radial-gradient(circle, rgba(255,255,255,0.08) 0%, transparent 70%);
    border-radius: 50%;
  }}}}
  .header::after {{{{
    content: ''; position: absolute; bottom: -30%; left: -10%; width: 400px; height: 400px;
    background: radial-gradient(circle, rgba(255,255,255,0.05) 0%, transparent 70%);
    border-radius: 50%;
  }}}}
  .header-content {{{{ max-width: 1400px; margin: 0 auto; position: relative; z-index: 1; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; }}}}
  .header h1 {{{{ font-size: 1.75rem; font-weight: 800; letter-spacing: -0.02em; }}}}
  .header .subtitle {{{{ font-size: 0.9rem; opacity: 0.85; margin-top: 4px; font-weight: 400; }}}}
  .header .timestamp {{{{
    background: rgba(255,255,255,0.15); backdrop-filter: blur(8px);
    padding: 8px 16px; border-radius: 8px; font-size: 0.8rem; font-weight: 500;
    border: 1px solid rgba(255,255,255,0.2);
  }}}}

  /* ── Container ── */
  .container {{{{ max-width: 1400px; margin: 0 auto; padding: 24px 20px; }}}}

  /* ── KPI Cards ── */
  .kpi-grid {{{{ display: grid; grid-template-columns: repeat(6, 1fr); gap: 16px; margin-bottom: 28px; }}}}
  @media (max-width: 1100px) {{{{ .kpi-grid {{{{ grid-template-columns: repeat(3, 1fr); }}}} }}}}
  @media (max-width: 600px) {{{{ .kpi-grid {{{{ grid-template-columns: repeat(2, 1fr); }}}} }}}}
  .kpi-card {{{{
    background: var(--card); border-radius: var(--radius); box-shadow: var(--shadow);
    padding: 20px; text-align: center; transition: transform 0.2s, box-shadow 0.2s;
    border-top: 3px solid transparent; position: relative; overflow: hidden;
  }}}}
  .kpi-card:hover {{{{ transform: translateY(-2px); box-shadow: var(--shadow-hover); }}}}
  .kpi-card .icon {{{{ font-size: 1.5rem; margin-bottom: 6px; }}}}
  .kpi-card .value {{{{ font-size: 2.2rem; font-weight: 800; letter-spacing: -0.02em; }}}}
  .kpi-card .label {{{{ font-size: 0.78rem; color: var(--gray); margin-top: 2px; font-weight: 500; text-transform: uppercase; letter-spacing: 0.04em; }}}}
  .kpi-blue {{{{ border-top-color: var(--blue); }}}} .kpi-blue .value {{{{ color: var(--blue); }}}}
  .kpi-red {{{{ border-top-color: var(--red); }}}} .kpi-red .value {{{{ color: var(--red); }}}}
  .kpi-green {{{{ border-top-color: var(--green); }}}} .kpi-green .value {{{{ color: var(--green); }}}}
  .kpi-purple {{{{ border-top-color: var(--purple); }}}} .kpi-purple .value {{{{ color: var(--purple); }}}}
  .kpi-orange {{{{ border-top-color: var(--orange); }}}} .kpi-orange .value {{{{ color: var(--orange); }}}}

  /* ── Cards ── */
  .card {{{{
    background: var(--card); border-radius: var(--radius); box-shadow: var(--shadow);
    padding: 24px; margin-bottom: 24px;
  }}}}
  .card h2 {{{{
    font-size: 1.05rem; font-weight: 700; color: #1F2937; margin-bottom: 16px;
    display: flex; align-items: center; gap: 8px;
  }}}}
  .card h2 .icon {{{{ font-size: 1.2rem; }}}}
  .card h2 .accent {{{{ width: 4px; height: 20px; background: var(--blue); border-radius: 2px; }}}}

  /* ── Charts ── */
  .charts-grid {{{{ display: grid; grid-template-columns: 1.8fr 1fr; gap: 24px; margin-bottom: 24px; }}}}
  @media (max-width: 900px) {{{{ .charts-grid {{{{ grid-template-columns: 1fr; }}}} }}}}
  .chart-wrap canvas {{{{ max-height: 320px; }}}}

  /* ── Tables ── */
  .table-scroll {{{{ overflow-x: auto; }}}}
  table {{{{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}}}
  thead th {{{{
    position: sticky; top: 0; background: #F9FAFB; text-align: left;
    padding: 12px 10px; border-bottom: 2px solid #E5E7EB; font-weight: 600;
    color: #4B5563; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.04em;
    white-space: nowrap;
  }}}}
  tbody td {{{{ padding: 10px; border-bottom: 1px solid #F3F4F6; vertical-align: middle; }}}}
  tbody tr {{{{ transition: background 0.15s; }}}}
  tbody tr:hover {{{{ background: #F0F7FF; }}}}
  .title-col {{{{ max-width: 350px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}}}
  a {{{{ color: var(--blue); text-decoration: none; font-weight: 500; }}}}
  a:hover {{{{ text-decoration: underline; }}}}

  /* ── Badges ── */
  .badge {{{{ display: inline-block; padding: 3px 10px; border-radius: 20px; font-size: 0.75rem; font-weight: 600; white-space: nowrap; }}}}
  .badge-blue {{{{ background: var(--blue-light); color: var(--blue); }}}}
  .badge-red {{{{ background: var(--red-bg); color: var(--red); }}}}
  .badge-green {{{{ background: var(--green-bg); color: var(--green); }}}}
  .badge-orange {{{{ background: var(--orange-bg); color: var(--orange); }}}}
  .badge-purple {{{{ background: var(--purple-bg); color: var(--purple); }}}}
  .badge-gray {{{{ background: var(--gray-bg); color: var(--gray); }}}}

  /* ── Workload bar ── */
  .bar-track {{{{ background: #E5E7EB; border-radius: 6px; overflow: hidden; height: 24px; }}}}
  .bar-fill {{{{ height: 100%; border-radius: 6px; background: linear-gradient(90deg, #0078D4, #40A9FF); transition: width 0.6s ease; display: flex; align-items: center; padding-left: 8px; color: white; font-size: 0.75rem; font-weight: 600; min-width: 30px; }}}}

  /* ── Search ── */
  .search-box {{{{
    display: flex; align-items: center; gap: 8px; margin-bottom: 16px;
    background: #F9FAFB; border: 1px solid #E5E7EB; border-radius: 8px; padding: 8px 14px;
  }}}}
  .search-box input {{{{
    border: none; background: transparent; outline: none; font-size: 0.9rem;
    font-family: inherit; flex: 1; color: #1F2937;
  }}}}
  .search-box .icon {{{{ color: #9CA3AF; font-size: 1rem; }}}}

  /* ── Footer ── */
  .footer {{{{ text-align: center; color: #9CA3AF; font-size: 0.78rem; padding: 32px 0 24px; }}}}
  .footer a {{{{ color: var(--blue); }}}}

  /* ── Animations ── */
  @keyframes fadeInUp {{{{ from {{{{ opacity: 0; transform: translateY(16px); }}}} to {{{{ opacity: 1; transform: translateY(0); }}}} }}}}
  .kpi-card, .card {{{{ animation: fadeInUp 0.4s ease both; }}}}
  .kpi-card:nth-child(1) {{{{ animation-delay: 0.05s; }}}}
  .kpi-card:nth-child(2) {{{{ animation-delay: 0.1s; }}}}
  .kpi-card:nth-child(3) {{{{ animation-delay: 0.15s; }}}}
  .kpi-card:nth-child(4) {{{{ animation-delay: 0.2s; }}}}
  .kpi-card:nth-child(5) {{{{ animation-delay: 0.25s; }}}}
  .kpi-card:nth-child(6) {{{{ animation-delay: 0.3s; }}}}
</style>
</head>
<body>

<div class="header">
  <div class="header-content">
    <div>
      <h1>\U0001f4ca GitHub Issue Tracker Dashboard</h1>
      <div class="subtitle">CSA Solutioning \u2014 Tracking {repo_count} Repositories Across microsoft &amp; Azure-Samples</div>
    </div>
    <div class="timestamp">\U0001f552 {now_ist}</div>
  </div>
</div>

<div class="container">

<!-- KPI Cards -->
<div class="kpi-grid">
  <div class="kpi-card kpi-blue">
    <div class="icon">\U0001f4cb</div>
    <div class="value">{agg["total_issues"]}</div>
    <div class="label">Open Issues</div>
  </div>
  <div class="kpi-card kpi-red">
    <div class="icon">\U0001f41b</div>
    <div class="value">{agg["total_bugs"]}</div>
    <div class="label">Bugs</div>
  </div>
  <div class="kpi-card kpi-green">
    <div class="icon">\u2728</div>
    <div class="value">{agg["total_enhancements"]}</div>
    <div class="label">Enhancements</div>
  </div>
  <div class="kpi-card kpi-purple">
    <div class="icon">\U0001f4e6</div>
    <div class="value">{agg["total_other"]}</div>
    <div class="label">Other</div>
  </div>
  <div class="kpi-card kpi-orange">
    <div class="icon">\u26a0\ufe0f</div>
    <div class="value">{agg["total_overdue"]}</div>
    <div class="label">Overdue</div>
  </div>
  <div class="kpi-card kpi-blue">
    <div class="icon">\U0001f4c1</div>
    <div class="value">{repo_count}</div>
    <div class="label">Repos</div>
  </div>
</div>

<!-- Charts -->
<div class="charts-grid">
  <div class="card chart-wrap">
    <h2><div class="accent"></div> Issues by Repository</h2>
    <canvas id="repoChart"></canvas>
  </div>
  <div class="card chart-wrap">
    <h2><div class="accent"></div> Type Distribution</h2>
    <canvas id="typeChart"></canvas>
  </div>
</div>

<!-- Repo Summary -->
<div class="card">
  <h2><div class="accent"></div> Repository Summary</h2>
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
  <h2><div class="accent"></div> Owner Workload</h2>
  <table>
    <thead><tr><th>Owner</th><th style="text-align:center;width:80px">Issues</th><th>Workload Distribution</th></tr></thead>
    <tbody>{owner_rows}</tbody>
  </table>
</div>

<!-- All Open Issues -->
<div class="card">
  <h2><div class="accent"></div> All Open Issues <span style="font-weight:400;font-size:0.85rem;color:#9CA3AF;margin-left:8px">(Top 50 by Age)</span></h2>
  <div class="search-box">
    <span class="icon">\U0001f50d</span>
    <input type="text" id="issueSearch" placeholder="Search issues by title, accelerator, or reporter..." onkeyup="filterIssues()">
  </div>
  <div class="table-scroll">
  <table id="issueTable">
    <thead><tr>
      <th>Issue #</th><th>Accelerator</th><th>Title</th><th>Reported By</th><th>Labels</th><th style="text-align:center">Age</th>
    </tr></thead>
    <tbody>{issue_rows}</tbody>
  </table>
  </div>
</div>

</div><!-- /container -->

<div class="footer">
  GitHub Issue Tracker Dashboard \u2022 Auto-generated on {now_ist} \u2022 CSA Solutioning<br>
  <span style="font-size:0.7rem;color:#C0C0C0">Refreshes every 30 minutes via GitHub Actions \u2022 Powered by GitHub Pages</span>
</div>

<script>
// ── Search/filter ──
function filterIssues() {{{{
  const q = document.getElementById('issueSearch').value.toLowerCase();
  const rows = document.querySelectorAll('#issueTable tbody tr');
  rows.forEach(r => {{{{ r.style.display = r.textContent.toLowerCase().includes(q) ? '' : 'none'; }}}});
}}}}

// ── Charts ──
Chart.defaults.font.family = "'Inter', 'Segoe UI', sans-serif";
Chart.defaults.font.size = 12;

new Chart(document.getElementById('repoChart'), {{{{
  type: 'bar',
  data: {{{{
    labels: {repo_names_js},
    datasets: [
      {{{{ label: 'Bugs', data: {bugs_js}, backgroundColor: 'rgba(216,59,1,0.85)', borderRadius: 4 }}}},
      {{{{ label: 'Enhancements', data: {enh_js}, backgroundColor: 'rgba(16,124,16,0.85)', borderRadius: 4 }}}},
      {{{{ label: 'Other', data: {other_js}, backgroundColor: 'rgba(107,114,128,0.6)', borderRadius: 4 }}}}
    ]
  }}}},
  options: {{{{
    responsive: true, maintainAspectRatio: true,
    plugins: {{{{ legend: {{{{ position: 'top', labels: {{{{ usePointStyle: true, padding: 16 }}}} }}}} }}}},
    scales: {{{{
      x: {{{{ stacked: true, ticks: {{{{ maxRotation: 40, minRotation: 20, font: {{{{ size: 11 }}}} }}}}, grid: {{{{ display: false }}}} }}}},
      y: {{{{ stacked: true, beginAtZero: true, ticks: {{{{ stepSize: 1 }}}}, grid: {{{{ color: '#F3F4F6' }}}} }}}}
    }}}}
  }}}}
}}}});

new Chart(document.getElementById('typeChart'), {{{{
  type: 'doughnut',
  data: {{{{
    labels: ['Bugs', 'Enhancements', 'Other'],
    datasets: [{{{{
      data: [{agg["total_bugs"]}, {agg["total_enhancements"]}, {agg["total_other"]}],
      backgroundColor: ['#D83B01', '#107C10', '#6B7280'],
      borderWidth: 0, hoverOffset: 8
    }}}}]
  }}}},
  options: {{{{
    responsive: true, maintainAspectRatio: true,
    cutout: '65%',
    plugins: {{{{
      legend: {{{{ position: 'bottom', labels: {{{{ usePointStyle: true, padding: 16 }}}} }}}}
    }}}}
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
