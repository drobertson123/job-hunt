# Corpus & Profile UI — Canvas-pane tabs

**Date:** 2026-06-12
**Status:** Approved design, not yet implemented
**Decided with user:** tabs inside the Canvas pane (option A of A/B/C layout
mockups); profile is read-only (re-synthesize to change it); OpenAI key field
added to the Settings badge even though the user will primarily use
`OH_OPENAI_API_KEY`.

## Goal

The corpus/profile backend (Phase 2 slice B) is fully functional but API-only:
`/api/corpus/documents` (paste), `/api/corpus/documents/upload` (multipart),
list/delete, `/api/corpus/profile/synthesize`, `/api/corpus/profile`. Build the
frontend so a user can run the whole flow — add career docs, synthesize, view
the profile — without `curl`.

## Scope

- **In:** Profile tab in the Canvas pane (corpus document management + profile
  view); API-client functions for all six corpus endpoints; OpenAI key field in
  the Settings badge; error surfacing for the three known 400s (missing OpenAI
  key, unsupported file type, empty corpus).
- **Out:** profile editing (re-synthesize is the only mutation); backend
  changes of any kind; corpus search UI (the agent uses `search_corpus`
  internally); pagination (single-user corpus stays small); frontend unit-test
  infrastructure.

## 1. Component structure

`frontend/app/page.tsx` is 376 lines; new UI goes in new files.

```
frontend/app/components/ProfileTab.tsx   # new — all Profile-tab UI
frontend/lib/api.ts                      # extended — corpus types + functions
frontend/app/page.tsx                    # modified — tab state + tab bar + OpenAI key field
```

`ProfileTab.tsx` exports `ProfileTab` and keeps `DocumentRow`, `PasteForm`,
and `ProfileCard` as private components in the same file. It owns its own
state (documents, profile, busy flags, error strip) and fetches on mount —
`Home` passes nothing; the tab is self-contained.

`Home` gains `canvasTab: "workspace" | "profile"` state. The Canvas pane
header (`Canvas — Artifacts (n) · Notes (n)`) becomes a two-tab bar:
**Workspace** (exactly today's artifacts + notes rendering) and **Profile**
(the new component). Inactive tab content unmounts (no hidden iframe-style
keep-alive; ProfileTab refetches on each mount, which doubles as refresh).

## 2. API client additions (`frontend/lib/api.ts`)

Follow the file's existing conventions: typed fetch wrappers that throw
`Error` with the server's `detail` when available (the `exportArtifact`
pattern).

```ts
export type CorpusDocument = {
  id: number; title: string;
  source_kind: "upload" | "paste";
  media_type: "pdf" | "docx" | "txt" | "md";
  char_count: number;
};
export type Profile = {
  id: number; headline: string | null; summary: string | null;
  skills: string[]; experience: Record<string, unknown>[];
  achievements: string[]; target_titles: string[]; locations: string[];
  source_doc_count: number; synthesized_at: string;
};

fetchDocuments(): Promise<CorpusDocument[]>          // GET  /api/corpus/documents
uploadDocument(file: File, title?: string)           // POST /api/corpus/documents/upload (FormData; no Content-Type header — browser sets the boundary)
pasteDocument(title: string, text: string)           // POST /api/corpus/documents (JSON)
deleteDocument(id: number)                           // DELETE /api/corpus/documents/{id}
synthesizeProfile(): Promise<Profile>                // POST /api/corpus/profile/synthesize
getProfile(): Promise<Profile | null>                // GET  /api/corpus/profile (200 with null body when absent)
```

## 3. Profile tab behavior

Vertically stacked (the pane is half-width on desktop, full-width stacked on
mobile): documents section on top, profile section below.

**Documents section**
- Header `Corpus documents (n)`.
- Each row: title, `source_kind · media_type · {char_count} chars`, delete
  button gated by `confirm()`.
- **Upload file**: hidden `<input type="file" accept=".pdf,.docx,.txt,.md">`
  triggered by a button; uploads immediately on selection, filename becomes
  the title.
- **Paste text**: toggles an inline form (title input + textarea + Add
  button); clears and collapses on success.
- Both refetch the document list on success and disable while a request is
  in flight.
- Empty state: "No documents yet — upload your resume to get started."

**Profile section**
- Header row: `Synthesized profile` label + **Synthesize** button
  (relabelled **Re-synthesize** when a profile exists). Disabled with a
  spinner/`…` while running — this is an LLM call that can take tens of
  seconds.
- Read-only `ProfileCard`: headline (bold), summary paragraph, skills as
  chips, experience entries (render `title`/`organization`/`period`-ish keys
  defensively — entries are model-produced dicts, so unknown shapes fall back
  to a compact key: value line), achievements / target titles / locations as
  short lists, footer `From {source_doc_count} documents · synthesized {local
  datetime}`.
- Empty state: "No profile yet — add documents, then synthesize."

**Error strip**
- Any failed request sets one dismissible amber strip at the top of the tab
  showing the server's `detail` verbatim (e.g. "OpenAI API key is not
  configured (Settings or OH_OPENAI_API_KEY)."). New errors replace the old;
  any success clears it.

## 4. Settings badge

Add an "OpenAI API key (embeddings)" password field between the Anthropic key
and the model field, mirroring the Anthropic field exactly: placeholder shows
`••••• (set)` when `settings.openai_key_configured`, sends
`openai_api_key` in the existing `updateSettings` body only when non-empty.

## 5. Error handling summary

| Failure | Where it surfaces |
|---|---|
| 400 missing OpenAI key (ingest) | error strip, server message verbatim |
| 400 unsupported file type | error strip |
| 400 empty corpus (synthesize) | error strip |
| network/5xx | error strip with status fallback |

## 6. Testing & verification

No backend changes — pytest suite untouched and must stay green.
Frontend has no unit-test infra (repo convention); verification is:

1. `NODE_ENV=production npm --prefix frontend run build` passes (static
   export is the production artifact).
2. Live seam check against the running server with `OH_OPENAI_API_KEY` set:
   paste a doc → row appears; upload a `.md` → row appears; synthesize →
   profile renders with chips and footer; delete a doc → list updates;
   missing-key path (key unset) shows the error strip.
