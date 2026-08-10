---
name: test-database-isolation
description: The pytest suite reads and writes the developer's live database. Noticed 2026-08-10 while verifying the credential AEAD migration; not fixed.
type: project
---

# The test suite mutates the development database

**Date:** 2026-08-10
**Status:** known, deliberately not fixed in this round

## What was observed

While verifying the credential AEAD migration, `scripts/reencrypt_credentials.py
--dry-run` reported **2 legacy provider rows**. A `make check` ran in between.
The next scan reported **0** — the rows had changed underneath.

Ruled out, in this order, because "data changed after a dry-run" must not be
left as a guess:

- **Not a dry-run leak.** `tests/test_reencrypt_script.py::test_dry_run_reports_without_writing`
  asserts byte-identical ciphertext across a dry run, against a throwaway table.
- **Not startup seeding.** `seed_providers_on_startup` does `continue` on any
  preset whose name already exists; it never touches an existing row.
- **It was the test suite.** Tests create and delete `providers` rows against
  the real database. The pre-existing legacy rows were removed by test cleanup
  and new rows were written through the current code path. Row ids 443 and 452
  are the replacements.

## Why it matters

- **Verifying anything about production-shaped data is unreliable.** Any
  measurement taken before a test run may not survive it. This cost real time
  during the AEAD work and will cost it again.
- **A destructive test bug damages developer data**, not a scratch fixture.
  Today the blast radius is provider rows; nothing stops it growing.
- Two developers (or a developer and an agent) cannot run the suite
  concurrently against the same database without interfering.
- `conftest.py` already documents a related hazard — `test_smoke_api.py` was
  excluded from collection because its separate event loop poisons the
  module-level engine's pool. Same root cause: **the suite shares process-global
  database state with the application.**

## Not fixed here, and why

Fixing it properly means one of:

1. a per-session throwaway database (template DB or container per run), or
2. wrapping each test in a transaction that is rolled back, which needs the
   app's `AsyncSessionLocal` to be injectable rather than module-global, or
3. a dedicated test database via `DATABASE_URL` plus a truthful failure when it
   points at anything that looks like a working database.

(3) is cheapest and would have prevented what was seen here. (2) is the right
end state but reaches into `app/core/database.py`, which every service imports —
that is a refactor with its own risk, and it does not belong bolted onto a
credential-encryption change.

## Pointer

The nearest existing note is `docs/superpowers/plans/2026-08-08-approval-loop-verification-debt.md`,
which records what the approval work did not prove. This is the same category:
a gap in what can be *verified*, not in what is built.
