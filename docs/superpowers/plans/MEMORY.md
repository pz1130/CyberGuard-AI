# Memory Index

- [Project Status](project_status.md) — CyberGuard impl state as of 2026-05-29 (scheduled-tasks model export + webui port)
- [Architecture Facts](architecture_facts.md) — Key tech choices that differ from original design docs (WebUI, Celery, LLM Router)
- [Approval-loop verification debt](2026-08-08-approval-loop-verification-debt.md) — what the approval work did not prove; every test of it is mocked
- [Test database isolation](2026-08-10-test-database-isolation.md) — the suite reads/writes the developer's live DB; measurements do not survive a `make check`
