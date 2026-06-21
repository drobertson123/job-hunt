"use client";

import { useCallback, useEffect, useState } from "react";
import { OpportunityDetail, completeAction, createContact, fetchOpportunityDetail } from "@/lib/api";

function Badge({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded bg-slate-100 px-2 py-0.5 text-xs uppercase text-slate-600">
      {children}
    </span>
  );
}

function Section({ title, count, children }: {
  title: string;
  count: number;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
        {title} ({count})
      </h3>
      {count === 0 ? (
        <p className="text-sm text-slate-400">None.</p>
      ) : (
        <div className="flex flex-col gap-1">{children}</div>
      )}
    </div>
  );
}

export default function OpportunityDetailTab({ opportunityId }: { opportunityId: string }) {
  const [detail, setDetail] = useState<OpportunityDetail | null>(null);

  const load = useCallback(() => {
    if (!opportunityId) {
      setDetail(null);
      return;
    }
    fetchOpportunityDetail(opportunityId).then(setDetail).catch(() => setDetail(null));
  }, [opportunityId]);

  useEffect(() => {
    load();
  }, [load]);

  const [cName, setCName] = useState("");
  const [cRole, setCRole] = useState("");
  const [cLink, setCLink] = useState("");

  const addContact = async () => {
    if (!cName.trim()) return;
    await createContact({
      name: cName.trim(),
      role: cRole || null,
      link: cLink || null,
      opportunity_id: opportunityId,
    });
    setCName("");
    setCRole("");
    setCLink("");
    load();
  };

  if (!opportunityId) {
    return (
      <p className="p-4 text-sm text-slate-400">
        Select an opportunity above to see its detail.
      </p>
    );
  }
  if (!detail) {
    return <p className="p-4 text-sm text-slate-400">Loading…</p>;
  }

  const o = detail.opportunity;
  return (
    <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4 text-sm">
      {/* Header */}
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-2">
          <h2 className="text-base font-semibold">{o.title}</h2>
          <Badge>{o.stage}</Badge>
          {o.fit_score != null && <Badge>Fit {o.fit_score}</Badge>}
        </div>
        <div className="text-xs text-slate-500">
          {o.organization}
          {o.location && ` · ${o.location}`}
          {o.url && (
            <>
              {" · "}
              <a href={o.url} target="_blank" rel="noreferrer" className="text-blue-600 underline">
                link
              </a>
            </>
          )}
        </div>
        {o.summary && <p className="text-slate-700">{o.summary}</p>}
        {detail.company && (
          <div className="text-xs text-slate-500">
            <span className="font-medium">{detail.company.name}</span>
            {detail.company.industry && ` · ${detail.company.industry}`}
            {detail.company.size && detail.company.size !== "unknown" && ` · ${detail.company.size}`}
            {detail.company.ats_vendor && ` · ATS: ${detail.company.ats_vendor}`}
            {detail.company.careers_url && (
              <>
                {" · "}
                <a
                  href={detail.company.careers_url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-blue-600 underline"
                >
                  careers
                </a>
              </>
            )}
          </div>
        )}
      </div>

      <Section title="Briefing" count={detail.briefing ? 1 : 0}>
        {detail.briefing && (
          <div className="flex flex-col gap-1">
            {detail.briefing.summary && (
              <p className="text-slate-700">{detail.briefing.summary}</p>
            )}
            {detail.briefing.facts.map((f, i) => (
              <div key={i} className="rounded border border-slate-200 p-2">
                <div className="font-medium">{f.question}</div>
                <div>{f.answer}</div>
                <div className="text-xs text-slate-500">
                  {f.confidence != null && `confidence ${f.confidence.toFixed(2)}`}
                  {f.source && ` · source: ${f.source}`}
                </div>
              </div>
            ))}
          </div>
        )}
      </Section>

      <Section title="Applications" count={detail.applications.length}>
        {detail.applications.map((a) => (
          <div key={a.id} className="flex items-center gap-2 rounded border border-slate-200 p-2">
            <Badge>{a.status}</Badge>
            {a.portal_url && (
              <a href={a.portal_url} target="_blank" rel="noreferrer" className="text-xs text-blue-600 underline">
                portal
              </a>
            )}
            {a.submitted_at && (
              <span className="text-xs text-slate-500">
                {new Date(a.submitted_at).toLocaleDateString()}
              </span>
            )}
          </div>
        ))}
      </Section>

      <Section title="Contacts" count={detail.contacts.length}>
        {detail.contacts.map((c) => (
          <div key={c.id} className="rounded border border-slate-200 p-2">
            <div className="flex items-center gap-2">
              <span className="font-medium">{c.name}</span>
              {c.role && <span className="text-xs text-slate-500">{c.role}</span>}
              {c.link && (
                <a href={c.link} target="_blank" rel="noreferrer"
                   className="text-xs text-blue-600 underline">link</a>
              )}
            </div>
            {c.notes && <p className="text-xs text-slate-500">{c.notes}</p>}
          </div>
        ))}
      </Section>
      <div className="mt-1 flex flex-wrap items-center gap-1">
        <input value={cName} onChange={(e) => setCName(e.target.value)}
               placeholder="name" className="rounded border px-2 py-1 text-xs" />
        <input value={cRole} onChange={(e) => setCRole(e.target.value)}
               placeholder="role" className="rounded border px-2 py-1 text-xs" />
        <input value={cLink} onChange={(e) => setCLink(e.target.value)}
               placeholder="link" className="rounded border px-2 py-1 text-xs" />
        <button onClick={addContact} disabled={!cName.trim()}
                className="rounded bg-slate-900 px-2 py-1 text-xs text-white disabled:opacity-50">
          Add
        </button>
      </div>

      <Section title="Communications" count={detail.communications.length}>
        {detail.communications.map((c) => (
          <div key={c.id} className="rounded border border-slate-200 p-2">
            <div className="flex items-center gap-2">
              <Badge>{c.direction}</Badge>
              <Badge>{c.channel}</Badge>
              <span className="font-medium">{c.subject || "(no subject)"}</span>
            </div>
            <div className="text-xs text-slate-500">
              {new Date(c.occurred_at).toLocaleDateString()}
              {c.follow_up_due_at && (
                <span
                  className={
                    new Date(c.follow_up_due_at) < new Date()
                      ? "text-red-600"
                      : "text-slate-500"
                  }
                >
                  {" · follow-up "}
                  {new Date(c.follow_up_due_at).toLocaleDateString()}
                </span>
              )}
            </div>
          </div>
        ))}
      </Section>

      <Section title="Actions" count={detail.actions.length}>
        {detail.actions.map((a) => (
          <div key={a.id} className="flex items-center gap-2 rounded border border-slate-200 p-2">
            <Badge>{a.status}</Badge>
            <span>{a.title}</span>
            <span className="text-xs text-slate-400">{a.kind}</span>
            {a.due_at && (
              <span className="text-xs text-slate-500">
                due {new Date(a.due_at).toLocaleDateString()}
              </span>
            )}
            {a.status === "open" && (
              <button
                onClick={() => completeAction(a.id).then(load)}
                className="ml-auto rounded bg-slate-200 px-2 py-0.5 text-xs hover:bg-slate-300"
              >
                Done
              </button>
            )}
          </div>
        ))}
      </Section>

      <Section title="Artifacts" count={detail.artifacts.length}>
        {detail.artifacts.map((a) => (
          <div key={a.id} className="flex items-center gap-2 rounded border border-slate-200 p-2">
            <Badge>{a.review_status}</Badge>
            <span>{a.title}</span>
            <span className="text-xs text-slate-400">{a.kind} v{a.version}</span>
          </div>
        ))}
      </Section>

      <Section title="Decisions" count={detail.decisions.length}>
        {detail.decisions.map((d) => (
          <div key={d.id} className="rounded border border-slate-200 p-2">
            <Badge>{d.kind}</Badge> <span>{d.summary}</span>
          </div>
        ))}
      </Section>
    </div>
  );
}
