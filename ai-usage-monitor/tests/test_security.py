from backend.services.security import mask_secret, redact, send_budget_email


def test_redaction_removes_bearer_and_key_material():
    prefix = "sk" + "-live-"
    sample = "Authorization: Bearer " + prefix + "EXAMPLEKEY123456"
    cleaned = redact(sample)
    assert "EXAMPLEKEY123456" not in cleaned
    assert "Bearer" not in cleaned


def test_mask_does_not_return_the_secret():
    secret = "admin-key-value-9988"
    masked = mask_secret(secret)
    assert secret not in masked
    assert masked.endswith("9988")


def test_email_stays_disabled_by_default(monkeypatch):
    monkeypatch.setenv("ALERT_EMAIL_ENABLED", "false")
    from backend.config import reset_settings

    reset_settings()
    assert send_budget_email("subject", "body") == "disabled"
    reset_settings()
