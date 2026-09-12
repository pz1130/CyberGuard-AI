"""SMTP skip must be visible, not a debug-level silent no-op."""
from app.services import email_service as es


def test_smtp_status_false_when_host_is_localhost(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "localhost")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "ops@example.org")
    status = es.smtp_status()
    assert status["configured"] is False
    assert "localhost" in status["reason"]


def test_smtp_status_true_when_host_and_from_set(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.org")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "ops@example.org")
    monkeypatch.setenv("SMTP_ADMIN_EMAIL", "soc@example.org")
    status = es.smtp_status()
    assert status["configured"] is True
    assert status["admin_email_set"] is True
