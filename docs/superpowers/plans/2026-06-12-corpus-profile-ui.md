# Corpus & Profile UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Frontend for the existing corpus/profile backend — a Profile tab in the Canvas pane to upload/paste/delete career docs and synthesize/view the profile, plus an OpenAI key field in the Settings badge.

**Architecture:** Spec: `docs/superpowers/specs/2026-06-12-corpus-profile-ui-design.md`. Zero backend changes. Three frontend units: corpus functions in `frontend/lib/api.ts` (typed fetch wrappers, existing style), a self-contained `ProfileTab` component (owns its own fetch/state/error strip), and `page.tsx` edits (tab bar in the Canvas pane + OpenAI key field in SettingsBadge).

**Tech Stack:** Next.js 14 static export, React client components, Tailwind. No frontend unit-test infra (repo convention) — each task is verified by the production build type-checking and compiling, plus a final live seam check.

**Verification convention:** `NODE_ENV=production npm --prefix frontend run build` must exit 0 ("Compiled successfully", static export to `frontend/out/`). That replaces the test-run steps a TDD plan would have; the backend pytest suite must stay untouched and green.

---

### Task 1: Corpus API client (`frontend/lib/api.ts`)

**Files:**
- Modify: `frontend/lib/api.ts` (append after `updateSettings`, ~line 188; plus one refactor of `exportArtifact`)

- [ ] **Step 1: Add types, a shared error helper, and the six corpus functions**

Append to `frontend/lib/api.ts`:

```ts
// ----- corpus & profile (spec: 2026-06-12-corpus-profile-ui-design.md) -----

export type CorpusDocument = {
  id: number;
  title: string;
  source_kind: "upload" | "paste";
  media_type: "pdf" | "docx" | "txt" | "md";
  char_count: number;
};

export type Profile = {
  id: number;
  headline: string | null;
  summary: string | null;
  skills: string[];
  experience: Record<string, unknown>[];
  achievements: string[];
  target_titles: string[];
  locations: string[];
  source_doc_count: number;
  synthesized_at: string;
};

/** Throw an Error carrying the server's `detail` when present. */
async function throwDetail(res: Response, fallback: string): Promise<never> {
  let detail = fallback;
  try {
    detail = (await res.json()).detail ?? detail;
  } catch {
    /* keep fallback */
  }
  throw new Error(detail);
}

export async function fetchDocuments(): Promise<CorpusDocument[]> {
  const res = await fetch("/api/corpus/documents");
  if (!res.ok) throw new Error(`documents failed: ${res.status}`);
  return res.json();
}

/** Multipart upload — no Content-Type header; the browser sets the boundary. */
export async function uploadDocument(
  file: File,
  title?: string,
): Promise<CorpusDocument> {
  const form = new FormData();
  form.append("file", file);
  if (title) form.append("title", title);
  const res = await fetch("/api/corpus/documents/upload", {
    method: "POST",
    body: form,
  });
  if (!res.ok) await throwDetail(res, `upload failed: ${res.status}`);
  return res.json();
}

export async function pasteDocument(
  title: string,
  text: string,
): Promise<CorpusDocument> {
  const res = await fetch("/api/corpus/documents", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title, text }),
  });
  if (!res.ok) await throwDetail(res, `paste failed: ${res.status}`);
  return res.json();
}

export async function deleteDocument(id: number): Promise<void> {
  const res = await fetch(`/api/corpus/documents/${id}`, { method: "DELETE" });
  if (!res.ok) await throwDetail(res, `delete failed: ${res.status}`);
}

/** LLM call — can take tens of seconds; callers should show a busy state. */
export async function synthesizeProfile(): Promise<Profile> {
  const res = await fetch("/api/corpus/profile/synthesize", { method: "POST" });
  if (!res.ok) await throwDetail(res, `synthesize failed: ${res.status}`);
  return res.json();
}

export async function getProfile(): Promise<Profile | null> {
  const res = await fetch("/api/corpus/profile");
  if (!res.ok) throw new Error(`profile failed: ${res.status}`);
  return res.json(); // server returns JSON null when no profile exists
}
```

- [ ] **Step 2: Refactor `exportArtifact` to use `throwDetail` (DRY)**

In the existing `exportArtifact` (~line 145), replace the inline detail-parsing block:

```ts
  if (!res.ok) {
    let detail = `export failed: ${res.status}`;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* keep status fallback */
    }
    throw new Error(detail);
  }
```

with:

```ts
  if (!res.ok) await throwDetail(res, `export failed: ${res.status}`);
```

(`throwDetail` must be declared above `exportArtifact` or hoisted — function declarations hoist, so appending is fine; keep the declaration as a `function`, not a `const` arrow.)

- [ ] **Step 3: Verify the build**

Run: `NODE_ENV=production npm --prefix frontend run build`
Expected: exit 0, "Compiled successfully".

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat(frontend): corpus/profile API client functions"
```

---

### Task 2: `ProfileTab` component

**Files:**
- Create: `frontend/app/components/ProfileTab.tsx`

- [ ] **Step 1: Create the component file**

Full content of `frontend/app/components/ProfileTab.tsx`:

```tsx
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  CorpusDocument,
  Profile,
  deleteDocument,
  fetchDocuments,
  getProfile,
  pasteDocument,
  synthesizeProfile,
  uploadDocument,
} from "@/lib/api";

/** Self-contained Profile tab: corpus doc management + synthesized profile. */
export default function ProfileTab() {
  const [docs, setDocs] = useState<CorpusDocument[]>([]);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [synthesizing, setSynthesizing] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [d, p] = await Promise.all([fetchDocuments(), getProfile()]);
      setDocs(d);
      setProfile(p);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  /** Run a doc mutation: busy flag, error strip, refresh. True on success. */
  const mutate = useCallback(
    async (fn: () => Promise<unknown>) => {
      setBusy(true);
      try {
        await fn();
        setError(null);
        await refresh();
        return true;
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
        return false;
      } finally {
        setBusy(false);
      }
    },
    [refresh],
  );

  const synthesize = useCallback(async () => {
    setSynthesizing(true);
    try {
      setProfile(await synthesizeProfile());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSynthesizing(false);
    }
  }, []);

  return (
    <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
      {error && (
        <div className="flex items-start justify-between gap-2 rounded bg-amber-100 px-3 py-2 text-sm text-amber-800">
          <span className="whitespace-pre-wrap">{error}</span>
          <button aria-label="dismiss" className="font-bold" onClick={() => setError(null)}>
            ×
          </button>
        </div>
      )}

      <section>
        <h3 className="text-sm font-medium text-slate-600">
          Corpus documents ({docs.length})
        </h3>
        <div className="mt-2 space-y-2">
          {loaded && docs.length === 0 && (
            <p className="text-sm text-slate-400">
              No documents yet — upload your resume to get started.
            </p>
          )}
          {docs.map((d) => (
            <DocumentRow
              key={d.id}
              doc={d}
              disabled={busy}
              onDelete={() => mutate(() => deleteDocument(d.id))}
            />
          ))}
        </div>
        <AddDocuments
          busy={busy}
          onUpload={(f) => mutate(() => uploadDocument(f))}
          onPaste={(title, text) => mutate(() => pasteDocument(title, text))}
        />
      </section>

      <hr />

      <section>
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-medium text-slate-600">Synthesized profile</h3>
          <button
            className="rounded bg-slate-900 px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
            onClick={synthesize}
            disabled={synthesizing || busy}
          >
            {synthesizing ? "Synthesizing…" : profile ? "↻ Re-synthesize" : "Synthesize"}
          </button>
        </div>
        <div className="mt-2">
          {profile ? (
            <ProfileCard profile={profile} />
          ) : (
            loaded && (
              <p className="text-sm text-slate-400">
                No profile yet — add documents, then synthesize.
              </p>
            )
          )}
        </div>
      </section>
    </div>
  );
}

function DocumentRow({
  doc,
  disabled,
  onDelete,
}: {
  doc: CorpusDocument;
  disabled: boolean;
  onDelete: () => void;
}) {
  return (
    <div className="flex items-center justify-between gap-2 rounded border bg-slate-50 px-3 py-2">
      <div className="min-w-0">
        <span className="text-sm font-medium">{doc.title}</span>
        <span className="ml-2 text-xs text-slate-400">
          {doc.source_kind} · {doc.media_type} · {doc.char_count.toLocaleString()} chars
        </span>
      </div>
      <button
        className="text-xs text-slate-400 hover:text-red-600 disabled:opacity-40"
        disabled={disabled}
        onClick={() => window.confirm(`Delete "${doc.title}"?`) && onDelete()}
      >
        delete
      </button>
    </div>
  );
}

function AddDocuments({
  busy,
  onUpload,
  onPaste,
}: {
  busy: boolean;
  onUpload: (f: File) => void;
  onPaste: (title: string, text: string) => Promise<boolean>;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [pasteOpen, setPasteOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");

  const add = async () => {
    // only clear/collapse on success — a failed paste keeps the text
    if (await onPaste(title.trim(), text)) {
      setTitle("");
      setText("");
      setPasteOpen(false);
    }
  };

  return (
    <div className="mt-3 space-y-2">
      <div className="flex gap-2">
        <input
          ref={fileRef}
          type="file"
          accept=".pdf,.docx,.txt,.md"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) onUpload(f);
            e.target.value = ""; // allow re-selecting the same file
          }}
        />
        <button
          className="rounded bg-slate-200 px-2 py-1 text-xs font-medium text-slate-800 hover:bg-slate-300 disabled:opacity-40"
          disabled={busy}
          onClick={() => fileRef.current?.click()}
        >
          ⬆ Upload file
        </button>
        <button
          className="rounded bg-slate-200 px-2 py-1 text-xs font-medium text-slate-800 hover:bg-slate-300 disabled:opacity-40"
          disabled={busy}
          onClick={() => setPasteOpen((o) => !o)}
        >
          📋 Paste text
        </button>
      </div>
      {pasteOpen && (
        <div className="space-y-2 rounded border p-3">
          <input
            className="w-full rounded border px-2 py-1 text-sm"
            placeholder="Title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <textarea
            className="h-28 w-full rounded border px-2 py-1 text-sm"
            placeholder="Paste your document text…"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <button
            className="rounded bg-slate-900 px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
            disabled={busy || !title.trim() || !text.trim()}
            onClick={add}
          >
            Add
          </button>
        </div>
      )}
    </div>
  );
}

function ProfileCard({ profile }: { profile: Profile }) {
  return (
    <article className="rounded border bg-slate-50 p-3">
      {profile.headline && <h4 className="text-sm font-semibold">{profile.headline}</h4>}
      {profile.summary && (
        <p className="mt-1 whitespace-pre-wrap text-sm text-slate-700">{profile.summary}</p>
      )}
      {profile.skills.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {profile.skills.map((s) => (
            <span
              key={s}
              className="rounded-full bg-slate-200 px-2 py-0.5 text-xs text-slate-700"
            >
              {s}
            </span>
          ))}
        </div>
      )}
      {profile.experience.length > 0 && (
        <div className="mt-3">
          <h5 className="text-xs font-semibold uppercase text-slate-500">Experience</h5>
          {profile.experience.map((e, i) => (
            <ExperienceEntry key={i} entry={e} />
          ))}
        </div>
      )}
      <ListSection label="Achievements" items={profile.achievements} />
      <ListSection label="Target titles" items={profile.target_titles} />
      <ListSection label="Locations" items={profile.locations} />
      <p className="mt-3 text-[11px] text-slate-400">
        From {profile.source_doc_count} document{profile.source_doc_count === 1 ? "" : "s"} ·
        synthesized {new Date(profile.synthesized_at).toLocaleString()}
      </p>
    </article>
  );
}

// Experience entries are model-produced dicts; render known keys nicely and
// fall back to compact key: value lines for anything unexpected.
const KNOWN_KEYS = [
  "title",
  "role",
  "organization",
  "company",
  "period",
  "dates",
  "summary",
  "description",
];

function ExperienceEntry({ entry }: { entry: Record<string, unknown> }) {
  const get = (...keys: string[]) => {
    for (const k of keys) {
      const v = entry[k];
      if (typeof v === "string" && v) return v;
    }
    return null;
  };
  const role = get("title", "role");
  const org = get("organization", "company");
  const period = get("period", "dates");
  const summary = get("summary", "description");
  const rest = Object.entries(entry).filter(
    ([k, v]) => !KNOWN_KEYS.includes(k) && v != null && v !== "",
  );
  return (
    <div className="mt-1 text-sm text-slate-700">
      <span className="font-medium">
        {[role, org].filter(Boolean).join(" — ") || "Entry"}
      </span>
      {period && <span className="ml-1 text-xs text-slate-400">({period})</span>}
      {summary && <p className="text-xs text-slate-500">{summary}</p>}
      {rest.map(([k, v]) => (
        <p key={k} className="text-xs text-slate-400">
          {k}: {typeof v === "string" ? v : JSON.stringify(v)}
        </p>
      ))}
    </div>
  );
}

function ListSection({ label, items }: { label: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div className="mt-3">
      <h5 className="text-xs font-semibold uppercase text-slate-500">{label}</h5>
      <ul className="mt-1 list-inside list-disc text-sm text-slate-700">
        {items.map((it) => (
          <li key={it}>{it}</li>
        ))}
      </ul>
    </div>
  );
}
```

- [ ] **Step 2: Verify the build**

Run: `NODE_ENV=production npm --prefix frontend run build`
Expected: exit 0. (The component isn't referenced yet — this step only proves it type-checks and compiles.)

- [ ] **Step 3: Commit**

```bash
git add frontend/app/components/ProfileTab.tsx
git commit -m "feat(frontend): ProfileTab component (corpus docs + profile view)"
```

---

### Task 3: Canvas-pane tabs in `page.tsx`

**Files:**
- Modify: `frontend/app/page.tsx` (imports ~line 3; state ~line 43; Canvas section, lines 234–282)

- [ ] **Step 1: Add the import and tab state**

Below the existing `@/lib/api` import block, add:

```tsx
import ProfileTab from "./components/ProfileTab";
```

In `Home`, after `const [settings, setSettings] = ...` (~line 43), add:

```tsx
const [canvasTab, setCanvasTab] = useState<"workspace" | "profile">("workspace");
```

- [ ] **Step 2: Replace the Canvas section**

Replace the entire `{/* Canvas pane */}` `<section>` (lines 235–282) with:

```tsx
        {/* Canvas pane */}
        <section className="flex min-h-0 flex-1 flex-col bg-white">
          <div className="flex gap-4 border-b px-4 text-sm font-medium">
            <button
              className={`border-b-2 py-2 ${
                canvasTab === "workspace"
                  ? "border-slate-900 text-slate-900"
                  : "border-transparent text-slate-400 hover:text-slate-600"
              }`}
              onClick={() => setCanvasTab("workspace")}
            >
              Workspace — Artifacts ({artifacts.length}) · Notes ({notes.length})
            </button>
            <button
              className={`border-b-2 py-2 ${
                canvasTab === "profile"
                  ? "border-slate-900 text-slate-900"
                  : "border-transparent text-slate-400 hover:text-slate-600"
              }`}
              onClick={() => setCanvasTab("profile")}
            >
              Profile
            </button>
          </div>
          {canvasTab === "profile" ? (
            <ProfileTab />
          ) : (
            <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
              {artifacts.length === 0 && notes.length === 0 && (
                <p className="text-sm text-slate-400">
                  Artifacts and notes the agent saves will appear here.
                </p>
              )}
              {artifacts.map((a) => (
                <article key={`a-${a.id}`} className="rounded border bg-slate-50 p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="text-sm font-semibold">{a.title}</h3>
                    <span className="rounded bg-slate-200 px-1.5 py-0.5 text-[10px] font-medium text-slate-600">
                      {a.kind} v{a.version}
                    </span>
                    <span
                      className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${BADGE[a.review_status]}`}
                    >
                      {a.review_status.replace("_", " ")}
                    </span>
                    {(["docx", "pdf"] as const).map((fmt) => (
                      <button
                        key={fmt}
                        className="rounded border px-1.5 py-0.5 text-[10px] font-medium text-slate-600 hover:bg-slate-200"
                        onClick={() => doExport(a.id, fmt)}
                      >
                        {fmt}
                      </button>
                    ))}
                  </div>
                  {a.provenance && (
                    <p className="mt-0.5 text-[11px] text-slate-400">{a.provenance}</p>
                  )}
                  <p className="mt-1 max-h-40 overflow-hidden whitespace-pre-wrap text-sm text-slate-700">
                    {a.body}
                  </p>
                </article>
              ))}
              {notes.map((n) => (
                <article key={`n-${n.id}`} className="rounded border bg-slate-50 p-3">
                  <h3 className="text-sm font-semibold">{n.title}</h3>
                  <p className="mt-1 whitespace-pre-wrap text-sm text-slate-700">{n.body}</p>
                </article>
              ))}
            </div>
          )}
        </section>
```

The artifact/note markup inside the workspace branch is **identical to today's** — only the header (now a tab bar) and the conditional wrapper are new.

- [ ] **Step 3: Verify the build**

Run: `NODE_ENV=production npm --prefix frontend run build`
Expected: exit 0.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/page.tsx
git commit -m "feat(frontend): Workspace/Profile tabs in the canvas pane"
```

---

### Task 4: OpenAI key field in `SettingsBadge`

**Files:**
- Modify: `frontend/app/page.tsx` (the `SettingsBadge` function, ~line 314)

- [ ] **Step 1: Add state, save wiring, and the field**

In `SettingsBadge`, after `const [key, setKey] = useState("");` add:

```tsx
const [openaiKey, setOpenaiKey] = useState("");
```

In `save`, after the `if (key.trim())` line, add (and clear it alongside `setKey("")`):

```tsx
if (openaiKey.trim()) body.openai_api_key = openaiKey.trim();
```
```tsx
setOpenaiKey("");
```

Between the Anthropic key input and the "Agent model" label, add:

```tsx
<label className="block text-xs font-medium text-slate-600">
  OpenAI API key (embeddings)
</label>
<input
  type="password"
  className="w-full rounded border px-2 py-1 text-sm"
  placeholder={settings?.openai_key_configured ? "••••• (set)" : "sk-…"}
  value={openaiKey}
  onChange={(e) => setOpenaiKey(e.target.value)}
/>
```

- [ ] **Step 2: Verify the build**

Run: `NODE_ENV=production npm --prefix frontend run build`
Expected: exit 0.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/page.tsx
git commit -m "feat(frontend): OpenAI key field in settings badge"
```

---

### Task 5: Full verification (backend untouched + live seam)

**Files:** none (verification only)

- [ ] **Step 1: Backend suite still green**

Run: `uv run pytest -q`
Expected: all tests pass (137 at last count), no failures — this plan must not have touched Python.

- [ ] **Step 2: Confirm no backend diffs**

Run: `git diff main --stat -- app/ tests/`
Expected: empty output.

- [ ] **Step 3: Live seam check (requires a running server + OpenAI key)**

With the server running (`uv run uvicorn app.main:app --port 8000`) and `OH_OPENAI_API_KEY` set in its environment:

```bash
curl -s http://localhost:8000/ | grep -c "Opportunity Hunter"        # expect 1
curl -s -X POST http://localhost:8000/api/corpus/documents \
  -H 'Content-Type: application/json' \
  -d '{"title":"seam-check","text":"Test document for the corpus UI seam."}' # expect JSON with "id"
curl -s http://localhost:8000/api/corpus/documents | grep -c seam-check     # expect 1
curl -s -X DELETE http://localhost:8000/api/corpus/documents/<id-from-above> # expect {"deleted": ...}
```

UI-level checks (paste form, upload, synthesize spinner, profile card, error
strip with the key unset) are confirmed by the user in the browser — note this
in the final report rather than claiming them verified.

- [ ] **Step 4: Commit any plan-checkbox updates; hand off for merge**

Implementation complete → use superpowers:finishing-a-development-branch.
