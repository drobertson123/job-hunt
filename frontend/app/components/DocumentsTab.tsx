"use client";

import { useCallback, useEffect, useState } from "react";
import { Artifact, Communication, fetchArtifacts, fetchCommunications } from "@/lib/api";
import ArtifactCard from "./ArtifactCard";
import FetchError from "./FetchError";

const GROUPS: { key: string; label: string; kinds: string[] }[] = [
  { key: "all", label: "All", kinds: [] },
  { key: "resumes", label: "Résumés", kinds: ["cv"] },
  { key: "covers", label: "Cover letters", kinds: ["cover_letter"] },
  { key: "briefs", label: "Briefs", kinds: ["research_brief", "fit_analysis"] },
  { key: "outreach", label: "Outreach", kinds: ["outreach", "pitch", "proposal"] },
  { key: "comms", label: "Communications", kinds: [] },
];

export default function DocumentsTab() {
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [comms, setComms] = useState<Communication[]>([]);
  const [error, setError] = useState(false);
  const [group, setGroup] = useState("all");

  const load = useCallback(() => {
    fetchArtifacts()
      .then((a) => { setArtifacts(a); setError(false); })
      .catch(() => { setArtifacts([]); setError(true); });
    fetchCommunications().then(setComms).catch(() => setComms([]));
  }, []);
  useEffect(() => { load(); }, [load]);

  if (error) return <FetchError onRetry={load} />;

  const g = GROUPS.find((x) => x.key === group)!;
  const docs = g.kinds.length ? artifacts.filter((a) => g.kinds.includes(a.kind)) : artifacts;

  return (
    <div className="min-h-0 flex-1 overflow-y-auto p-5">
      <h1 className="text-[22px] font-bold tracking-tight text-ink">Documents</h1>
      <p className="mb-4 text-[13.5px] text-ink-muted">{artifacts.length} generated documents · {comms.length} communications</p>

      <div className="mb-4 flex flex-wrap gap-1.5">
        {GROUPS.map((x) => (
          <button
            key={x.key}
            onClick={() => setGroup(x.key)}
            className={`rounded-md px-3 py-1.5 text-[12.5px] font-semibold transition ${
              group === x.key ? "bg-accent text-white" : "border border-line bg-surface text-ink-muted hover:bg-accent-tint hover:text-accent"
            }`}
          >
            {x.label}
          </button>
        ))}
      </div>

      {group === "comms" ? (
        comms.length === 0 ? (
          <p className="text-[13px] text-ink-subtle">No communications logged.</p>
        ) : (
          <div className="flex flex-col gap-2.5">
            {comms.map((c) => (
              <div key={c.id} className="rounded-xl border border-line bg-surface p-4">
                <div className="flex items-center gap-2">
                  <span className="rounded-xs bg-accent-tint px-1.5 py-0.5 text-[10.5px] font-semibold uppercase text-accent">{c.channel}</span>
                  <span className="rounded-xs bg-surface-sunk px-1.5 py-0.5 text-[10.5px] text-ink-muted">{c.direction}</span>
                  <span className="ml-auto font-mono text-[10px] text-ink-subtle">{new Date(c.occurred_at).toLocaleDateString()}</span>
                </div>
                {c.subject && <div className="mt-1.5 text-[13.5px] font-semibold text-ink">{c.subject}</div>}
                {c.body && <p className="mt-1 line-clamp-3 text-[12.5px] leading-snug text-ink-body">{c.body}</p>}
              </div>
            ))}
          </div>
        )
      ) : docs.length === 0 ? (
        <p className="text-[13px] text-ink-subtle">No documents in this group yet — generate them from an opportunity (CV tailor, cover letter, …).</p>
      ) : (
        <div className="flex flex-col gap-3">
          {docs.map((a) => (
            <ArtifactCard key={a.id} artifact={a} onChanged={load} />
          ))}
        </div>
      )}
    </div>
  );
}
