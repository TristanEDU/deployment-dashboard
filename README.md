# 🚀 Deployment Dashboard

This repo runs a scheduled GitHub Action that scans repositories you can access, reads deployment + deployment status data, then publishes a dashboard of active deployments.

## Dashboard Links

- 📋 **[Markdown Dashboard](./DEPLOYMENTS.md)**
- 🌐 **[Web Dashboard](./docs/index.html)** (or your GitHub Pages URL)

## Required Setup (important)

To scan **all your repositories**, configure a fine-grained or classic PAT and save it as:

- `DASHBOARD_GH_TOKEN` (Repository **Settings → Secrets and variables → Actions**)

Recommended token permissions/scopes:
- Repository metadata read
- Deployments read
- Contents read/write for this dashboard repo

> Why this matters: `github.token` is usually scoped to the current repository only, so it often cannot read deployments from your other repos.

## How it works

1. Workflow `.github/workflows/update-deployments.yml` runs hourly (and manually).
2. Script `scripts/update_dashboard.py`:
   - Lists repos visible to the token (`/user/repos` with pagination)
   - Pulls deployments and latest status for each repo, then keeps only active states (in_progress, queued, pending, waiting)
   - Writes:
     - `DEPLOYMENTS.md` (table with repo + deployment links)
     - `docs/index.html` (card dashboard with direct links)
     - `deployments_data.json` (raw snapshot)
3. Workflow commits and pushes updates automatically.

## Manual run

- Go to **Actions → Update Deployment Dashboard → Run workflow**.

## Troubleshooting

- If dashboard is empty, verify `DASHBOARD_GH_TOKEN` is present and has repo/deployment visibility.
- Check workflow logs for API errors or permission issues.
