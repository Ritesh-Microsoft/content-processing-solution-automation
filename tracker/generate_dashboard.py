"""
GitHub Issue Tracker Dashboard — Cloud Edition
Generates the same dashboard as the local version, using GitHub REST API instead of gh CLI.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

IST = timezone(timedelta(hours=5, minutes=30))

SCRIPT_DIR = Path(__file__).parent
STATE_FILE = Path(os.environ.get("STATE_FILE", SCRIPT_DIR / "state" / "tracked_issues_state.json"))
OUTPUT_HTML = Path(os.environ.get("OUTPUT_HTML", SCRIPT_DIR / "dashboard.html"))

REPOS = [
    {"name": "Customer Chatbot", "owner": "microsoft", "repo": "customer-chatbot-solution-accelerator",
     "primary": "Ajit Padhi", "secondary": "Prajwal D C"},
    {"name": "Code Modernization", "owner": "microsoft", "repo": "Modernize-your-code-solution-accelerator",
     "primary": "Priyanka Singhal", "secondary": "Shreyas Waikar"},
    {"name": "Container Migration", "owner": "microsoft", "repo": "Container-Migration-Solution-Accelerator",
     "primary": "Shreyas Waikar", "secondary": "Priyanka Singhal"},
    {"name": "Content Generation", "owner": "microsoft", "repo": "content-generation-solution-accelerator",
     "primary": "Ragini Chauragade", "secondary": "Pavan Kumar"},
    {"name": "Content Processing", "owner": "microsoft", "repo": "content-processing-solution-accelerator",
     "primary": "Shreyas Waikar", "secondary": "Ajit Padhi"},
    {"name": "CWYD", "owner": "Azure-Samples", "repo": "chat-with-your-data-solution-accelerator",
     "primary": "Ajit Padhi", "secondary": "Priyanka Singhal"},
    {"name": "Data & Agent Governance", "owner": "microsoft", "repo": "Data-and-Agent-Governance-and-Security-Accelerator",
     "primary": "Saswato Chatterjee", "secondary": "Yamini"},
    {"name": "Deploy AI App", "owner": "microsoft", "repo": "Deploy-Your-AI-Application-In-Production",
     "primary": "Saswato Chatterjee", "secondary": "Yamini"},
    {"name": "DKM", "owner": "microsoft", "repo": "Document-Knowledge-Mining-Solution-Accelerator",
     "primary": "Priyanka Singhal", "secondary": "Ajit Padhi"},
    {"name": "Agentic App", "owner": "microsoft", "repo": "agentic-applications-for-unified-data-foundation-solution-accelerator",
     "primary": "Ragini Chauragade", "secondary": "Pavan Kumar"},
    {"name": "KM Generic", "owner": "microsoft", "repo": "Conversation-Knowledge-Mining-Solution-Accelerator",
     "primary": "Pavan Kumar", "secondary": "Avijit Ghorui"},
    {"name": "UDF", "owner": "microsoft", "repo": "unified-data-foundation-with-fabric-solution-accelerator",
     "primary": "Saswato Chatterjee", "secondary": "Yamini"},
    {"name": "MACAE", "owner": "microsoft", "repo": "Multi-Agent-Custom-Automation-Engine-Solution-Accelerator",
     "primary": "Dhruvkumar Babariya", "secondary": "Abdul Mujeeb T A"},
    {"name": "RTI", "owner": "microsoft", "repo": "real-time-intelligence-operations-solution-accelerator",
     "primary": "Saswato Chatterjee", "secondary": "Yamini"},
]


def _gh_headers():
    token = os.environ.get("GITHUB_TOKEN", "")
    h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def fetch_live_issues(owner, repo):
    """Fetch open issues (not PRs) via GitHub REST API with pagination."""
    issues = []
    page = 1
    for _ in range(20):  # safety limit
        try:
            r = requests.get(
                f"https://api.github.com/repos/{owner}/{repo}/issues",
                params={"state": "open", "per_page": 100, "page": page},
                headers=_gh_headers(), timeout=30,
            )
            if r.status_code == 403:
                print(f"  Rate limited, waiting...")
                time.sleep(10)
                continue
            r.raise_for_status()
            batch = r.json()
            if not batch:
                break
            for item in batch:
                if item.get("pull_request") is None:
                    issues.append({
                        "number": item["number"],
                        "title": item["title"],
                        "html_url": item["html_url"],
                        "created_at": item["created_at"],
                        "user": item["user"]["login"],
                        "labels": [l["name"] for l in item.get("labels", [])],
                    })
            if len(batch) < 100:
                break
            page += 1
        except Exception as e:
            print(f"  Error: {e}")
            return issues
    return issues


def load_state():
    if STATE_FILE.exists():
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def generate_dashboard():
    print("Generating GitHub Issue Tracker Dashboard...")
    state = load_state()
    now = datetime.now(timezone.utc)
    generated_at = datetime.now(IST).strftime("%d-%b-%Y %I:%M %p IST")

    repo_data = []
    total_open = 0
    total_overdue = 0
    total_bug = 0
    total_enhancement = 0
    total_other = 0
    all_issues = []

    for repo_cfg in REPOS:
        owner = repo_cfg["owner"]
        repo = repo_cfg["repo"]
        name = repo_cfg["name"]
        repo_key = f"{owner}/{repo}"
        repo_url = f"https://github.com/{repo_key}"

        print(f"  Fetching: {name}...")
        issues = fetch_live_issues(owner, repo)
        if issues is None:
            issues = []

        repo_state = state.get(repo_key, {})
        issue_details = repo_state.get("issue_details", {})
        last_checked = repo_state.get("last_checked", "N/A")

        bugs = [i for i in issues if "bug" in [l.lower() for l in i.get("labels", [])]]
        enhancements = [i for i in issues if "enhancement" in [l.lower() for l in i.get("labels", [])]]
        others = [i for i in issues if i not in bugs and i not in enhancements]

        overdue = 0
        for num_str, det in issue_details.items():
            if not det.get("followup_found", False):
                first_seen = datetime.fromisoformat(det["first_seen"])
                if (now - first_seen).days >= 2:
                    overdue += 1

        oldest_days = 0
        if issues:
            oldest_created = min(i["created_at"] for i in issues)
            try:
                oldest_dt = datetime.fromisoformat(oldest_created.replace("Z", "+00:00"))
                oldest_days = (now - oldest_dt).days
            except Exception:
                pass

        total_open += len(issues)
        total_overdue += overdue
        total_bug += len(bugs)
        total_enhancement += len(enhancements)
        total_other += len(others)

        for i in issues:
            i["_accel"] = name
            i["_repo_url"] = repo_url
            age = 0
            try:
                age = (now - datetime.fromisoformat(i["created_at"].replace("Z", "+00:00"))).days
            except Exception:
                pass
            i["_age_days"] = age
        all_issues.extend(issues)

        repo_data.append({
            "name": name,
            "repo_key": repo_key,
            "repo_url": repo_url,
            "primary": repo_cfg["primary"],
            "secondary": repo_cfg["secondary"],
            "open_count": len(issues),
            "bug_count": len(bugs),
            "enhancement_count": len(enhancements),
            "other_count": len(others),
            "overdue": overdue,
            "oldest_days": oldest_days,
            "last_checked": last_checked[:19] if last_checked != "N/A" else "N/A",
        })

    all_issues.sort(key=lambda i: i.get("_age_days", 0), reverse=True)

    html = _build_html(repo_data, all_issues, total_open, total_overdue,
                       total_bug, total_enhancement, total_other, generated_at)

    OUTPUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\nDashboard generated: {OUTPUT_HTML}")
    print(f"  Total: {total_open} open | {total_bug} bugs | {total_enhancement} enh | {total_overdue} overdue")


def _build_html(repo_data, all_issues, total_open, total_overdue,
                total_bug, total_enhancement, total_other, generated_at):
    # Build repo rows
    repo_rows = ""
    for r in repo_data:
        overdue_badge = f'<span class="badge badge-red">{r["overdue"]}</span>' if r["overdue"] > 0 else '<span class="badge badge-green">0</span>'
        open_badge = f'<span class="badge badge-blue">{r["open_count"]}</span>' if r["open_count"] > 0 else '<span class="badge badge-green">0</span>'
        repo_rows += f"""
        <tr>
            <td><a href="{r['repo_url']}/issues" target="_blank">{r['name']}</a></td>
            <td class="center">{open_badge}</td>
            <td class="center">{r['bug_count']}</td>
            <td class="center">{r['enhancement_count']}</td>
            <td class="center">{r['other_count']}</td>
            <td class="center">{overdue_badge}</td>
            <td class="center">{r['oldest_days']}d</td>
            <td>{r['primary']}</td>
            <td>{r['secondary']}</td>
        </tr>"""

    # Build all issues rows (top 50)
    issue_rows = ""
    for i in all_issues[:50]:
        labels = ", ".join(i.get("labels", [])) or "\u2014"
        label_class = "label-bug" if "bug" in labels.lower() else ("label-enhancement" if "enhancement" in labels.lower() else "label-other")
        age_class = "age-red" if i["_age_days"] > 7 else ("age-yellow" if i["_age_days"] > 2 else "age-green")
        issue_rows += f"""
        <tr>
            <td><a href="{i['html_url']}" target="_blank">#{i['number']}</a></td>
            <td>{i['_accel']}</td>
            <td class="title-col">{i['title'][:80]}</td>
            <td>{i.get('user', 'N/A')}</td>
            <td><span class="{label_class}">{labels}</span></td>
            <td class="center {age_class}">{i['_age_days']}d</td>
        </tr>"""

    # Owner workload
    owner_counts = {}
    for r in repo_data:
        p = r["primary"]
        owner_counts[p] = owner_counts.get(p, 0) + r["open_count"]

    owner_rows = ""
    for owner, count in sorted(owner_counts.items(), key=lambda x: -x[1]):
        bar_width = min(count * 15, 300)
        owner_rows += f"""
        <tr>
            <td>{owner}</td>
            <td class="center">{count}</td>
            <td><div class="bar" style="width:{bar_width}px"></div></td>
        </tr>"""

    # Chart data for JS
    repo_names_js = json.dumps([r["name"] for r in repo_data])
    bugs_js = json.dumps([r["bug_count"] for r in repo_data])
    enhancements_js = json.dumps([r["enhancement_count"] for r in repo_data])
    others_js = json.dumps([r["other_count"] for r in repo_data])

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GitHub Issue Tracker Dashboard</title>
<style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f0f2f5; color: #333; }}
    .header {{ background: linear-gradient(135deg, #0078D4, #005a9e); color: white; padding: 20px 30px; }}
    .header h1 {{ font-size: 24px; font-weight: 600; }}
    .header .subtitle {{ font-size: 13px; opacity: 0.8; margin-top: 4px; }}
    .container {{ max-width: 1400px; margin: 0 auto; padding: 20px; }}

    /* KPI Cards */
    .kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin-bottom: 24px; }}
    .kpi-card {{ background: white; border-radius: 8px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); text-align: center; }}
    .kpi-card .value {{ font-size: 36px; font-weight: 700; }}
    .kpi-card .label {{ font-size: 13px; color: #666; margin-top: 4px; }}
    .kpi-blue .value {{ color: #0078D4; }}
    .kpi-red .value {{ color: #D83B01; }}
    .kpi-green .value {{ color: #107C10; }}
    .kpi-orange .value {{ color: #FF8C00; }}
    .kpi-purple .value {{ color: #8661C5; }}

    /* Sections */
    .section {{ background: white; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
    .section h2 {{ font-size: 18px; font-weight: 600; margin-bottom: 12px; color: #0078D4; border-bottom: 2px solid #0078D4; padding-bottom: 6px; }}

    /* Tables */
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th {{ background: #f5f5f5; padding: 10px 8px; text-align: left; font-weight: 600; border-bottom: 2px solid #ddd; position: sticky; top: 0; }}
    td {{ padding: 8px; border-bottom: 1px solid #eee; }}
    tr:hover {{ background: #f8f9fa; }}
    .center {{ text-align: center; }}
    .title-col {{ max-width: 400px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    a {{ color: #0078D4; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}

    /* Badges */
    .badge {{ display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; }}
    .badge-red {{ background: #FDE7E9; color: #D83B01; }}
    .badge-green {{ background: #DFF6DD; color: #107C10; }}
    .badge-blue {{ background: #E1F0FF; color: #0078D4; }}
    .badge-yellow {{ background: #FFF4CE; color: #7A6400; }}

    /* Labels */
    .label-bug {{ background: #FDE7E9; color: #D83B01; padding: 2px 8px; border-radius: 4px; font-size: 11px; }}
    .label-enhancement {{ background: #DFF6DD; color: #107C10; padding: 2px 8px; border-radius: 4px; font-size: 11px; }}
    .label-other {{ background: #f0f0f0; color: #666; padding: 2px 8px; border-radius: 4px; font-size: 11px; }}

    /* Age colors */
    .age-red {{ color: #D83B01; font-weight: 700; }}
    .age-yellow {{ color: #FF8C00; font-weight: 600; }}
    .age-green {{ color: #107C10; }}

    /* Bar chart */
    .bar {{ background: linear-gradient(90deg, #0078D4, #40A9FF); height: 18px; border-radius: 4px; min-width: 4px; }}

    /* Chart container */
    .chart-container {{ display: grid; grid-template-columns: 2fr 1fr; gap: 20px; margin-bottom: 20px; }}
    .chart-canvas {{ max-height: 300px; }}

    /* Responsive */
    @media (max-width: 900px) {{
        .chart-container {{ grid-template-columns: 1fr; }}
        .kpi-grid {{ grid-template-columns: repeat(3, 1fr); }}
    }}

    .footer {{ text-align: center; color: #999; font-size: 11px; padding: 16px; }}
</style>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
</head>
<body>

<div class="header">
    <h1>GitHub Issue Tracker Dashboard</h1>
    <div class="subtitle">CSA Solutioning \u2014 {len(repo_data)} Repositories | Generated: {generated_at}</div>
</div>

<div class="container">

    <!-- KPI Cards -->
    <div class="kpi-grid">
        <div class="kpi-card kpi-blue">
            <div class="value">{total_open}</div>
            <div class="label">Total Open Issues</div>
        </div>
        <div class="kpi-card kpi-red">
            <div class="value">{total_bug}</div>
            <div class="label">Bugs</div>
        </div>
        <div class="kpi-card kpi-green">
            <div class="value">{total_enhancement}</div>
            <div class="label">Enhancements</div>
        </div>
        <div class="kpi-card kpi-purple">
            <div class="value">{total_other}</div>
            <div class="label">Other / Unlabeled</div>
        </div>
        <div class="kpi-card kpi-orange">
            <div class="value">{total_overdue}</div>
            <div class="label">Overdue Follow-ups</div>
        </div>
        <div class="kpi-card kpi-blue">
            <div class="value">{len(repo_data)}</div>
            <div class="label">Repos Tracked</div>
        </div>
    </div>

    <!-- Charts -->
    <div class="chart-container">
        <div class="section">
            <h2>Issues by Repository</h2>
            <canvas id="repoChart" class="chart-canvas"></canvas>
        </div>
        <div class="section">
            <h2>Issue Type Distribution</h2>
            <canvas id="typeChart" class="chart-canvas"></canvas>
        </div>
    </div>

    <!-- Repo Summary Table -->
    <div class="section">
        <h2>Repository Summary</h2>
        <table>
            <thead>
                <tr>
                    <th>Accelerator</th>
                    <th class="center">Open</th>
                    <th class="center">Bugs</th>
                    <th class="center">Enhancements</th>
                    <th class="center">Other</th>
                    <th class="center">Overdue</th>
                    <th class="center">Oldest</th>
                    <th>Primary Owner</th>
                    <th>Secondary Owner</th>
                </tr>
            </thead>
            <tbody>{repo_rows}</tbody>
        </table>
    </div>

    <!-- Owner Workload -->
    <div class="section">
        <h2>Owner Workload (Open Issues by Primary Owner)</h2>
        <table>
            <thead>
                <tr><th>Owner</th><th class="center">Issues</th><th>Distribution</th></tr>
            </thead>
            <tbody>{owner_rows}</tbody>
        </table>
    </div>

    <!-- All Open Issues -->
    <div class="section">
        <h2>All Open Issues (Top 50 by Age)</h2>
        <table>
            <thead>
                <tr>
                    <th>Issue #</th>
                    <th>Accelerator</th>
                    <th>Title</th>
                    <th>Reported By</th>
                    <th>Labels</th>
                    <th class="center">Age</th>
                </tr>
            </thead>
            <tbody>{issue_rows}</tbody>
        </table>
    </div>

</div>

<div class="footer">
    GitHub Issue Tracker Dashboard | Auto-generated on {generated_at} | CSA Solutioning
</div>

<script>
// Repo bar chart
new Chart(document.getElementById('repoChart'), {{
    type: 'bar',
    data: {{
        labels: {repo_names_js},
        datasets: [
            {{ label: 'Bugs', data: {bugs_js}, backgroundColor: '#D83B01' }},
            {{ label: 'Enhancements', data: {enhancements_js}, backgroundColor: '#107C10' }},
            {{ label: 'Other', data: {others_js}, backgroundColor: '#0078D4' }}
        ]
    }},
    options: {{
        responsive: true,
        plugins: {{ legend: {{ position: 'bottom' }} }},
        scales: {{
            x: {{ ticks: {{ maxRotation: 45, font: {{ size: 10 }} }} }},
            y: {{ beginAtZero: true, ticks: {{ stepSize: 1 }} }}
        }}
    }}
}});

// Type donut chart
new Chart(document.getElementById('typeChart'), {{
    type: 'doughnut',
    data: {{
        labels: ['Bugs', 'Enhancements', 'Other'],
        datasets: [{{
            data: [{total_bug}, {total_enhancement}, {total_other}],
            backgroundColor: ['#D83B01', '#107C10', '#0078D4']
        }}]
    }},
    options: {{
        responsive: true,
        plugins: {{ legend: {{ position: 'bottom' }} }}
    }}
}});
</script>

</body>
</html>"""


if __name__ == "__main__":
    generate_dashboard()
