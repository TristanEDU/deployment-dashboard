# 🚀 Deployment Dashboard

Welcome to your deployment tracking dashboard! This repository automatically scans all your GitHub repositories every hour and provides a centralized view of all active deployments.

## Features

✨ **Automatic Hourly Updates** - Scans all your repos on a schedule
📊 **Beautiful Dashboard** - View deployments in markdown and HTML formats
🔍 **Complete Visibility** - See all active deployments across your projects
⚡ **Zero Configuration** - Just set up the workflow and it runs automatically

## Dashboard Links

- **📋 [Markdown Dashboard](./README.md)** - Simple table format (this file gets auto-updated)
- **🌐 [Web Dashboard](https://TristanEDU.github.io/deployment-dashboard/)** - Interactive HTML view

## How It Works

1. A GitHub Actions workflow runs **every hour** (configurable)
2. The workflow queries all your repositories for active deployments
3. It generates both a markdown table and an interactive web dashboard
4. Files are automatically committed and pushed back to this repo
5. The web dashboard is served via GitHub Pages

## Status Indicators

- ✅ **Success** - Deployment completed successfully
- ❌ **Failure** - Deployment failed
- ⚠️ **Error** - An error occurred
- 🔄 **In Progress** - Deployment is currently running
- ⏳ **Pending** - Waiting to start
- 📋 **Queued** - Queued for deployment
- ❓ **Unknown** - Status not available

## Setup Instructions

The dashboard is already configured! Here's what was set up:

### 1. GitHub Actions Workflow
- Located in `.github/workflows/update-deployments.yml`
- Runs automatically every hour at the top of the hour
- Can be triggered manually via GitHub Actions UI

### 2. Dashboard Files
- `README.md` - Auto-updated markdown table (you're reading it!)
- `docs/index.html` - Interactive web dashboard

### 3. GitHub Pages
- Web dashboard is served from the `docs/` folder
- Automatically deployed with each update
- View at: https://TristanEDU.github.io/deployment-dashboard/

## Customization

### Change Update Frequency
Edit `.github/workflows/update-deployments.yml` and modify the cron schedule:
```yaml
schedule:
  - cron: '0 */4 * * *'  # Every 4 hours
```

Cron format: `minute hour day month day-of-week`

### Filter Specific Repositories
Modify the Python script in the workflow to filter repos by name pattern.

## Manual Trigger

Want to update the dashboard immediately? Go to:
**Actions** → **Update Deployment Dashboard** → **Run workflow**

## Troubleshooting

### Deployments not showing?
1. Make sure your repositories have actual deployments
2. Check that deployments are in the GitHub Deployments API
3. Run the workflow manually to see any errors

### GitHub Pages not working?
1. Go to repository **Settings** → **Pages**
2. Ensure it's set to deploy from `docs/` folder on the `main` branch
3. Wait a few minutes for GitHub to build the site

## Last Updated

This dashboard was automatically generated. Check back frequently for the latest deployment info!

---

**Need help?** Check out the [GitHub Deployments documentation](https://docs.github.com/en/rest/deployments)