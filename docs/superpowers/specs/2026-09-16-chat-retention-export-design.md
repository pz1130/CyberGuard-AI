# Chat Message Storage — Round 3: WORM export and retention

**Date:** 2026-09-16
**Scope:** Mirror whole conversations to write-once object storage, then dispose of the ones whose retention period has passed.
**Goal:** Let a deployment honour "keep records for N years, then dispose of them" without the disposal destroying the evidence.

**Builds on:** Round 1 (`…-chat-message-storage-design.md`) for the per-conversation hash chain and the anchors, Round 2 (`…-chat-message-search-design.md`) for the partial owner index.

**Not in this round:** cross-user search for auditors. It is a scope parameter on Round 2's `search_messages` plus a permission check — unrelated to export and retention, and small enough to do as ordinary bounded work afterwards.

---

## 1. Where Round 1's sketch was wrong, again

Round 1 §8 said to copy `audit_worm_exports`: "a marker table recording `last_message_id` … `conversation_messages.id` being a monotonic `BIGSERIAL` is what makes an incremental export possible."

That contradicts what Round 1 itself chose. The chain is **per conversation** and the anchor in the global audit log is **per conversation**, so the unit of evidence is a conversation. An export keyed on a global id boundary produces objects holding fragments of many conversations:

- no complete chain inside any one object, so the object cannot be verified on its own
- nothing to compare against the `conversation.chain_anchor` audit rows, which record a head seq and head hash for one conversation

**This is the second forward-looking claim in Round 1 §8 that did not survive contact with the detail** — the first was the `tsvector` index, replaced in Round 2. Sections of a spec that describe a later round are sketches, and this project has now twice found them wrong when the work was actually done. They are worth writing and not worth trusting.

**One conversation, one export object.**

---

## 2. Decisions

| # | Decision | Rejected alternative and why |
|---|---|---|
| D1 | One export object per conversation, containing its metadata, every message, and the chain fields. | Incremental export on `conversation_messages.id` (§1): fragments across objects, independently verifiable as nothing. |
| D2 | **The chain is verified before the object is written.** A conversation whose chain is broken is reported and not exported. | Exporting anyway: writing a known-corrupt chain into immutable storage makes the corruption permanent and gives it the appearance of evidence. |
| D3 | Purge deletes **every message of a conversation, or none**. | Purging by age at message granularity: the oldest surviving message's `prev_hash` would point at a deleted row, and `verify_conversation_chain` could no longer tell retention apart from tampering. |
| D4 | The `conversations` row survives a purge, carrying `purged_at` and `export_key`. | Deleting the row: the `conversation.chain_anchor` audit entries would name a conversation nothing can resolve, and the person would see their history silently shrink rather than see that it was archived. |
| D5 | Purge requires a **complete** export: an export row whose `head_seq` equals the conversation's current maximum `seq`. | "Has been exported at all": a conversation exported at seq 40 and since grown to seq 90 would lose fifty messages that exist in no object. |
| D6 | Purge applies to every conversation older than the cutoff, not only tombstoned ones, and the UI shows such a conversation as archived. | Tombstones only: it would leave the database growing without bound and would not implement disposal, which is the compliance obligation this round exists for. |
| D7 | `POST /conversations/purge` **dry-runs by default**; deleting requires `confirm=true`. | Deleting on call: this is the one irreversible operation in the product, and it should not be a typo away. |
| D8 | `older_than_days` is a **call parameter**, stored nowhere. | A `security_settings` column: this repo has shipped six settings that nothing read (`rbac_enabled`, `max_login_attempts` before it was wired, and four more). A retention period that silently stops being applied is worse than one that must be typed. |
| D9 | Export and purge require `AUDIT_READ`. | `SETTINGS_WRITE` or admin-only: this is the auditor's job, and `Role.AUDITOR` holds `AUDIT_READ` and nothing else — it is the role that should be able to do this without also being able to change the system. |

---

## 3. Schema

```sql
CREATE TABLE conversation_exports (
    id              SERIAL PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    object_key      VARCHAR(300) NOT NULL,
    rows            INTEGER NOT NULL,
    head_seq        INTEGER NOT NULL,
    head_hash       VARCHAR(64) NOT NULL,
    retain_until    TIMESTAMP,
    exported_at     TIMESTAMP NOT NULL
);
CREATE INDEX ix_conv_exports_conv ON conversation_exports (conversation_id, head_seq);

ALTER TABLE conversations ADD COLUMN purged_at  TIMESTAMP NULL;
ALTER TABLE conversations ADD COLUMN export_key VARCHAR(300) NULL;
```

Migration id: `045_conversation_retention` (26 chars — `alembic_version.version_num` is `varchar(32)`), revising `044_conversation_search`.

A conversation may be exported more than once as it grows; the row with the
highest `head_seq` is the current one. Old rows are kept: each names an object
that still exists in WORM storage and cannot be withdrawn.

`ON DELETE CASCADE` means a genuine administrative removal of the
`conversations` row takes its export records with it. The objects themselves
survive in WORM storage, which is the point — the marker table is a
convenience, never the archive.

### 3.1 The export object

JSONL, one object per conversation, at `conversations/worm/<conv_id>-<head_seq>-<timestamp>.jsonl`:

```
{"type":"conversation","id":4,"user_id":3,"title":"Port scan triage","created_at":…}
{"type":"message","seq":0,"role":"user","content":"…","created_at":…,"run_id":null,
 "turn_id":null,"backfilled":false,"prev_hash":"000…","entry_hash":"a1b2…"}
…
```

Everything `entry_hash` covers is present, so a reader can recompute the chain
from the object alone and compare its head against the
`conversation.chain_anchor` row in the exported audit log. The two exports —
audit and conversation — verify each other.

Written with S3 Object Lock in `COMPLIANCE` mode and a `retain_until`, exactly
as `audit_worm._put_worm_object` does.

---

## 4. Export

`app/services/conversation_export.py`:

```python
# One conversation. Raises RuntimeError when S3 is unconfigured (§6).
async def export_conversation(session, conversation_id: int, retain_days: int) -> dict:
    # {"conversation_id", "object_key", "rows", "head_seq", "head_hash"}
    # or {"conversation_id", "skipped": "empty" | "chain-broken-at-seq-N"}

# Every conversation last updated before the cutoff.
async def export_eligible(session, older_than_days: int, retain_days: int) -> dict:
    # {"exported": [<per-conversation dict>, …],
    #  "skipped":  [<per-conversation dict>, …]}
```

Per conversation:

1. read every message in `seq` order
2. `verify_conversation_chain(messages)` — a break aborts *this* conversation, records it in the summary, and leaves the others to proceed
3. serialise, upload with Object Lock, insert the `conversation_exports` row

A conversation with no messages is skipped: there is nothing to preserve, and
an empty object would be an assertion that the conversation was empty at a
moment nothing recorded.

**Re-export is safe and is not deduplicated.** If the head has not moved, a
second call writes a second object with identical content. Suppressing that
would mean trusting the marker table to decide whether evidence exists, and the
marker table is mutable while the objects are not.

---

## 5. Purge

`app/services/conversation_purge.py`:

```python
async def purge_eligible(session, older_than_days: int, confirm: bool = False) -> dict:
    # {"dry_run": bool,
    #  "conversations": [{"conversation_id", "messages", "object_key"}, …],
    #  "messages_deleted": int}     # 0 whenever dry_run is true
```

A conversation is eligible when **all** of:

- `updated_at < now - older_than_days` — `append_messages_locked` sets
  `updated_at` on every append, so this is genuinely last activity
- `purged_at IS NULL`
- an export row exists with `head_seq == max(seq)` for that conversation (D5)

Tombstoned conversations are included rather than special-cased: a deleted
conversation old enough to dispose of is the most obvious candidate there is,
and D6 already decided that age, not deletion state, is what governs.

With `confirm=False` the summary lists what would go and nothing is written.
With `confirm=True`, per conversation: delete its messages, set `purged_at` and
`export_key`, and write one `record_action` audit row —
`conversation.purged`, `action_category="remediate"`, carrying the
conversation id, message count, head hash and object key.

`remediate` rather than `annotate`: the gatekeeper taxonomy already puts
irreversible external effects in that tier, and this is the one operation in
the product that destroys data.

The audit row is written **after** the delete commits, so a crash between them
leaves a purged conversation with no audit row — visible as an inconsistency —
rather than an audit row claiming a deletion that did not happen.

### 5.1 What the person sees

`ConversationResponse` gains `archived: bool` (true when `purged_at` is set).
An archived conversation still appears in the sidebar with its title and
`message_count: 0`; opening it shows an archived notice rather than an empty
transcript, because "your conversation is empty" would be a lie.

Appending to an archived conversation is refused with `409`. Resuming a
conversation whose history now exists only in WORM storage would produce a
chain starting at seq 0 again, colliding with the exported one.

Search (Round 2) returns nothing from archived conversations — their messages
are gone, so this needs no new predicate.

---

## 6. Operability

`_s3_client()` raises when `S3_ENDPOINT`/`S3_ACCESS_KEY` are unset, which is
the current state of every deployment here. The consequence is deliberate:

- export fails loudly with a message naming the missing variables
- purge therefore finds nothing eligible, because eligibility requires an export
- **no data can be deleted by a deployment that cannot archive it**

That ordering is the safety property of this whole round, so the tests assert
it rather than mocking S3 everywhere and letting it pass unnoticed.

---

## 7. Testing

**Export**
- a conversation exports with every message, in `seq` order, with its chain fields
- the object is recomputable: parsing it and re-running `verify_conversation_chain` returns `None`
- the recorded `head_hash` equals the conversation's last `entry_hash`
- a conversation with a tampered message is reported and **not** uploaded (D2)
- an empty conversation is skipped
- one conversation's failure does not stop the others

**Purge eligibility**
- an exported, old conversation is eligible
- an old conversation with no export is not
- an old conversation exported at seq 40 but now at seq 90 is not (D5)
- a recently updated conversation is not
- an already purged conversation is not

**Purge**
- `confirm=False` writes nothing at all and still reports the candidates
- `confirm=True` deletes every message and leaves the `conversations` row with `purged_at` and `export_key`
- a `conversation.purged` audit row is written and links into the global chain
- the anchor written in Round 1 still names the head hash, so the conversation is still provably accounted for

**The safety ordering**
- with S3 unconfigured, export raises and names the missing variables
- with S3 unconfigured, purge reports zero eligible conversations even for very old ones

**The person's view**
- an archived conversation is listed, with `archived: true` and `message_count: 0`
- appending to an archived conversation returns 409
- searching returns nothing from it

---

## 8. Invariant

**INV-44: nothing is deleted that was not first archived.** A conversation's
messages may be removed only when an export object holds every one of them with
its chain intact, the conversation row survives naming that object, and the
deletion is recorded in the global audit chain.
