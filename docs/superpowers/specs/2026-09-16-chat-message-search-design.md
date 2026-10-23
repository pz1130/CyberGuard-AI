# Chat Message Storage — Round 2: user-scoped keyword search

**Date:** 2026-09-16
**Scope:** A server-side endpoint that searches the caller's own chat messages, and the `GlobalSearch` pane rewired to use it.
**Goal:** Answer *"在我的对话里找关键词"* — the original request — across the whole history rather than the 50 most recent conversations in the browser.

**Builds on:** Round 1 (`docs/superpowers/specs/2026-09-16-chat-message-storage-design.md`). The `conversation_messages` table, its `id`, and `conversations.deleted_at` are reused unchanged.

**Round 3** — retention and WORM export — keeps its own spec. §7 states what this round must not foreclose.

---

## 1. What the investigation changed

Round 1 §8 said the index target would be "a `tsvector` column with a GIN index over `content`". **That was written without testing it, and it is wrong for this product.** Measured against the running deployment (PostgreSQL 16.13):

```
to_tsvector('english', '扫描主机的开放端口')  ->  '扫描主机的开放端口':1
to_tsvector('simple',  '扫描主机的开放端口')  ->  '扫描主机的开放端口':1
… @@ plainto_tsquery('simple','端口')         ->  f
```

PostgreSQL tokenises an entire Chinese sentence as **one lexeme**. A search for 端口 inside 扫描主机的开放端口 does not match; only the whole string does. `zhparser` is not present in the image, and `default_text_search_config` is `pg_catalog.english`.

Full-text search is therefore unusable for this product's content, which is bilingual. `pg_trgm` is available and is the route this round takes.

### 1.1 What pg_trgm actually does here

Measured on 200,000 rows with a `gin (content gin_trgm_ops)` index:

| Query | Index behaviour |
|---|---|
| `firewall` (English) | Fully selective; resolved from the index without touching the heap |
| `防火墙` (3 chars) | Fully selective — index scan returned exactly the 66,667 matching rows |
| `开放端口` (4 chars) | Fully selective |
| **`端口` (2 chars)** | **No selectivity** — the index scan returned all 200,000 rows and a recheck discarded 133,334. The planner correctly preferred a sequential scan. |

Two Chinese characters is the common case for a search term (端口, 漏洞, 密码, 主机), so this is not an edge case to wave away. §3 is built around bounding it rather than pretending it is solved.

### 1.2 Why the candidate set is what saves it

Search is scoped to one user. Measured with the real join shape — a partial index on the owner, then the messages of each of their conversations:

```
Nested Loop (actual rows=333)
  -> Bitmap Index Scan on c_user (actual rows=10)          -- the user's conversations
  -> Bitmap Index Scan on msg_conv (actual rows=100, loops=10)
     Filter: content ILIKE '%端口%'   Rows Removed: 67
```

A 2-character Chinese query reads **1,000 rows** — that user's messages — not the deployment's 200,000. A heavy account with 20,000 messages reads 20,000, still milliseconds.

---

## 2. Decisions

| # | Decision | Rejected alternative and why |
|---|---|---|
| D1 | `pg_trgm` GIN index on `content`, queried with `ILIKE`. | `tsvector` + GIN (§1): one lexeme per Chinese sentence, so it cannot match a keyword inside one. |
| D2 | A **partial** index `conversations (user_id) WHERE deleted_at IS NULL`. | A plain index plus a `deleted_at IS NULL` predicate: the partial index makes "a tombstoned conversation is not searchable" a property of the index rather than of every query that remembers to filter. |
| D3 | The owner is reached by **joining `conversations`**; `user_id` is *not* denormalised onto `conversation_messages`. | Denormalising: §1.2 shows the join already resolves in two index lookups, and a duplicated owner column is a value that can drift from the one the permission check uses. |
| D4 | A **composite `gin (user_id, content gin_trgm_ops)`** index is not used. | Measured: GIN requires every term to produce candidates, and a 2-character CJK pattern produces terms matching every row, so the AND still yields the whole table. It helps English and nothing else — two separate indexes do the same job with less to maintain. |
| D5 | The caller is taken from the token; the endpoint accepts **no** `user_id`. | A `user_id` parameter would make this an admin endpoint wearing a self-service name — the same reasoning as `POST /auth/change-password`. |
| D6 | `%`, `_` and `\` in the query are escaped, with `ESCAPE '\'`. | Passing the query through: a search for `100%` would otherwise become a wildcard and match everything, and `_` would match any character. |
| D7 | Results carry a **snippet** around the hit, not the message body. | Returning full messages: one long transcript would dominate the payload, and the pane only renders a preview line. |
| D8 | Paged on `conversation_messages.id DESC` with a cursor. | `OFFSET`: it re-reads and skips, and shifts when a message is appended mid-scroll. The monotonic `BIGSERIAL` from Round 1 exists for exactly this. |
| D9 | Internal-agent memory slices (`agent_id IS NOT NULL`) are excluded, in the index predicate and the query. | Including them: they are `conversations` rows owned by the user, holding an internal agent's own working memory. A person searching their chat history means the conversations they had, not an agent's scratchpad. See §3.1. |

---

## 3. Schema

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- The caller's live, human-facing conversations. Partial, so a tombstoned or
-- agent-internal row is absent from the index rather than filtered out by each
-- query that remembers to.
CREATE INDEX ix_conv_user_live ON conversations (user_id)
    WHERE deleted_at IS NULL AND agent_id IS NULL;

-- Content matching. Carries English and any query of three characters or more;
-- a two-character CJK query gets no selectivity from it (§1.1) and is bounded
-- instead by the owner index above.
CREATE INDEX ix_conv_messages_content_trgm
    ON conversation_messages USING gin (content gin_trgm_ops);
```

Migration id: `044_conversation_search` (≤32 chars — `alembic_version.version_num` is `varchar(32)`).

`conversations.user_id` has no index today at all, so D2 also makes the existing `list_conversations` cheaper.

### 3.1 A listing bug this round has to fix anyway

`InternalAgentRunner._get_or_create_slice_row` stores each internal agent's
memory as a `conversations` row: `user_id` set to the person, `agent_id` and
`parent_conversation_id` set, `title` of `agent:<name>`
(`app/services/internal_agent.py:181`). `list_conversations` filters only on
`user_id` and `deleted_at`, so **those slices already belong in the sidebar as
conversations** — no deployment has noticed because the preview database has
run no internal agents (`agent_slices = 0`).

Search would surface the same rows, and their contents are an agent's internal
working memory rather than anything the person said. The filter belongs in both
places, so `list_conversations` gets `agent_id IS NULL` in this round.

---

## 4. The endpoint

```
GET /api/v1/conversations/search?q=<term>&limit=20&cursor=<message id>
```

```json
{
  "results": [
    {
      "conversation_id": 4,
      "conversation_title": "Port scan triage",
      "message_id": 918,
      "seq": 12,
      "role": "assistant",
      "created_at": "2026-09-16T10:00:05",
      "snippet": "…three open ports on 10.0.0.1, including 22/tcp…"
    }
  ],
  "next_cursor": 918
}
```

- `q` is trimmed; empty is `400`. No minimum length — §1.2 makes a short query bounded rather than dangerous, and a minimum would reject 端口, which is exactly what people search for.
- `limit` defaults to 20, capped at 100.
- `next_cursor` is absent when the page is the last one.
- `conversation_title` may be `null`; the client renders its own placeholder, as it does in the sidebar.
- `next_cursor` is the `message_id` of the last row returned; pass it back to continue from the next-older message.

Ordering is `id DESC` — newest first — which matches what a person expects from "find that thing I said".

### 4.1 Snippet

Pure, in a small module beside `conversation_chain.py`: given the content and the matched term, return at most `SNIPPET_CHARS` (200) centred on the first case-insensitive hit, with an ellipsis on each truncated side. No hit — which can only happen if the row changed between index and read — yields the leading 200 characters rather than an error.

Not highlighted server-side: the client already knows the query and highlights it, the way `GlobalSearch` highlights title matches today.

---

## 5. The frontend

`GlobalSearch`'s CONVERSATIONS group calls the endpoint, debounced, instead of grepping parsed blobs. Titles keep matching client-side from the conversation list already loaded, so a title match still appears with no round trip.

This restores what Round 1 removed and goes past it: the browser version only ever searched the 50 most recent conversations, and only what was already in memory.

---

## 6. Testing

**Correctness**
- an English term and a Chinese term each find their message
- a two-character Chinese term finds its message (the case §1.1 says the index cannot accelerate — it must still be *correct*)
- the snippet is centred on the hit and is shorter than the message

**The permission boundary**
- user A's search never returns user B's message — the test that matters most, asserted against two seeded users
- the endpoint's signature accepts no `user_id` (a source-level guard, like INV-43's)

**Tombstones and agent slices**
- a message is findable, its conversation is deleted, the message is no longer findable
- the row still exists in the table afterwards (Round 1's immutability is not weakened by this round)
- a message in an internal agent's memory slice is never returned, though the slice is owned by the searching user
- `list_conversations` does not return agent slices either (§3.1)

**Escaping**
- `100%` matches a message containing the literal `100%` and does not match one containing `100 apples`
- `a_b` does not match `axb`

**Paging**
- two pages over five hits return five distinct messages with no repeats
- a `next_cursor` is absent on the final page

**The index is used**
- `EXPLAIN` for an English query on a seeded set shows the trigram index, not a sequential scan. Asserted on the plan rather than on timing, so it does not flake.

---

## 7. What this must not foreclose

**Round 3 — retention and export.** Nothing here changes `conversation_messages`' columns, so the incremental export keyed on `id` is unaffected. The partial owner index also serves a per-user export.

**A future auditor search.** The user chose user-scoped only for this round, with cross-user search deferred to Round 3 where it sits with the other auditor-facing work. This round must not make that harder: the query builder therefore takes the owner filter as a parameter rather than reading the token inside itself, so a later admin path can pass a different scope without rewriting the search.

---

## 8. The limit, stated plainly

**A two-character CJK query scans every message the user owns.** Measured at 20,000 messages it is still milliseconds, but the cost grows with that user's history rather than staying flat.

Removing it means Chinese word segmentation in the database — `zhparser` or an equivalent — which means building and maintaining a custom PostgreSQL image. That is a deployment decision with its own consequences, not a code change, and it is not made here.
