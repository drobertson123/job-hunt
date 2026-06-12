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
