---
name: evidence_handling
description: Chain-of-custody basics — hash, read-only mount, notes, export hygiene
version: "1.0.0"
requires_tools: []
mode: both
---

# SOP · Evidence handling

For files, disk images, memory dumps, or exports used as investigation evidence:

1. **Copy first** when possible; work on a working copy, keep original read-only.
2. **Hash** (sha256) before analysis; record filename, size, hash, acquired_at, source.
3. **Minimize mutation**: prefer tools that do not rewrite the evidence.
4. **Notes**: who acquired, how, authorization, system clock source.
5. **Export**: only to user-chosen locations; never auto-sync sensitive evidence.
6. **Output** evidence index table:
   | id | path/name | sha256 | source | trust | notes |

Constraints:

- Sandbox writable roots are for work product, not long-term evidence vaults.
- Do not store secrets inside evidence notes in plaintext if avoidable.
- Tool-returned "hashes" from hostile sources are claims until recomputed locally.
