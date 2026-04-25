# BLOCKERS.md

Missing credentials and runtime dependencies that prevent full verification.

Created: 2026-04-24

## Missing Credentials

### ANTHROPIC_API_KEY
- **Required for:** `claude-critical` model (anthropic/claude-sonnet-4-6)
- **Impact:** Cannot verify Claude model availability
- **Action:** Provide Anthropic API key in `.env`

### Kimi Self-Hosted
- **KIMI_API_BASE:** <FILL_IN>
- **KIMI_API_KEY:** <FILL_IN>
- **Required for:** `kimi-default` model
- **Impact:** Cannot verify Kimi model availability
- **Action:** Deploy Kimi K2 inference endpoint and provide credentials

### GLM Self-Hosted
- **GLM_API_BASE:** <FILL_IN>
- **GLM_API_KEY:** <FILL_IN>
- **Required for:** `glm-default` model
- **Impact:** Cannot verify GLM model availability
- **Action:** Deploy GLM inference endpoint and provide credentials

## Verification Without Credentials

Static configuration verification:
```bash
# Config syntax check (does not require API keys)
docker run --rm -v $(pwd)/litellm/config.yaml:/app/config.yaml \
  ghcr.io/berriai/litellm:main-latest \
  --config /app/config.yaml --test
```

## Runtime Verification Blocked

Full health check (`curl http://localhost:4000/health`) requires:
- At least one valid model credential
- Or: mock/test mode configuration

## Resolution Path

1. Add credentials to `.env` file
2. Restart LiteLLM container
3. Run: `curl http://localhost:4000/health`
4. Expected: HTTP 200 with model list

## Notes

- Configuration file is syntactically valid
- All environment variable mappings are correct
- Langfuse callbacks configured for observability
- Router configured with usage-based strategy + 3 retries
