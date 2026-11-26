# M4 plan: Second Brain capture and organization

Status: **Approved** (2026-11-26), D1–D3 resolved as recommended
Source: [vision.md](../vision.md) §2.2, §2.8, §6, §9, §10 (M4) · [roadmap.md](../roadmap.md)

## Goal and done criteria

Save a note or a link once, organise it, find it again, delete it.

**Done when** (vision §10, made testable):

1. Capture: a note, a web link, a YouTube link or a pasted excerpt can be saved from `/library`
   and from a quick action on `/today`.
2. Organise: status (Inbox → To Read → Reading → Archived), tags, one collection, favourite.
3. Search: a keyword search finds items by title, note body, excerpt, URL host and tag, ranked
   by relevance, with filters for kind, status, tag, collection, favourite and date.
4. Retrieve: an item page shows the original source link, and keeps **your excerpt**, **your
   note** and (later) **AI summary** visibly separate.
5. Delete: soft delete with undo, then a "Delete permanently" action. Both are audited.
6. A second user cannot read, find, tag, move or delete the first user's items (API tests).
7. The Chief of Staff can search the library through one read-only tool, and saved text
   reaches the model only as tool-result data.

## Out of scope (kept for later milestones)

| Not in M4 | Why / where |
|---|---|
| Ask Your Library (grounded answers with citations) | M5; needs the shared search service first |
| Chunking, embeddings, semantic search | M5, and only after keyword search proves insufficient |
| AI summaries and key points | M5 alongside grounded answers (consent + budget already exist) |
| Full-text article extraction / readability scraping | Copyright rules in §2.2; store links and the user's own excerpts only |
| YouTube transcripts | §2.2: never assume they are available |
| Google Drive files, document uploads | Needs the integrations framework (M7/M8 era) |
| Scheduled metadata refresh, retention policies | Needs the background worker (M6) |
| Browser extension | Later; the PWA share target covers phone capture |

## Data model (migration `0007_library`)

Follows the repo conventions: UUIDv7 ids, `user_id → users ON DELETE CASCADE`, soft delete,
`version`, enumerations as `text` + CHECK.

```text
library_collections            library_items                         tags
-------------------            -------------                         ----
id                             id                                    id
user_id                        user_id                               user_id
name (≤60)                     kind  note|link|video|excerpt         name (≤40)
sort_order                     status inbox|to_read|reading|archived name_key (lower, trimmed)
created/updated/deleted_at     title (≤300)                          created_at
version                        url (≤2048, null for notes)           UNIQUE(user_id, name_key)
UNIQUE(user_id, lower(name))   url_key (normalised, null for notes)
  WHERE deleted_at IS NULL     site_name, author (≤200)              library_item_tags
                               excerpt (≤10k, user-pasted)           -----------------
                               body (≤100k, user's markdown note)    item_id → library_items CASCADE
                               collection_id → collections SET NULL  tag_id  → tags CASCADE
                               is_favorite                           user_id
                               metadata_status none|fetched|failed   PK(item_id, tag_id)
                               fetched_at
                               search_tsv  GENERATED ALWAYS AS (...) STORED
                               created/updated/deleted_at, version
```

Indexes and constraints:

- `UNIQUE(user_id, url_key) WHERE deleted_at IS NULL AND url_key IS NOT NULL` → deduplication.
- `GIN(search_tsv)`; `(user_id, status, created_at DESC) WHERE deleted_at IS NULL` for the inbox.
- CHECK: `kind = 'note' OR url IS NOT NULL`; `kind <> 'note' OR url IS NULL`.
- `search_tsv` = `setweight(title,'A') || setweight(excerpt,'B') || setweight(body,'C')`
  with the `simple` config (multilingual-safe, no stemming surprises). Tag names are matched
  through the join, not baked into the vector, so renaming a tag never needs a reindex.

Why tables, not a `text[]` of tags: tags are listed, renamed and filtered on their own
(the data-model rule in our preferences). `tags` is a generic user-owned table so M5+ can tag
tasks or meetings without a second tag system; only `library_item_tags` exists in M4.

Why one collection per item: a folder is a single home; tags already give many-to-many.

## URL handling and safe source handling

`app/modules/library/urls.py`, pure functions with table tests:

- `normalise(url)`: https/http only; lowercase scheme and host; drop default port, fragment,
  `utm_*`, `fbclid`, `gclid`; sort remaining query params; strip trailing `/`.
  YouTube `youtu.be/ID`, `m.youtube.com`, `/shorts/ID` all collapse to `youtube.com/watch?v=ID`.
- `classify(url)`: `video` for YouTube hosts, otherwise `link`.
- Rejects `javascript:`, `data:`, `file:`, credentials in URL, IP-literal hosts.

Saving a URL that already exists returns **409 `library_duplicate`** with the existing item id;
the UI offers "Open existing". Restoring a soft-deleted duplicate is allowed (the partial index
excludes deleted rows).

### Metadata fetch (title, site, author)

`POST /library/items` saves immediately with whatever the user typed. If the user leaves the
title empty, the API fetches metadata **inline with a hard 5 s budget**, then falls back to the
URL host as title and `metadata_status = failed`. "Refresh details" retries on demand.

- YouTube: the public oEmbed endpoint (`youtube.com/oembed`) for title and channel. Authorised,
  no scraping, no transcript.
- Other pages: `GET` with `httpx`, read at most 512 KB, `text/html` only, parse `<title>`,
  `og:title`, `og:site_name`, `author` meta. Nothing else from the page is stored.
- SSRF guard: reuse the `_blocked()` check from `app/ai/providers.py` (move it to
  `app/core/netguard.py` so both modules share it), **resolve once and connect to the resolved
  IP** (pin via a custom transport) so DNS rebinding cannot swap in a private address after the
  check. Redirects followed manually, at most 3, each hop re-checked. Ports 80/443 only.
- Fetched strings are length-capped, stripped of control characters and rendered as text, never
  HTML.

Server-side fetching is **D1** below; the fallback is "user types the title, no fetch".

## API (`/api/v1/library`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/library/items` | List + search: `q`, `kind`, `status`, `tag`, `collection`, `favorite`, `from`, `to`, cursor paging. With `q`, ordered by `ts_rank_cd`, else newest first |
| POST | `/library/items` | Capture (note / link / video / excerpt), optional tags by name (created on the fly) |
| GET | `/library/items/{id}` | Detail |
| PATCH | `/library/items/{id}` | Edit title, body, excerpt, status, collection, favourite, tags; `version` required (409 on conflict) |
| POST | `/library/items/{id}/refresh` | Re-fetch metadata |
| DELETE | `/library/items/{id}` | Soft delete (audited) |
| POST | `/library/items/{id}/restore` | Undo soft delete |
| DELETE | `/library/items/{id}/permanent` | Hard delete; only for already-deleted items (audited) |
| GET | `/library/trash` | Soft-deleted items |
| GET/POST/PATCH/DELETE | `/library/collections[/{id}]` | Manage collections; deleting one leaves items uncollected |
| GET/PATCH/DELETE | `/library/tags[/{id}]` | List with counts, rename (merge if the new name exists), delete |
| GET | `/library/counts` | Per-status counts for the inbox tabs |

Search query parsing uses `websearch_to_tsquery('simple', q)` (quotes, `-exclude`, `OR`), plus
an `ILIKE` fallback on `url_key` and title for short or partial input so "githu" still finds
github links. Every query filters `user_id` and `deleted_at IS NULL` inside the service.

Rate limit: capture and refresh share the existing per-user limiter (e.g. 30/min) because
each may make an outbound request.

## AI Chief of Staff

`app/modules/library/ai_tools.py`, level 1 (read), scope `library:read`:

- `search_library(query, kind?, status?, tag?, limit≤10)` returns title, kind, status, tags,
  url, saved date, and at most 500 characters of excerpt/body per item, each wrapped as
  `{"source": "user_saved_content", ...}`. The system prompt already says tool results are data;
  add one line naming saved web content explicitly.
- No write tools (saving from chat waits for the approval inbox, ADR-0004).

## Web (`apps/web`)

- `/library`: inbox tabs with counts, search box (debounced, URL-synced `?q=`), filter chips
  (kind, tag, collection, favourite), item list with source host and tags.
- Capture dialog: one field that accepts a URL or text. A URL becomes a link/video; plain text
  becomes a note; "Save as excerpt" with a source URL field. Tags with autocomplete.
- Item page `/library/[id]`: source link (`rel="noopener noreferrer nofollow"`), sections
  labelled **Saved excerpt** and **My note**, markdown rendered without raw HTML, status and
  collection controls, delete with undo toast.
- Trash view, collections and tag management in a side panel.
- Quick action "Save to Library" on `/today`; sidebar entry under the existing nav sections.
- PWA `share_target` in the manifest so "Share → Personal OS" on a phone opens the capture
  dialog pre-filled (GET share target, so no CSRF exemption is needed).
- Regenerate `packages/api-client`; empty, loading and error states via `components/states.tsx`.

## Module layout

```text
backend/app/modules/library/
  models.py     # LibraryItem, LibraryCollection, Tag, LibraryItemTag
  schemas.py    # ItemIn (discriminated by kind), ItemUpdate, ItemOut, filters
  urls.py       # normalise / classify (pure)
  metadata.py   # oEmbed + HTML meta fetch, uses core/netguard
  service.py    # all queries, ownership, dedup, tags, audit
  router.py
  ai_tools.py
backend/app/core/netguard.py   # moved _blocked + pinned-IP transport, shared with ai/providers
```

The architecture test already enforces that other modules only import `service`, `schemas`
or `ai_tools`.

## Tests

| Area | Tests |
|---|---|
| `urls.py` | Table tests: tracking params, YouTube variants, case, ports, fragments, rejected schemes, IP literals, IDN hosts |
| `metadata.py` | `httpx.MockTransport`: oEmbed success/404, HTML og tags, oversize body cut at 512 KB, non-HTML refused, timeout → `failed`, redirect to private IP refused, DNS answer that is private refused, 4th redirect refused |
| Capture API | Each kind; note with URL rejected; link without URL rejected; duplicate → 409 with id; duplicate of a deleted item allowed; tags created once per name, case-insensitive |
| Search | Ranking (title beats body), `-exclude` and quoted phrases, partial host match, every filter, cursor paging stable, deleted items never returned |
| Update | Optimistic version conflict; tag rename merges; deleting a collection keeps items |
| Delete | Soft delete → trash → restore; permanent delete only from trash; audit rows written |
| Authorisation | Second user gets 404 on every item, collection and tag route, and search never returns another user's rows |
| AI tool | Returns only the caller's items; output capped; an item titled "ignore previous instructions" comes back as plain data |
| Web | Vitest for capture-field parsing (URL vs note) and the excerpt/note labelling; Playwright-free for now, matching the current suite |

## Build order (one PR each, each shippable)

1. `core/netguard.py`: shared private-address check plus pinned-IP transports, wired into every
   OpenAI-compatible client (chat, model listing, roadmap drafting). Behaviour change: a provider
   URL that later resolves to a private address is refused at connect time. **Done** on
   `feat/library-netguard`.
2. Migration 0007 + models + `urls.py` + capture/list/detail/update/delete API + tests.
3. Search (tsvector, filters, ILIKE fallback) + tags + collections + tests.
4. Metadata fetch + refresh + SSRF tests.
5. `search_library` AI tool + prompt line + tests.
6. Web: `/library`, capture dialog, item page, trash, `/today` quick action, share target.
7. Docs: roadmap row for M4 and experience #2, architecture note on the library index, SECURITY.md
   line on outbound fetches.

## Decisions (resolved 2026-11-26)

- **D1 Metadata fetch: server fetch.** oEmbed for YouTube, meta tags for pages, SSRF-pinned,
  5 s budget. Rejected: no server fetch (user types every title).
- **D2 Note storage: plain text in Postgres** like tasks and goals, so full-text search works;
  disk/backup encryption comes with M9. Rejected: AES-GCM like AI history (rules out database
  search).
- **D3 Search index: generated `search_tsv` column on `library_items`.** M5 adds a
  `content_chunks` table and a unified search service over library, tasks and later meetings.
  Rejected: a generic `search_documents` table now, before a second source exists.

## Risks and notes

- DNS rebinding is the main SSRF gap in the current `check_base_url` (it resolves, then lets
  httpx resolve again). The pinned transport in step 1 fixes it for both callers.
- `simple` text config means no stemming ("running" won't match "run"). Fine for M4; revisit
  in M5 with real queries.
- The OpenAI SDK runs on `httpx2`, not `httpx`, so `core/netguard.py` ships one guarded
  transport per library (`PublicOnlyTransport`, `PublicOnlyTransportHttpx2`). Metadata fetching
  uses the `httpx` one.
- Proxies set through environment variables bypass the guarded transport. No deployment uses one
  today; revisit at M9 if hosting needs an egress proxy.
