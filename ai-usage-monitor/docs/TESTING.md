# Testing

From `ai-usage-monitor` with the virtual environment active:

```powershell
python -m pytest -q
python -m ruff check .
```

What the tests cover:

- Asia/Singapore dates around 16:00 UTC.
- Null token, request, latency, and error-rate totals stay null.
- Provider-billed and gateway-estimated costs are not added.
- Reconciliation variance and unmatched estimated rows.
- Secret redaction, masked credentials, and email remaining disabled.
- OpenAI, Anthropic, and xAI payload parsing, including an unrecognized xAI body that stores nothing.
- Missing keys do not call the network. HTTP 401 and 429 become permission and rate-limit statuses without echoing the response body.
- Importing the same CSV twice does not change row counts, and prompt columns are dropped.
- Demo seed is idempotent. Overview marks that data as demo and hides it when `include_demo=false`.
- SGD subscription fees stay out of the USD subscription total.
- Frontend modules compile.

A live sync against OpenAI, Anthropic, or xAI is not part of the automated suite. Run **Test connection** in Settings after placing a key in `.env`.
