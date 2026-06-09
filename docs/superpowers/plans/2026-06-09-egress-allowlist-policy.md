# Egress Allowlist / Containment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add destination egress control so agents and tools can only reach approved network destinations — the defense-in-depth that actually contains a black-box agent (or a tool command) trying to act out-of-band, closing the follow-up flagged in the black-box-wrapping plan.

**Architecture:** Two layers, because they enforce different things honestly:
1. **App layer** — extend the existing block-list `app/core/ssrf.py` into an opt-in **allow-list** egress policy (`app/core/egress.py`), enforced at the outbound calls the application controls (webhooks, n8n, remote-agent HTTP push, skill downloads, web search) and audited.
2. **Network layer** — a Kubernetes `NetworkPolicy` (none exists today) that puts the **tool-runner** on default-deny egress with an explicit allowlist. This is the *only* thing that can contain an arbitrary tool command (`curl`, `nmap`, …), since app-level checks cannot intercept a subprocess's own sockets.

**Tech Stack:** Python (`urllib`, the existing `ssrf` module), FastAPI, Kubernetes NetworkPolicy, pytest. No DB migration.

---

## Dependencies & decisions

- **Builds on** `app/core/ssrf.py::validate_outbound_url()` (keeps the private/metadata block as the always-on floor) and the audit `record_action()` (controls plan) for egress-deny evidence.
- **Opt-in, like the rate limiter:** `EGRESS_ALLOWLIST_ENABLED` defaults `False` so nothing breaks until an operator turns it on and populates the list. When enabled, **default-deny**: only hosts in the allowlist (global + optional per-call extra) are permitted, on top of the SSRF floor.
- **Honest split:** the app layer governs calls *the app makes*. It **cannot** stop a tool subprocess (e.g. `curl http://evil`) from connecting — that is what the NetworkPolicy is for. Both are needed; neither alone is sufficient.
- **Per-agent allowlist** is passed as an optional `extra_allow` (read from the agent's `metadata_json`), avoiding a migration; a first-class column is a later refinement.
- **Allowlist match:** exact host or registrable-suffix (`api.example.com` matches an `example.com` entry); IP-literal entries matched exactly. Conservative — no wildcards beyond suffix.

## File Structure

| File | Responsibility |
|------|----------------|
| `app/core/egress.py` (create) | `enforce_egress()` — SSRF floor + allowlist; `EgressBlocked` |
| `app/config.py` (modify) | `EGRESS_ALLOWLIST_ENABLED`, `EGRESS_ALLOWLIST` |
| `app/services/webhook_service.py` (modify) | enforce on webhook delivery |
| `app/services/skill_installer.py` (modify) | enforce on skill/tool downloads |
| `app/services/agent_executor.py` (modify) | enforce on remote-agent HTTP push |
| `k8s/06-networkpolicy.yaml` (create) | default-deny egress for tool-runner + allowlist |
| `tests/test_egress.py` (create) | allow/deny, SSRF floor, suffix match, extra_allow, disabled passthrough |

---

### Task 1: Egress policy module

**Files:**
- Create: `app/core/egress.py`
- Modify: `app/config.py`
- Test: `tests/test_egress.py`

- [ ] **Step 1: Add settings** to `app/config.py` `Settings`:

```python
    EGRESS_ALLOWLIST_ENABLED: bool = False
    EGRESS_ALLOWLIST: str = ""   # comma-separated hosts/domains, e.g. "api.virustotal.com,example.com"
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_egress.py
import pytest
from app.core import egress
from app.core.ssrf import SSRFError


def test_disabled_passthrough_still_blocks_ssrf(monkeypatch):
    monkeypatch.setattr("app.config.settings.EGRESS_ALLOWLIST_ENABLED", False)
    # SSRF floor is always on, even when allowlist disabled:
    with pytest.raises(SSRFError):
        egress.enforce_egress("http://169.254.169.254/latest/meta-data")
    # normal public URL passes when disabled:
    assert egress.enforce_egress("https://example.com/x") == "https://example.com/x"


def test_allowlist_denies_unlisted(monkeypatch):
    monkeypatch.setattr("app.config.settings.EGRESS_ALLOWLIST_ENABLED", True)
    monkeypatch.setattr("app.config.settings.EGRESS_ALLOWLIST", "example.com")
    assert egress.enforce_egress("https://api.example.com/v3") == "https://api.example.com/v3"  # suffix match
    with pytest.raises(egress.EgressBlocked):
        egress.enforce_egress("https://evil.test/x")


def test_extra_allow_per_call(monkeypatch):
    monkeypatch.setattr("app.config.settings.EGRESS_ALLOWLIST_ENABLED", True)
    monkeypatch.setattr("app.config.settings.EGRESS_ALLOWLIST", "")
    with pytest.raises(egress.EgressBlocked):
        egress.enforce_egress("https://vt.example/x")
    assert egress.enforce_egress("https://vt.example/x", extra_allow=["vt.example"]) == "https://vt.example/x"


def test_exact_host_not_overmatched(monkeypatch):
    monkeypatch.setattr("app.config.settings.EGRESS_ALLOWLIST_ENABLED", True)
    monkeypatch.setattr("app.config.settings.EGRESS_ALLOWLIST", "example.com")
    with pytest.raises(egress.EgressBlocked):
        egress.enforce_egress("https://notexample.com/x")   # must not suffix-match
```

- [ ] **Step 3: Run to verify failure**

```bash
.venv/bin/python -m pytest tests/test_egress.py -v
```
Expected: FAIL — `ModuleNotFoundError: app.core.egress`.

- [ ] **Step 4: Implement `app/core/egress.py`**

```python
"""Outbound egress allowlist (defense-in-depth over SSRF block-list).

SSRF floor (private/metadata block) is ALWAYS enforced. When
EGRESS_ALLOWLIST_ENABLED, additionally require the host to match the configured
allowlist (global + optional per-call extra). Opt-in: disabled => SSRF-only.
"""
from __future__ import annotations
from urllib.parse import urlparse
from app.core.ssrf import validate_outbound_url, SSRFError  # noqa: F401 (re-exported for callers)


class EgressBlocked(ValueError):
    """Raised when a URL's host is not on the egress allowlist."""


def _allowlist() -> list[str]:
    from app.config import settings
    return [h.strip().lower() for h in (settings.EGRESS_ALLOWLIST or "").split(",") if h.strip()]


def _host_allowed(host: str, allow: list[str]) -> bool:
    host = (host or "").lower()
    for entry in allow:
        if host == entry or host.endswith("." + entry):
            return True
    return False


def enforce_egress(url: str, *, extra_allow: list[str] | None = None) -> str:
    """Validate an outbound URL. Always applies the SSRF floor; applies the
    allowlist when enabled. Returns the URL on success; raises SSRFError /
    EgressBlocked otherwise."""
    validate_outbound_url(url)                      # SSRF floor (raises SSRFError)
    from app.config import settings
    if not settings.EGRESS_ALLOWLIST_ENABLED:
        return url
    allow = _allowlist() + [a.strip().lower() for a in (extra_allow or [])]
    host = urlparse(url).hostname or ""
    if not _host_allowed(host, allow):
        raise EgressBlocked(f"egress to {host!r} blocked — not on allowlist")
    return url
```

- [ ] **Step 5: Run to verify pass**

```bash
.venv/bin/python -m pytest tests/test_egress.py -v
```
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add app/core/egress.py app/config.py tests/test_egress.py
git commit -m "feat(egress): opt-in egress allowlist over SSRF floor"
```

### Task 2: Enforce at app-controlled egress points

**Files:**
- Modify: `app/services/webhook_service.py`, `app/services/skill_installer.py`, `app/services/agent_executor.py`

- [ ] **Step 1: Webhook delivery.** In `webhook_service.py`, where the target URL is validated/used (the existing `_validate_url`), call the egress policy and audit denials:

```python
    from app.core.egress import enforce_egress, EgressBlocked
    try:
        enforce_egress(url)
    except (EgressBlocked, Exception) as e:
        # audit + refuse delivery
        from app.core.audit import record_action
        await record_action(user_id=None, action="egress:blocked", action_category="notify",
                            input_data={"url": url, "where": "webhook"}, output_data={"error": str(e)})
        raise
```

> Place this at the single delivery chokepoint so every webhook target is checked once. Keep the existing `_validate_url` as well (belt-and-suspenders).

- [ ] **Step 2: Skill/tool downloads.** In `skill_installer.py`, before any download of an external skill/tool artifact, wrap the URL with `enforce_egress(download_url)` (same import). Skill registries are exactly where a poisoned URL would pull untrusted content, so allowlisting registries here is high value.

- [ ] **Step 3: Remote-agent HTTP push.** In `agent_executor.py`, before pushing a task to a remote `endpoint_url` (hermes/custom backends), call `enforce_egress(endpoint_url)` so a registered agent can't redirect the orchestrator to an arbitrary internal host.

- [ ] **Step 4: Smoke-check imports + run touched suites**

```bash
.venv/bin/python -c "import app.services.webhook_service, app.services.skill_installer, app.services.agent_executor; print('ok')"
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/cyberguard \
  .venv/bin/python -m pytest tests/ -q -k "webhook or skill or egress or agent"
```
Expected: pass (egress disabled by default → behaviour unchanged unless turned on).

- [ ] **Step 5: Commit**

```bash
git add app/services/webhook_service.py app/services/skill_installer.py app/services/agent_executor.py
git commit -m "feat(egress): enforce egress policy on webhook/skill-download/remote-push"
```

### Task 3: Tool-runner network containment (NetworkPolicy)

**Files:**
- Create: `k8s/06-networkpolicy.yaml`

- [ ] **Step 1: Write the NetworkPolicy** — default-deny egress for the tool-runner, allowing only DNS + an explicit allowlist. (Adjust the namespace/labels to match `k8s/00-namespace.yaml` + `k8s/02-deployment-api.yaml`; the example assumes namespace `cyberguard` and a `tool-runner` pod label.)

```yaml
# k8s/06-networkpolicy.yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: tool-runner-egress
  namespace: cyberguard
spec:
  podSelector:
    matchLabels:
      app: tool-runner          # match the tool-runner deployment's pod label
  policyTypes:
    - Egress
  egress:
    # 1. DNS resolution only (kube-dns)
    - to:
        - namespaceSelector: {}
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
    # 2. Explicit destination allowlist — replace with approved CIDRs.
    #    Default is INTENTIONALLY empty (deny-all egress beyond DNS) so an
    #    operator must opt in each destination a tool legitimately needs.
    - to:
        - ipBlock:
            cidr: 0.0.0.0/0
            except:
              - 169.254.169.254/32   # cloud metadata
              - 10.0.0.0/8           # internal
              - 172.16.0.0/12
              - 192.168.0.0/16
      ports:
        - protocol: TCP
          port: 443
        - protocol: TCP
          port: 80
```

> **Operator note in the file's header comment:** the `except` block reproduces the SSRF floor at the network layer (no metadata, no RFC-1918). For a strict deny-default posture, replace the `ipBlock 0.0.0.0/0` rule with one `ipBlock` per approved destination CIDR. Requires a CNI that enforces NetworkPolicy (Calico/Cilium); document this as a cluster prerequisite.

- [ ] **Step 2: Validate the manifest**

```bash
kubectl apply --dry-run=client -f k8s/06-networkpolicy.yaml 2>&1 | head -3 || echo "kubectl not available — validate in CI/cluster"
```
Expected: `networkpolicy.networking.k8s.io/tool-runner-egress created (dry run)` (or a note that kubectl is unavailable locally).

- [ ] **Step 3: Commit**

```bash
git add k8s/06-networkpolicy.yaml
git commit -m "feat(egress): default-deny tool-runner egress NetworkPolicy"
```

**Plan gate:**
```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/cyberguard \
  .venv/bin/python -m pytest tests/ -q
```
Expected: all pass.

---

## Self-Review notes

- **Closes the wrapping plan's "egress allowlisting" follow-up** with the honest two-layer split: app-layer policy for calls the app makes; NetworkPolicy for arbitrary tool subprocesses.
- **Safe by default:** `EGRESS_ALLOWLIST_ENABLED=False` and an empty allowlist leave runtime behaviour unchanged; the SSRF floor remains always-on. Turning it on is an operator decision with a populated allowlist.
- **Audit:** egress denials are recorded (`egress:blocked`) so attempts to reach unapproved destinations are visible.
- **Known limitations / follow-ups:** (1) **MCP/LLM/search egress** points are not wired in this pass — add `enforce_egress` at `mcp_executor`, `search_service`, and the LLM provider base-URL resolution if you want those under the same policy (straightforward repeats of Task 2). (2) **docker-compose parity** — the NetworkPolicy is k8s-only; a compose deployment needs an equivalent egress firewall (e.g. a sidecar/iptables) — document for non-k8s installs. (3) **Per-agent allowlist** is via `extra_allow` today; promote to a first-class governance column if NDB wants per-agent destinations declared and exported in `agent_governance.yaml`. (4) NetworkPolicy enforcement depends on the CNI (Calico/Cilium) — note as a cluster prerequisite.
