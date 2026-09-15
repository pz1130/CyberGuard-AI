# Per-Script Egress Allowlist — Phase 2 of Executable Skill Scripts

**Date:** 2026-09-15
**Scope:** `script_network = "allowlist"`. Phase 1 (`"none"`) already ships and is not modified.
**Goal:** Let an approved skill script reach a named set of hosts and nothing else, with the allowlist enforced per script rather than per deployment.

**Builds on:** `docs/superpowers/specs/2026-09-15-skill-script-execution-design.md` (Phase 1, shipped in `b54e4b5`..`31de161`). The `script_network` and `script_network_allowlist` columns already exist; this phase adds no migration.

---

## 1. The finding that shapes this design

Phase 1's §8 sketched Phase 2 as "outbound only through a forward proxy holding the domain allowlist, injected as `HTTP_PROXY`/`HTTPS_PROXY`".

**`HTTP_PROXY` is not a security boundary.** It is a convention that a library may choose to honor. This was measured, not assumed:

```
urllib with HTTP_PROXY set   -> 403 from the proxy   (honored the convention)
raw socket, same process     -> 200 from the origin  (ignored it entirely)
```

Three lines of `socket.connect()` defeat it. Any design that treats the environment variable as the control is enforcing nothing against the only adversary that matters — a script that does not cooperate.

The control must therefore be the **route table**, not the environment:

1. The script's container has no route to the internet.
2. The proxy is a **separate container**. Same container means the same network namespace and the same routes, so a co-located proxy is bypassable by definition.
3. The script's only reachable external endpoint is that proxy.

`HTTP_PROXY` remains in the design, but demoted to what it actually is: the mechanism that makes ordinary `urllib.request.urlopen(...)` work without the script author doing anything special.

---

## 2. Decisions

| # | Decision | Rejected alternative and why |
|---|---|---|
| D1 | **Per-execution nonce.** The API registers `(nonce → this tool's allowlist, TTL)` with the proxy before dispatch; the nonce travels as proxy credentials. | A deployment-wide allowlist (script A could reach script B's approved hosts, and a column named `script_network_allowlist` would not be per script — the name would lie). A long-lived per-tool credential (leaks once, works forever; and the proxy would need database access, which is exactly what it must not have). |
| D2 | **Write the proxy, Python standard library, CONNECT + absolute-form HTTP only.** | squid with an `external_acl_type` helper: a new image and CVE surface, config that is easy to get subtly wrong, and the SSRF floor would still have to be written by hand in the helper — so little is actually saved. |
| D3 | **A second service from the same image**, `skill-runner-net`, differing from `skill-runner` only in network attachment. | Teaching one service both modes: it would have to sit on both networks, so a `script_network=none` script could reach the proxy. Phase 1's guarantee, and INV-40 which asserts it, would both weaken. |
| D4 | **The proxy checks the resolved IP, not just the hostname**, and then connects to that same resolved IP. | Hostname-only checking: an admin allowlists `vendor.example`, the attacker controls that name, points it at `169.254.169.254`, and the allowlist becomes a door to cloud metadata. Re-resolving after the check reopens the same hole (DNS rebinding). |
| D5 | **Ports 80 and 443 only.** | Arbitrary ports: an allowlisted host becomes a generic tunnel. |

---

## 3. Topology

One image, two services, differing only in where they are attached:

```
backend ─────────── postgres   redis   tool-runner   celery   webui
   │
  api ──┬── sandbox      (internal) ── skill-runner        script_network = none
        │
        └── sandbox-net  (internal) ── skill-runner-net    script_network = allowlist
                                │
                          egress-proxy ──── egress ──→ internet
```

- **`sandbox` is not touched.** Phase 1's `skill-runner` stays on it alone, cannot reach the proxy, and INV-40 continues to hold unchanged. A shipped, tested guarantee should not be weakened to add a feature beside it.
- `skill-runner-net` runs the **same image** as `skill-runner`. Its only reachable external endpoint is `egress-proxy`.
- `egress-proxy` is the only service on both `sandbox-net` and `egress`. It is on neither `backend` nor `sandbox`.
- A script calling `socket.connect("1.2.3.4", 443)` fails for want of a route. That is the boundary; `HTTP_PROXY` is the convenience on top of it.

### 3.1 The sandbox needs no DNS

With a proxy configured, the script sends `CONNECT host:443` and the **proxy** resolves the name. The script never resolves anything, so `sandbox-net` needs no DNS reachability — one fewer path out, and one fewer place for a rebinding trick to land.

---

## 4. Nonce lifecycle

`_pool_execute` already branches on `source_skill_id`. After the digest check it branches again on `script_network`:

```
"none"       -> POST skill-runner/run                                  (Phase 1, unchanged)
"allowlist"  -> grant -> POST skill-runner-net/run -> revoke
```

1. `secrets.token_urlsafe(32)` produces the nonce.
2. `POST egress-proxy/grant {nonce, allowlist, ttl}` authenticated with `EGRESS_PROXY_TOKEN`, which `api` and the proxy share and
   neither runner ever sees.
3. `POST skill-runner-net/run {argv, timeout, files, proxy_url}` where `proxy_url` is `http://<nonce>:x@$EGRESS_PROXY_URL` (default host
   `egress-proxy:3128`).
4. The runner injects that URL into `HTTP_PROXY`, `HTTPS_PROXY`, `http_proxy`, `https_proxy`. **`MINIMAL_ENV` is otherwise unchanged and still carries no token or secret** — the nonce is scoped to one execution and buys only that execution's allowlist.
5. `finally: POST egress-proxy/revoke {nonce}` — including when the run raised.

Grants live in the proxy process's memory, keyed by nonce, with `ttl = run timeout + 30s`
so a grant cannot outlive the execution that owns it by more than a margin.

**The proxy therefore runs a single worker process.** In-memory grants and a
multi-worker uvicorn are silently incompatible: `grant` would land in one worker and
the `CONNECT` in another, and the failure would look like an intermittent `407` rather
than a configuration error. The compose command pins `--workers 1`, and a test asserts
it, because this is exactly the kind of constraint that gets tuned away later by
someone reasonably trying to make the proxy faster.

If the proxy restarts mid-execution the grant is gone and the script loses network:
fail-closed, which is the right direction.

### 4.1 Why the credential reaches the script transparently

Python's `urllib` parses userinfo out of the proxy URL and sends `Proxy-Authorization: Basic base64("<nonce>:x")` on its own. Measured, not assumed:

```
HTTP_PROXY=http://exec-nonce-abc123:x@127.0.0.1:PORT
proxy received: Proxy-Authorization: Basic ZXhlYy1ub25jZS1hYmMxMjM6eA==
decoded: 'exec-nonce-abc123:x'
```

So a skill author writes ordinary `urllib.request.urlopen("https://vendor.example/api")` and the scoping happens underneath. Nothing in the script mentions nonces.

---

## 5. What the proxy checks

Every request — `CONNECT host:port`, or an absolute-form HTTP request line — passes all of:

| Check | On failure |
|---|---|
| `Proxy-Authorization` decodes to a nonce with a live grant | `407` |
| Port is 80 or 443 | `403` |
| Host matches that nonce's allowlist — exact, or `.suffix`. Same rule as `app/core/egress.py`, reimplemented rather than imported (§5.1) | `403` |
| The **resolved** IP is not private, loopback, link-local or a metadata address | `403` |
| Connect to the IP already resolved — never resolve a second time | — |

HTTPS is tunnelled, never intercepted. The script's own TLS validation still runs against the hostname it asked for, so connecting by resolved IP changes nothing it can observe and needs no certificate machinery on our side.

### 5.1 The duplicated blocklist, and the guard for it

`egress_proxy/` is standalone: like `tool_runner/` and `skill_runner/`, it must not import from `app`. So the private/metadata network list exists twice — once in `app/core/ssrf.py`, once in the proxy.

Duplicating a security blocklist is a real drift hazard, so an invariant test asserts the two lists are element-wise equal. Cheap, and it fails the moment someone tightens one copy and forgets the other.

---

## 6. Everything else

- **No migration.** `script_network` and `script_network_allowlist` were created in `038_skill_script_tools`.
- The promotion endpoint stops rejecting `"allowlist"` and starts validating the list: non-empty, syntactically valid hostnames, no bare IP addresses, no wildcards beyond a leading-dot suffix.
- New package `egress_proxy/`, new `egress-proxy/Dockerfile`.
- New environment: `SKILL_RUNNER_NET_URL`, `EGRESS_PROXY_CONTROL_URL`, `EGRESS_PROXY_TOKEN`, `EGRESS_PROXY_URL`. `EGRESS_PROXY_TOKEN` goes to `api` and `egress-proxy` only — never to either runner.

## 7. Failure modes

| Condition | Behavior |
|---|---|
| Proxy unreachable at grant time | Refuse the execution; do not fall back to running without network |
| Proxy restarted, grant lost | Script's requests get `407`; the run itself continues and fails on its own terms |
| Run raises before revoke | `finally` revokes; grants also expire on TTL |
| Allowlisted host resolves to a private IP | `403`, audited |
| Script ignores `HTTP_PROXY` | No route; connection fails |
| `script_network = "allowlist"` but the proxy is not configured | Promotion refuses; execution refuses |

## 8. Testing

- Proxy: allow and deny by exact host and by `.suffix`; port restriction; unknown, revoked and expired nonces; resolved-IP SSRF rejection; a real CONNECT tunnel carrying bytes end to end
- The blocklist-parity invariant (§5.1)
- The proxy service is pinned to a single worker (§4), so in-memory grants stay coherent
- Compose topology: `skill-runner-net` and `egress-proxy` are on neither `backend` nor `sandbox`; Phase 1's `skill-runner` still shares no network with the proxy; `egress-proxy` alone is on `egress`
- Executor: grant precedes dispatch and revoke follows it, including when the run raises; a `none` tool never contacts the proxy
- Promotion: valid allowlist accepted; empty list, bare IP and `*.x` wildcard all rejected

## 9. Out of scope

- Ports other than 80 and 443 (D5)
- TLS interception or response inspection — the proxy decides on the hostname and then moves bytes
- Egress for Phase 1's `script_network = "none"`, which stays absolute

## 10. Related future work, recorded so it is not rediscovered

A separate request — letting the model write a script during a chat and run it — was investigated and deferred to its own project. Two findings from that investigation are worth keeping:

1. **No code-execution capability exists today.** An agent's tools are MCP tools, pool `Tool` rows, `kb_search`, `web_search`, `vuln_search` and `load_skill` (`internal_agent._build_tools`). There is no path from model-generated text to execution.
2. **Tool-level approvals do not resume.** `internal_agent._request_approval` writes records with `action_type="tool.execute"` and no `thread_id`; `graph_resume_target` returns `None` for them, so approving one re-executes nothing. Only graph-suspended approvals (`agent_execution`) resume, through LangGraph checkpointing.

Point 2 is the real cost of that feature: "model writes code, human approves, code runs, result returns to the model" needs a suspend/resume loop that does not exist for tool calls. That is an orchestration project, not an added tool, and it should be scoped on its own.
