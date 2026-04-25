# Render.com Deployment Guide

**Target URL**: https://rca-render.intellisync.cloud  
**Repository**: https://github.com/sai-harsha-vardhan/stability-intelligence  
**Blueprint**: `render.yaml` (Infrastructure as Code)

---

## Overview

The Stability Intelligence System deploys as 7 services on Render.com:

| Service | Type | Purpose |
|---------|------|---------|
| rca-neo4j | Private Service | Graph database (Neo4j 5.18) |
| rca-langfuse-db | Private Service | PostgreSQL for Langfuse |
| rca-langfuse | Web Service | Observability platform |
| rca-litellm | Web Service | LLM proxy/router |
| rca-agent-runner | Background Worker | Autonomous agent execution |
| rca-dashboard-api | Web Service | FastAPI backend |
| rca-render | Static Site | React dashboard UI |

---

## Prerequisites

Before connecting to Render, ensure you have:

1. **Anthropic API Key** - For Claude model access
2. **Kimi API Base & Key** - Self-hosted Kimi K2 endpoint
3. **GLM API Base & Key** - Self-hosted GLM endpoint
4. **GitHub Token** - For issue synchronization
5. **Langfuse Keys** - From Langfuse dashboard
6. **Slack Webhook URL** (optional) - For notifications

---

## Step 1: Connect Repository to Render

1. Visit [render.com](https://render.com) and log in
2. Click **"New"** → **"Blueprint"**
3. Select GitHub account: `sai-harsha-vardhan`
4. Select repository: `stability-intelligence`
5. Click **"Connect"**

Render will detect `render.yaml` and display the 7 services to be created.

---

## Step 2: Configure Environment Variables

After the blueprint is connected, configure secrets for each service:

### rca-neo4j (Private Service)

```
NEO4J_AUTH=neo4j/YOUR_SECURE_PASSWORD
```

### rca-litellm (Web Service)

```
ANTHROPIC_API_KEY=sk-ant-...
KIMI_API_BASE=https://your-kimi-endpoint.com
KIMI_API_KEY=your-kimi-key
GLM_API_BASE=https://your-glm-endpoint.com
GLM_API_KEY=your-glm-key
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_PUBLIC_KEY=pk-lf-...
```

### rca-agent-runner (Worker)

```
NEO4J_PASSWORD=YOUR_NEO4J_PASSWORD_FROM_ABOVE
LITELLM_API_KEY=MATCHES_LITELLM_MASTER_KEY
GITHUB_TOKEN=ghp_...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_PUBLIC_KEY=pk-lf-...
SLACK_WEBHOOK_URL=https://hooks.slack.com/... (optional)
```

### rca-dashboard-api (Web Service)

```
NEO4J_PASSWORD=YOUR_NEO4J_PASSWORD
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_PUBLIC_KEY=pk-lf-...
SLACK_WEBHOOK_URL=https://hooks.slack.com/... (optional)
```

---

## Step 3: Set Custom Domain

For the dashboard UI (`rca-render` service):

1. Go to Dashboard → rca-render service
2. Click **"Settings"** → **"Custom Domain"**
3. Enter: `rca-render.intellisync.cloud`
4. Follow Render's DNS configuration instructions
5. Add CNAME record in Cloudflare/DNS provider

---

## Step 4: Deploy

1. Click **"Apply"** to create all services
2. Monitor deployment logs for each service
3. Wait for all health checks to pass:
   - Neo4j: Port 7474
   - Langfuse: `/api/health`
   - LiteLLM: `/health`
   - Dashboard API: `/api/health`

---

## Step 5: Verify Deployment

Once all services are live:

```bash
# Check dashboard
curl https://rca-render.intellisync.cloud

# Check API health
curl https://rca-dashboard-api.onrender.com/api/health

# Check LiteLLM health
curl https://rca-litellm.onrender.com/health
```

---

## Service Dependencies

Services start in this order (Render handles this automatically):

1. **Databases first**: rca-neo4j, rca-langfuse-db
2. **Observability**: rca-langfuse (depends on db)
3. **LLM Proxy**: rca-litellm
4. **Application layer**: rca-agent-runner, rca-dashboard-api
5. **Frontend**: rca-render (depends on API)

---

## Troubleshooting

### Service won't start
- Check logs in Render dashboard
- Verify all `sync: false` env vars are set
- Ensure dependent services are healthy first

### Database connection failures
- Verify NEO4J_PASSWORD matches between rca-neo4j and consumers
- Check network connectivity (services use internal hostnames)

### LiteLLM health check fails
- Likely missing API credentials
- Check ANTHROPIC_API_KEY or alternative model configs
- View logs: "No valid models configured"

---

## Costs

Estimated monthly cost (Starter plan):

| Service | Plan | Monthly Cost |
|---------|------|--------------|
| rca-neo4j | Starter | ~$7 |
| rca-langfuse-db | Starter | ~$7 |
| rca-langfuse | Starter | ~$7 |
| rca-litellm | Starter | ~$7 |
| rca-agent-runner | Starter | ~$7 |
| rca-dashboard-api | Starter | ~$7 |
| rca-render | Starter (Static) | Free |
| **Total** | | **~$42/month** |

---

## Maintenance

### Updates
- Push to GitHub `master` branch
- Render auto-deploys all services

### Database Backups
- Neo4j: Disk snapshots via Render dashboard
- PostgreSQL: Automatic daily backups

### Scaling
- Upgrade individual service plans in Render dashboard
- Consider upgrading to Standard for higher traffic

---

## Support

- **Render Docs**: https://render.com/docs
- **LiteLLM Docs**: https://docs.litellm.ai
- **Langfuse Docs**: https://langfuse.com/docs
