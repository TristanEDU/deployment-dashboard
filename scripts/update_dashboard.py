#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

API = "https://api.github.com"
STATUS_EMOJI = {
    "success": "✅",
    "failure": "❌",
    "error": "⚠️",
    "in_progress": "🔄",
    "pending": "⏳",
    "queued": "📋",
    "inactive": "⏸️",
}


@dataclass
class DeploymentRow:
    repo: str
    full_repo: str
    environment: str
    ref: str
    sha: str
    created_at: str
    status: str
    dashboard_url: str
    source_url: str
    status_description: str


def request_json(url: str, headers: Dict[str, str], params: Optional[Dict[str, Any]] = None) -> tuple[list[Any], Dict[str, str]]:
    query = urllib.parse.urlencode(params or {})
    full_url = f"{url}?{query}" if query else url
    request = urllib.request.Request(full_url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read().decode("utf-8")
        link_header = response.headers.get("Link", "")
    return json.loads(body), parse_link_header(link_header)


def parse_link_header(value: str) -> Dict[str, str]:
    links: Dict[str, str] = {}
    for part in value.split(","):
        section = part.strip()
        if not section or ";" not in section:
            continue
        url_part, rel_part = section.split(";", 1)
        url = url_part.strip().removeprefix("<").removesuffix(">")
        rel = rel_part.strip().replace('rel="', "").replace('"', "")
        links[rel] = url
    return links


def paged_get(url: str, headers: Dict[str, str], params: Optional[Dict[str, Any]] = None) -> Iterable[Dict[str, Any]]:
    page = 1
    base_params = dict(params or {})
    while True:
        merged_params = {**base_params, "per_page": 100, "page": page}
        items, links = request_json(url, headers, merged_params)
        if not items:
            break
        for item in items:
            yield item
        if "next" not in links:
            break
        page += 1


def latest_status(
    full_repo: str,
    deployment_id: int,
    headers: Dict[str, str],
) -> Dict[str, Any]:
    statuses, _ = request_json(
        f"{API}/repos/{full_repo}/deployments/{deployment_id}/statuses",
        headers,
        params={"per_page": 1, "page": 1},
    )
    return statuses[0] if statuses else {}


def deployment_target_url(deployment: Dict[str, Any], status: Dict[str, Any], repo_html_url: str) -> tuple[str, str]:
    payload = deployment.get("payload") if isinstance(deployment.get("payload"), dict) else {}
    environment_url = status.get("environment_url")
    target_url = status.get("target_url")
    payload_url = payload.get("web_url") or payload.get("url")

    for candidate in (environment_url, target_url, payload_url):
        if isinstance(candidate, str) and candidate.strip():
            return candidate, "deployment"

    return repo_html_url, "repository"


def fetch_deployments(token: str) -> List[DeploymentRow]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "deployment-dashboard-updater",
    }

    repos = list(
        paged_get(
            f"{API}/user/repos",
            headers,
            params={"affiliation": "owner,organization_member,collaborator", "sort": "full_name"},
        )
    )

    latest_by_environment: Dict[tuple[str, str], DeploymentRow] = {}
    for repo in repos:
        full_name = repo["full_name"]
        html_url = repo.get("html_url", f"https://github.com/{full_name}")

        # Limit to recent deployments; this keeps the scheduled workflow fast and reliably up-to-date.
        for deployment in paged_get(
            f"{API}/repos/{full_name}/deployments",
            headers,
            params={"per_page": 20},
        ):
            dep_id = deployment["id"]
            latest = latest_status(full_name, dep_id, headers)
            dashboard_url, source = deployment_target_url(deployment, latest, html_url)

            row = DeploymentRow(
                repo=repo["name"],
                full_repo=full_name,
                environment=deployment.get("environment") or "N/A",
                ref=str(deployment.get("ref") or "N/A"),
                sha=str(deployment.get("sha") or "")[:7],
                created_at=deployment.get("created_at") or "",
                status=latest.get("state") or "unknown",
                dashboard_url=dashboard_url,
                source_url=source,
                status_description=latest.get("description") or "",
            )

            key = (full_name.lower(), row.environment.lower())
            previous = latest_by_environment.get(key)
            if previous is None or row.created_at > previous.created_at:
                latest_by_environment[key] = row

    deployments = list(latest_by_environment.values())
    deployments.sort(key=lambda d: (d.full_repo.lower(), d.environment.lower(), d.created_at))
    return deployments


def fmt_time(value: str) -> str:
    if not value:
        return "N/A"
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return value


def render_readme(rows: List[DeploymentRow], generated_at: str) -> str:
    lines = [
        "# 🚀 Deployment Dashboard",
        "",
        f"Last updated: **{generated_at}**",
        "",
        "## Deployments",
        "",
    ]
    if not rows:
        lines.append("_No deployments found for repositories visible to this token._")
        return "\n".join(lines) + "\n"

    lines.extend(
        [
            "| Repository | Environment | Status | Ref | Commit | Created | Links |",
            "|---|---|---|---|---|---|---|",
        ]
    )

    for row in rows:
        emoji = STATUS_EMOJI.get(row.status, "❓")
        repo_link = f"[{row.full_repo}](https://github.com/{row.full_repo})"
        status_text = f"{emoji} {row.status}"
        link_text = "deployment" if row.source_url == "deployment" else "repository"
        link = f"[{link_text}]({row.dashboard_url})" if row.dashboard_url else "-"
        lines.append(
            f"| {repo_link} | {row.environment} | {status_text} | `{row.ref}` | `{row.sha or 'N/A'}` | {fmt_time(row.created_at)} | {link} |"
        )

    return "\n".join(lines) + "\n"


def render_html(rows: List[DeploymentRow], generated_at: str) -> str:
    source_label = {"deployment": "Open deployment", "repository": "Open repository"}
    cards = []
    for row in rows:
        emoji = STATUS_EMOJI.get(row.status, "❓")
        status_class = row.status.replace("_", "-")
        action_text = source_label.get(row.source_url, "Open link")
        cards.append(
            f"""
      <article class=\"card\">
        <header class=\"card-header\">
          <h2><a href=\"https://github.com/{html.escape(row.full_repo)}\" target=\"_blank\" rel=\"noreferrer\">{html.escape(row.full_repo)}</a></h2>
          <span class=\"status {html.escape(status_class)}\">{emoji} {html.escape(row.status)}</span>
        </header>
        <dl class=\"meta\">
          <div><dt>Environment</dt><dd>{html.escape(row.environment)}</dd></div>
          <div><dt>Branch/Ref</dt><dd class=\"break\">{html.escape(row.ref)}</dd></div>
          <div><dt>Commit</dt><dd><code>{html.escape(row.sha or 'N/A')}</code></dd></div>
          <div><dt>Created</dt><dd>{html.escape(fmt_time(row.created_at))}</dd></div>
        </dl>
        <p class=\"card-action\"><a href=\"{html.escape(row.dashboard_url)}\" target=\"_blank\" rel=\"noreferrer\">{action_text}</a></p>
      </article>
            """.strip()
        )

    cards_html = "\n".join(cards) if cards else '<p class="empty">No deployments found for repositories visible to this token.</p>'
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Deployment Dashboard</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #060913;
      --panel: #0d1327;
      --text: #dbe7ff;
      --muted: #9db0d9;
      --border: #24376d;
      --accent: #6ee7ff;
      --panel-soft: rgba(20, 32, 68, 0.72);
      --shadow: rgba(8, 12, 28, 0.45);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 28px 20px 40px;
      background: radial-gradient(circle at top, #101e42, var(--bg) 45%);
      color: var(--text);
      line-height: 1.45;
    }}
    main {{ max-width: 1180px; margin: 0 auto; }}
    .page-header {{
      margin-bottom: 18px;
      padding: 16px 18px;
      border: 1px solid var(--border);
      border-radius: 16px;
      background: linear-gradient(165deg, var(--panel-soft), rgba(10, 16, 35, 0.82));
      box-shadow: 0 10px 30px var(--shadow);
    }}
    h1 {{
      margin: 0;
      letter-spacing: 0.03em;
      text-transform: uppercase;
      font-size: clamp(1.2rem, 2vw, 1.8rem);
    }}
    .updated {{ margin: 6px 0 0; color: var(--muted); }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 14px; }}
    .card {{
      background: linear-gradient(158deg, rgba(19, 31, 66, 0.92), rgba(9, 15, 32, 0.95));
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 14px 16px;
      box-shadow: 0 8px 22px var(--shadow);
    }}
    .card-header {{ display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 12px; }}
    .card h2 {{ margin: 0; font-size: 0.98rem; }}
    .card a {{ color: var(--accent); }}
    .meta {{ margin: 0; display: grid; gap: 9px; }}
    .meta div {{
      display: grid;
      grid-template-columns: 105px 1fr;
      gap: 8px;
      align-items: baseline;
    }}
    .meta dt {{ color: var(--muted); font-size: 0.82rem; text-transform: uppercase; letter-spacing: 0.03em; }}
    .meta dd {{ margin: 0; font-weight: 500; }}
    .meta .break {{ overflow-wrap: anywhere; }}
    .card-action {{ margin: 14px 0 0; }}
    .card-action a {{ font-weight: 600; }}
    .status {{ display: inline-block; padding: 4px 10px; border-radius: 999px; font-weight: 600; margin-bottom: 10px; border: 1px solid transparent; }}
    .status.success {{ background: rgba(22, 101, 52, 0.32); border-color: #22c55e; color: #a7f3d0; }}
    .status.failure, .status.error {{ background: rgba(153, 27, 27, 0.32); border-color: #f87171; color: #fecaca; }}
    .status.in-progress {{ background: rgba(29, 78, 216, 0.35); border-color: #60a5fa; color: #bfdbfe; }}
    .status.pending, .status.queued {{ background: rgba(133, 77, 14, 0.35); border-color: #facc15; color: #fef08a; }}
    .status.unknown, .status.inactive {{ background: rgba(71, 85, 105, 0.42); border-color: #94a3b8; color: #cbd5e1; }}
    @media (max-width: 640px) {{
      body {{ padding: 16px 12px 28px; }}
      .card-header {{ flex-direction: column; align-items: flex-start; }}
      .meta div {{ grid-template-columns: 1fr; gap: 2px; }}
      .status {{ margin-bottom: 0; }}
    }}
  </style>
</head>
<body>
  <main>
    <header class=\"page-header\">
      <h1>🚀 Deployment Dashboard</h1>
      <p class=\"updated\">Last updated: <strong>{generated_at}</strong></p>
    </header>
    <div class=\"grid\">{cards_html}</div>
  </main>
</body>
</html>
"""


def main() -> None:
    token = os.getenv("DASHBOARD_GH_TOKEN") or os.getenv("GITHUB_TOKEN")
    if not token:
        raise SystemExit("Missing token. Set DASHBOARD_GH_TOKEN (preferred) or GITHUB_TOKEN.")

    rows = fetch_deployments(token)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    Path("deployments_data.json").write_text(
        json.dumps([row.__dict__ for row in rows], indent=2) + "\n",
        encoding="utf-8",
    )
    Path("DEPLOYMENTS.md").write_text(render_readme(rows, generated_at), encoding="utf-8")
    Path("docs/index.html").write_text(render_html(rows, generated_at), encoding="utf-8")

    print(f"Wrote dashboard files for {len(rows)} deployments")


if __name__ == "__main__":
    main()
