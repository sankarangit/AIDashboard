# Provider setup

No key is required for the demo dashboard. Put credentials only in `.env`.

## OpenAI

Create an organization **Admin API key** and set `OPENAI_ADMIN_KEY`.

The connector reads:

- `GET https://api.openai.com/v1/organization/usage/completions`
- `GET https://api.openai.com/v1/organization/costs`

A project inference key cannot read these routes. ChatGPT Plus or Pro usage is not returned here. Add that plan on the Subscriptions page if you want a manual fee.

Docs: https://developers.openai.com/api/reference/resources/admin/subresources/organization/subresources/usage/methods/costs and https://help.openai.com/en/articles/10478918-reviewing-api-usage-and-costs

Cost rows keep the provider line item. They are not joined onto usage buckets, because the grains differ.

## Anthropic

Set `ANTHROPIC_ADMIN_KEY` to an organization admin key. The connector reads:

- `GET https://api.anthropic.com/v1/organizations/usage_report/messages`
- `GET https://api.anthropic.com/v1/organizations/cost_report`

Cost `amount` values are treated as minor units (cents for USD) and divided by 100. Non-USD amounts are skipped rather than converted. Accounts without the Admin API get an unsupported or permission status; use a file import instead.

Claude Pro, Max, and Claude Code subscription quotas are not available from this API.

Docs: https://platform.claude.com/docs/en/manage-claude/usage-cost-api and https://platform.claude.com/docs/en/manage-claude/admin-api

## xAI

Set both `XAI_MANAGEMENT_API_KEY` and `XAI_TEAM_ID`. The connector calls:

- `POST https://management-api.x.ai/v1/billing/teams/{team_id}/usage` with `start_time` and `end_time`
- `GET https://management-api.x.ai/v1/billing/teams/{team_id}/prepaid/balance` for the connection test only

A regular inference key is not sent to these routes. If the usage response has no recognized record list, nothing is stored. Grok consumer subscriptions stay on the manual Subscriptions page.

Docs: https://docs.x.ai/developers/rest-api-reference/management/billing and https://docs.x.ai/developers/management-api-guide

## LiteLLM and agent logs

LiteLLM is optional. Set `LITELLM_BASE_URL` and `LITELLM_API_KEY` only when a proxy you already run should contribute spend logs. Those costs are stored as `gateway_estimated`.

Agent CSV or JSONL files are uploaded explicitly. Required fields are `timestamp`, `provider`, and the optional measures listed in the spec (`agent`, `model`, `input_tokens`, `output_tokens`, `cache_tokens`, `estimated_cost_usd`, `latency_ms`, `request_id`, `result`, `source`). Columns named prompt, response, messages, or content are dropped.
