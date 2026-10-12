# Limitations

- ChatGPT, Claude, and Grok consumer plan balances, reset timers, and remaining messages are not available through a supported read API. The Subscriptions page stores only what you type, with the time you recorded it.
- The monitor does not log into provider websites, accept passwords, or accept session cookies.
- OpenAI coverage is completions usage plus organization costs. Embeddings, images, audio, and other usage families are not collected.
- OpenAI cached input is a subset of input tokens. The dashboard does not add those two figures together.
- Anthropic cost amounts are interpreted as minor currency units. If Anthropic changes that unit, billed totals from that connector must be rechecked against the official docs before they are trusted.
- xAI usage is parsed only when the response contains a `data`, `usage`, `results`, or `records` list. A different shape is reported as failed and stored as zero rows.
- Non-USD provider cost rows are skipped. They are not converted unless you separately enter FX rates, and those rates are used only for a labeled subscription outlay.
- Gateway estimates and provider-billed totals are shown side by side. Variance is estimate minus billed. They are not summed.
- Missing request counts, latency, and error rates display as N/A. A missing measurement is not stored or shown as zero.
- No live provider call was made while building this copy, because no admin keys were configured. A Not Configured badge is the honest state until you add a key locally.
- Email alerts do nothing until SMTP is configured and `ALERT_EMAIL_ENABLED=true`. Demo budgets never send mail.
- Do not expose the service publicly without authentication and HTTPS.
