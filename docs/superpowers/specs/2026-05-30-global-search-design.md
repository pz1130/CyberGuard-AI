# Global Search (CTRL+K) — Design Spec

**Date:** 2026-05-30  
**Status:** Approved

---

## Overview

Implement a functional CTRL+K command-palette-style search modal for CyberGuard. The current search bar in the Header is a visual placeholder with no behavior. This spec covers making it fully functional.

---

## Scope

**In scope:**
- CTRL+K keyboard shortcut opens a search modal globally
- Clicking the Header search bar also opens the modal
- Search across 6 data sources: Agents, Providers, Skills, Tools, Knowledge Bases, MCP Servers
- Keyboard navigation within results (↑↓ / Enter / ESC)
- On result select: navigate to corresponding tab + scroll-to and flash-highlight the matched item
- Empty state: show 3 recently visited tabs as quick-jump shortcuts

**Out of scope:**
- Server-side search endpoint (all filtering is client-side)
- Full-text search within conversation messages or documents
- Fuzzy matching (simple case-insensitive substring match is sufficient)

---

## Architecture

### New files
- `webui/src/context/SearchContext.tsx` — React context carrying `searchTarget`
- `webui/src/components/GlobalSearch.tsx` — modal component

### Modified files
- `App.tsx` — wrap tree in `SearchContext.Provider`; mount `<GlobalSearch>`; add CTRL+K `keydown` listener; pass `setTab` + `setSearchOpen` to `GlobalSearch`
- `Header.tsx` — clicking search input calls `openSearch()` instead of doing nothing
- `Agents.tsx`, `Providers.tsx`, `Skills.tsx`, `Tools.tsx`, `Knowledge.tsx`, `MCP.tsx` — each adds a small `useEffect` to read `SearchContext` and highlight the matching row

### SearchContext shape
```ts
interface SearchTarget {
  tab: Tab
  id: number | string
  name: string
}

interface SearchContextValue {
  searchTarget: SearchTarget | null
  setSearchTarget: (t: SearchTarget | null) => void
}
```

---

## Data Loading

When the modal opens for the first time, fetch all 6 endpoints in parallel:

| Source | Endpoint | Display fields |
|--------|----------|----------------|
| Agents | `GET /agents` | `agent_name`, `backend_type` |
| Providers | `GET /providers` | `name`, `provider_type` |
| Skills | `GET /skills` | `name`, `description` |
| Tools | `GET /tools` | `name`, `description` |
| Knowledge | `GET /knowledge/bases` | `name` |
| MCP | `GET /mcp/servers` | `name`, `url` |

Results are cached in `GlobalSearch` component state for the session lifetime (no re-fetch on subsequent opens). Each result item stores: `{ id, name, subtitle, tab, category }`.

---

## Search Algorithm

- Trigger: on every keystroke (no debounce needed for client-side filtering of <1000 items)
- Match: case-insensitive substring on `name` + `subtitle`
- Ranking: exact prefix match first, then any substring match
- Max results displayed: 5 per category, 30 total

---

## UI Specification

**Modal:**
- Position: fixed, centered horizontally, top ~20% of viewport
- Width: 600px (max-width: 90vw)
- Max height: 70vh, results area scrollable
- Backdrop: `rgba(0,0,0,0.7)`, click to close
- Border: `1px solid var(--accent-border)`
- Background: `var(--bg-elevated)`

**Search input row:**
- Left icon: `⬡` in accent color
- Input: full width, no border, font-size 16px, monospace
- Right: `ESC` label in dim text
- Bottom border: `1px solid var(--border-bright)` separating input from results

**Results list:**
- Category header: small caps, `var(--text-dim)`, e.g. `AGENTS`
- Result row height: 40px, padding `0 16px`
- Row layout: `[icon] name (bold match highlighted)  subtitle`
- Selected row: background `var(--accent-dim)`, left border `2px solid var(--accent)`
- Match text: wrap matched portion in `<mark>` styled with accent color, no background

**Empty state:**
- Query entered, no results: centered text `NO RESULTS — TRY ANOTHER QUERY`
- Empty query: show 3 most recently visited tabs as `RECENT` section

---

## Keyboard UX

| Key | Action |
|-----|--------|
| CTRL+K | Open modal (global) |
| ESC | Close modal |
| ↑ / ↓ | Move selection through results |
| Enter | Select current result |
| Any char | Focus jumps to search input |

---

## Navigation & Highlight Behavior

On result selection:
1. Close modal (`setSearchOpen(false)`)
2. `setTab(result.tab)` — switch to target page
3. `setSearchTarget({ tab, id, name })` — publish to context

On target page (via `useEffect` watching `searchTarget`):
1. Find the DOM element with `data-item-id={id}` (each list row gets this attribute)
2. `element.scrollIntoView({ behavior: 'smooth', block: 'center' })`
3. Add CSS class `search-highlight` (green flash animation, 2s)
4. After 2s, call `setSearchTarget(null)` to clear

**CSS animation** (added to `index.css`):
```css
@keyframes search-highlight-flash {
  0%   { background: var(--accent-dim); }
  60%  { background: var(--accent-dim); }
  100% { background: transparent; }
}
.search-highlight {
  animation: search-highlight-flash 2s ease forwards;
}
```

---

## Error Handling

- If a fetch fails during data load, that category is silently omitted from results (no crash)
- If the target item no longer exists when navigating (stale cache), the page just shows normally with no highlight

---

## Testing

- Open modal with CTRL+K ✓
- Open modal by clicking Header search bar ✓
- Type query → results filter in real time ✓
- ↑↓ keyboard navigation wraps around ✓
- Enter selects, closes modal, navigates to page ✓
- ESC closes modal ✓
- Click backdrop closes modal ✓
- Clicking result for an Agent scrolls to and highlights the row in Agents page ✓
- Empty query shows recent tabs ✓
- No results shows empty state message ✓
