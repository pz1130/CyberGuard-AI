# Chat Message Storage — Round 1: a messages table with a per-conversation hash chain

**Date:** 2026-09-16
**Scope:** Move chat history out of `conversations.messages_json` into an append-only `conversation_messages` table, hash-chained per conversation and anchored into the global audit chain.
**Goal:** Make what the assistant actually said into evidence, and make appending a message cost the same on turn 500 as on turn 1.

**Rounds 2 and 3** — user-scoped keyword search, and retention/WORM export — get their own specs. §8 states what this round must not foreclose for them.

---

## 1. What exists, and what does not

Investigated before designing, because the answers decide the shape.

| Question | Answer |
|---|---|
| Where does chat history live? | `conversations.messages_json`, a single `Text` column holding a JSON array (`app/models/conversation.py:21`). No messages table exists. |
| What does an append cost? | The whole array is parsed, appended to and re-serialised on every message (`app/services/conversation_messages.py:append_messages_locked`). Cost is proportional to the history so far. |
| Is the history tamper-evident? | **No.** `PUT /conversations/{id}` accepts `messages_json` as a plain string field (`app/routers/conversations.py:56`) and writes it verbatim. Any client holding the user's token can replace the entire transcript, and nothing records that it happened. |
| Is the assistant's answer recorded anywhere tamper-evident? | **No.** `agent_run_events` is a real hash chain and it records that an answer was produced — `payload={"status": "answer_ready"}` (`packages/agent_core/run_loop.py:300`) — but not the answer text. Tool calls *are* evidenced, with arguments (`packages/agent_core/pipeline.py:115`). |
| Is there an existing per-scope chain to copy? | **Yes.** `app/services/run_event_log.py` chains `agent_run_events` per `run_id`, with an in-memory cursor re-derived from the table on a cold process. No global lock. |
| How does the global audit chain serialise? | One process-wide `asyncio.Lock` plus `pg_advisory_xact_lock(0xA0D17)` per flush (`app/core/audit.py:111-118`). Every audit write in the deployment queues behind it. |
| How does search work today? | Client-side. `GlobalSearch.tsx` calls `getConversations()` — capped at the 50 most recent by `list_conversations` — parses each `messages_json` in the browser and greps it. Older conversations are invisible to search, and every message is shipped to the browser to look at it. |
| Does every append take the row lock? | **No.** `chat_stream.py:187-191` does a raw read-modify-write with no `FOR UPDATE`, bypassing `append_messages_locked` entirely. Under `API_WORKERS>1` a concurrent append is silently lost. |

### 1.1 The gap that motivates this round

The user's stated requirement: *"万一 AI 犯错了，我们还有证据证明是 AI 做的，什么时候做的，做了什么"* — if the AI gets something wrong, we need proof of what it did and when.

For an assistant giving security advice, **what it said is the thing that could be wrong.** Today the tool calls are evidence and the words are not; the words live in a blob that a `PUT` can rewrite. That is the hole this round closes.

---

## 2. Decisions

| # | Decision | Rejected alternative and why |
|---|---|---|
| D1 | One row per message in a new `conversation_messages` table. | Keeping a JSON array, even as `JSONB` with `jsonb_insert`: Postgres rewrites the whole (TOASTed) datum on every update, so the append stays O(history). It also gives a message no identity of its own to hash, index or cite in an export. |
| D2 | **Per-conversation** hash chain: `prev_hash` points at the previous message *in that conversation*. | Joining the global `audit_logs` chain: every message in every conversation would serialise on `pg_advisory_xact_lock(0xA0D17)`. Chat volume is orders of magnitude above audit volume — the fix would create a worse bottleneck than the one it removes. `run_event_log.py` already sets the per-scope precedent. |
| D3 | Each conversation's chain head is periodically **anchored** into the global audit chain via `record_action`. | A per-conversation chain alone: it proves no message inside a conversation was altered, reordered or removed, but not that a whole conversation existed. Deleting every row of one chain leaves nothing inconsistent. The anchor is what makes a vanished conversation detectable. |
| D4 | `(conversation_id, seq)` carries a **unique constraint**, and a losing concurrent insert retries against the re-read head. | Relying on the in-memory cursor alone, as `run_event_log._cursor_for` does: two API workers appending to the same conversation would compute the same `seq` and write a forked chain that verifies as intact. This is a latent defect in the run-event chain too (§7.3). |
| D5 | `messages_json` is **removed from `ConversationUpdate`**. Message content reaches the database only through the append path. | Leaving the field: it is a one-request transcript rewrite, which contradicts the whole round. No frontend code sends it — only reads it (`GlobalSearch.tsx`, `api/client.ts:308`), and both move to the new read path. |
| D6 | Deleting a conversation becomes a **tombstone** (`deleted_at`), not a row deletion. Hidden from every UI listing; rows retained. | `db.delete(conv)` with the existing cascade: immutability-first — the user's stated priority — means a user cannot erase the record of what the AI told them. Hard expiry belongs to the retention policy in Round 3, not to a button in the chat sidebar. |
| D7 | The migration backfills existing `messages_json` into the table, and every backfilled row is flagged `backfilled=true`. | An unflagged backfill: hashes computed at migration time prove only that nothing changed *after* the migration. Presenting them as if they covered the mutable-blob era would make the trail claim more than it can support. |
| D8 | The `messages_json` **database column** stays as a legacy column that no code reads or writes, dropped in a later migration. (The API fields of the same name do go, per D5 and §5.) | Dropping the column in the same migration: a rollback would lose history that exists nowhere else at that moment. |

---

## 3. Schema

```sql
CREATE TABLE conversation_messages (
    id              BIGSERIAL PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    seq             INTEGER NOT NULL,
    role            VARCHAR(32)  NOT NULL,
    content         TEXT         NOT NULL,
    -- ties a message to the tool-level evidence already in agent_run_events
    run_id          VARCHAR(64),
    turn_id         VARCHAR(64),
    created_at      TIMESTAMP    NOT NULL,
    backfilled      BOOLEAN      NOT NULL DEFAULT FALSE,
    prev_hash       VARCHAR(64)  NOT NULL,
    entry_hash      VARCHAR(64)  NOT NULL,
    CONSTRAINT uq_conv_messages_seq UNIQUE (conversation_id, seq)
);
CREATE INDEX ix_conv_messages_conv_seq ON conversation_messages (conversation_id, seq);
```

`ON DELETE CASCADE` is kept so that a conversation removed by a genuine
administrative purge (Round 3) does not strand rows. D6 means the ordinary
delete button never reaches it.

`role` carries **no** check constraint: `user` and `assistant` are what the
chat paths write today, but `internal_agent` memory slices and any later
tool-message support would add more, and a constraint would turn that into a
migration. `content` is `NOT NULL`; the append path coerces a missing or `None`
content to `""` rather than rejecting it, because a message that reaches the
persist path must end up in the chain — dropping it to keep the column clean
would put a hole in the evidence.

On `conversations`:

```sql
ALTER TABLE conversations ADD COLUMN deleted_at TIMESTAMP NULL;
ALTER TABLE conversations ADD COLUMN last_anchored_seq INTEGER NOT NULL DEFAULT -1;
```

Migration id: `041_conversation_messages` (≤32 chars — `alembic_version.version_num` is `varchar(32)`).

### 3.1 What the hash covers

```
entry_hash = sha256(f"{conversation_id}|{seq}|{role}|{content}|"
                    f"{created_at.isoformat()}|{run_id or ''}|{turn_id or ''}|{prev_hash}")
```

Genesis `prev_hash` is `"0" * 64`, matching `audit._GENESIS` and
`run_event_log._GENESIS`.

`created_at` is inside the hash, so its origin matters: the append path keeps a
`created_at` already present on the incoming message and otherwise stamps
`utc_now()` — the behaviour `stamp_message` has today, preserved so that
backfilled rows keep the timestamps the blob recorded.

`backfilled` is deliberately **outside** the hash: it is a statement about the
row's provenance, not about the message, and including it would make the flag
unfixable if a later migration needed to correct it. The anchor record carries
the provenance claim instead (§4.1).

---

## 4. The append path

`app/services/conversation_messages.py` keeps its public shape — the callers in
`conversations.py`, `chat_stream.py`, `workers/tasks.py` and
`internal_agent.py` keep calling `append_messages_locked` — and changes
underneath:

```
append_messages_locked(session, conv_id, new_messages, user_id=None)
  ├─ SELECT conversation FOR UPDATE            (unchanged; ownership check too)
  ├─ SELECT seq, entry_hash FROM conversation_messages
  │       WHERE conversation_id = :id ORDER BY seq DESC LIMIT 1
  ├─ for each message: stamp seq, prev_hash, entry_hash; INSERT
  └─ conv.updated_at = utc_now()
```

The head is read fresh under the row lock rather than cached, which is what
makes D4's unique constraint a backstop rather than the primary mechanism. The
row lock already serialises writers within one conversation — that behaviour is
unchanged from today — and writers in *different* conversations no longer touch
anything in common.

`chat_stream.py:187-191` is rewritten to call `append_messages_locked`. Its
current raw read-modify-write is a pre-existing lost-append bug (§1); leaving
it would additionally mean a message that never enters the chain.

### 4.1 Anchoring

A Celery beat task, on the existing beat schedule (`app/workers/tasks.py:438`),
every 15 minutes:

```
for each conversation where last_anchored_seq < max(seq):
    head = latest message row
    record_action(
        user_id=conv.user_id,
        action="conversation.chain_anchor",
        action_category="annotate",
        input_data={"conversation_id": conv.id, "from_seq": conv.last_anchored_seq + 1},
        output_data={"head_seq": head.seq, "head_hash": head.entry_hash,
                     "backfilled_through": <last backfilled seq, or None>},
    )
    conv.last_anchored_seq = head.seq
```

One audit row per *active* conversation per interval, not per message — the
volume the global lock can absorb. `record_action` is the existing synchronous
chained writer (`app/core/audit.py:302`).

What this buys: a conversation whose rows are deleted wholesale still has an
anchor in the global chain naming its head hash and sequence, so its absence is
visible. What it does not buy: messages appended since the last anchor and then
removed before the next one. That window is the interval, and narrowing it is a
question of schedule, not of design.

---

## 5. The read paths

| Caller | Today | After |
|---|---|---|
| `GET /conversations/{id}/messages` | parses the whole blob | `ORDER BY seq` with `limit` (default 200, max 1000) and `before_seq` query params; unchanged response shape (`{"messages": [...]}`) so the existing client keeps working without a change |
| `list_conversations` → `ConversationResponse.messages_json` | ships every message of 50 conversations | field removed; a `message_count` and a `last_message_preview` replace it |
| `internal_agent._load_memory` | loads all messages, returns `msgs[-memory_window:]` | `ORDER BY seq DESC LIMIT memory_window`, reversed |
| `chat_stream` history load | loads all, slices `msgs[-20:]` | `ORDER BY seq DESC LIMIT 20`, reversed |
| `GlobalSearch.tsx` | greps parsed blobs client-side | out of scope this round; it degrades to title-only conversation matching until Round 2 gives it a server-side endpoint |

The `GlobalSearch` degradation is a real, temporary loss of function and is
stated as such rather than hidden: today's version only ever searched the 50
most recent conversations, so Round 2 replaces a partial capability with a
complete one. If that gap is not acceptable across the two rounds, the ordering
should change — that is the user's call, not an assumption this spec makes.

---

## 6. Performance: what this fixes, and what was never the problem

Three distinct costs grow with conversation length. This round addresses one of
them; the second is already handled; the third is one this design must avoid
creating.

**6.1 Append and read cost — fixed here.** Today message *n* costs
proportional to the total size of messages 1…n−1, because the array is
rewritten. After D1 it is a single `INSERT`: constant, whatever the history.
Reads become pageable instead of all-or-nothing.

**6.2 LLM context size — already handled, and independent of storage.**
`internal_agent.py:125` sets `memory_window` (default 20) and `_load_memory`
returns only that slice; `_maybe_compact` summarises against
`remaining_budget(context_window)` (`app/core/context_compressor.py`). A
1000-message conversation already sends 20 messages to the model. This round
makes that slice *cheaper to fetch* (§5) but does not change what is sent.

**6.3 Chain serialisation — the bottleneck this design exists to avoid.**
See D2. A global chain would put every message behind one advisory lock. The
per-conversation chain serialises only writers to the same conversation, which
the existing `FOR UPDATE` row lock already does today, so concurrency is no
worse than the status quo and considerably better across conversations.

---

## 7. Testing

**7.1 The chain.** The verifier is
`verify_conversation_chain(messages) -> Optional[str]`, mirroring
`run_event_log.verify_chain`: `None` when intact, otherwise a string naming the
first row that breaks.

- appending yields `seq` 0,1,2… with `prev_hash` linking each to the last
- a verifier over a conversation's rows returns `None` for an intact chain
- mutating one row's `content` makes the verifier name that row
- deleting a middle row makes the verifier name the break
- reordering two rows' `seq` makes the verifier name the break
- two conversations interleave without affecting each other's chains

**7.2 Immutability.**
- `PUT /conversations/{id}` with a `messages_json` body does not change any message (the field is gone from the schema, so this is a regression guard on the hole in §1)
- `DELETE /conversations/{id}` leaves the message rows and sets `deleted_at`
- a soft-deleted conversation does not appear in `list_conversations`

**7.3 Concurrency.** Two `append_messages_locked` calls against the same
conversation from separate sessions produce `seq` 0 and 1, never two rows at
`seq` 0. This is the test that would have caught the latent fork in
`run_event_log._cursor_for` (D4); that defect is **not** fixed in this round —
it is a separate change to a shipped, tested component — but it is recorded
here so it is not rediscovered as a surprise.

**7.4 Anchoring.**
- the task writes one `conversation.chain_anchor` audit row per active conversation and advances `last_anchored_seq`
- a second run with no new messages writes nothing
- the anchored `head_hash` equals the conversation's current head

**7.5 Backfill.** A conversation with a populated `messages_json` migrates to
rows with matching content in order, all flagged `backfilled=true`, forming a
chain that verifies.

**7.6 Cost.** Appending to a conversation with 500 existing messages issues the
same number of statements, and writes the same number of bytes, as appending to
an empty one. Asserted on statement count and inserted-row size, not on wall
clock, so it does not flake on a loaded machine.

---

## 8. What this round must not foreclose

**Round 2 — search.** The messages table is the index target. A `tsvector`
column with a GIN index over `content`, scoped by joining
`conversations.user_id`, answers *"在我的对话里找关键词"* on the server for the
whole history rather than the 50 most recent in the browser. Nothing in this
round should make `content` anything other than a plain queryable column —
which is why it is `TEXT` and not, say, compressed or encrypted at rest.

**Round 3 — retention and export.** `audit_worm_exports` is the pattern to
copy: a marker table recording `last_message_id`, `object_key`, `rows` and
`retain_until` (`app/models/audit_worm.py`). `conversation_messages.id` being a
monotonic `BIGSERIAL` is what makes an incremental export possible, and
`deleted_at` (D6) is what gives the retention job something to expire rather
than the user's delete button.

---

## 9. Invariant

**INV-43: the assistant's words are evidence.** Every message persisted to a
conversation enters a hash chain before it is readable, no API accepts a
message-content write outside that path, and each conversation's chain head is
anchored into the global audit chain.
