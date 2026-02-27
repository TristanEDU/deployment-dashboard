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

    deployments: List[DeploymentRow] = []
    for repo in repos:
        full_name = repo["full_name"]
        html_url = repo.get("html_url", f"https://github.com/{full_name}")

        for deployment in paged_get(f"{API}/repos/{full_name}/deployments", headers):
            dep_id = deployment["id"]
            statuses = list(
                paged_get(f"{API}/repos/{full_name}/deployments/{dep_id}/statuses", headers)
            )
            latest = statuses[0] if statuses else {}

            details_url = latest.get("target_url") or html_url
            deployments.append(
                DeploymentRow(
                    repo=repo["name"],
                    full_repo=full_name,
                    environment=deployment.get("environment") or "N/A",
                    ref=str(deployment.get("ref") or "N/A"),
                    sha=str(deployment.get("sha") or "")[:7],
                    created_at=deployment.get("created_at") or "",
                    status=latest.get("state") or "unknown",
                    dashboard_url=details_url,
                    status_description=latest.get("description") or "",
                )
            )

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
        link = f"[details]({row.dashboard_url})" if row.dashboard_url else "-"
        lines.append(
            f"| {repo_link} | {row.environment} | {status_text} | `{row.ref}` | `{row.sha or 'N/A'}` | {fmt_time(row.created_at)} | {link} |"
        )

    return "\n".join(lines) + "\n"


def render_html(rows: List[DeploymentRow], generated_at: str) -> str:
    cards = []
    for row in rows:
        emoji = STATUS_EMOJI.get(row.status, "❓")
        status_class = row.status.replace("_", "-")
        cards.append(
            f"""
      <article class=\"card\">
        <h2><a href=\"https://github.com/{html.escape(row.full_repo)}\" target=\"_blank\" rel=\"noreferrer\">{html.escape(row.full_repo)}</a></h2>
        <span class=\"status {html.escape(status_class)}\">{emoji} {html.escape(row.status)}</span>
        <p><strong>Environment:</strong> {html.escape(row.environment)}</p>
        <p><strong>Branch/Ref:</strong> {html.escape(row.ref)}</p>
        <p><strong>Commit:</strong> <code>{html.escape(row.sha or 'N/A')}</code></p>
        <p><strong>Created:</strong> {html.escape(fmt_time(row.created_at))}</p>
        <p><a href=\"{html.escape(row.dashboard_url)}\" target=\"_blank\" rel=\"noreferrer\">Open deployment</a></p>
      </article>
            """.strip()
        )

    cards_html = "\n".join(cards) if cards else "<p>No deployments found for repositories visible to this token.</p>"
    return f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"UTF-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
  <title>Deployment Dashboard</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 0; padding: 24px; background: #f4f6fb; color: #111827; }}
    main {{ max-width: 1100px; margin: 0 auto; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }}
    .card {{ background: white; border: 1px solid #e5e7eb; border-radius: 12px; padding: 16px; }}
    .card h2 {{ margin-top: 0; font-size: 1rem; }}
    .card p {{ margin: 8px 0; }}
    .status {{ display: inline-block; padding: 4px 10px; border-radius: 999px; font-weight: 600; margin-bottom: 10px; background: #e5e7eb; }}
    .status.success {{ background: #dcfce7; color: #166534; }}
    .status.failure, .status.error {{ background: #fee2e2; color: #991b1b; }}
    .status.in-progress {{ background: #dbeafe; color: #1d4ed8; }}
    .status.pending, .status.queued {{ background: #fef9c3; color: #854d0e; }}
  </style>
</head>
<body>
  <main>
    <h1>🚀 Deployment Dashboard</h1>
    <p>Last updated: <strong>{generated_at}</strong></p>
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
