"use client";

import { useCallback, useEffect, useState } from "react";
import {
  OpportunityDetail,
  completeAction,
  createContact,
  fetchOpportunityDetail,
  updateStage,
} from "@/lib/api";
import FetchError from "@/app/components/FetchError";

const STAGES = ["new", "qualifying", "analyzing", "active", "in_dialogue", "won", "lost"];

function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`rounded-xl border border-line bg-surface p-5 ${className}`}>
      {children}
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-2 text-[12.5px] font-bold uppercase tracking-wide text-ink-subtle">
      {children}
    </div>
  );
}

function Empty({ label }: { label: string }) {
  return <p className="text-[13px] text-ink-muted">No {label}.</p>;
}

export default function OpportunityDetailTab({
  opportunityId,
  onBack,
}: {
  opportunityId: string;
  onBack?: () => void;
}) {
  const [detail, setDetail] = useState<OpportunityDetail | null>(null);
  const [error, setError] = useState(false);

  const load = useCallback(() => {
    if (!opportunityId) {
      setDetail(null);
      return;
    }
    fetchOpportunityDetail(opportunityId)
      .then((d) => { setError(false); setDetail(d); })
      .catch(() => { setError(true); setDetail(null); });
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
      <p className="p-4 text-sm text-ink-muted">
        Select an opportunity above to see its detail.
      </p>
    );
  }
  if (error) return <FetchError onRetry={load} />;
  if (!detail) {
    return <p className="p-4 text-sm text-ink-muted">Loading…</p>;
  }

  const o = detail.opportunity;

  // Advance stage helper: next stage in STAGES array
  const currentStageIdx = STAGES.indexOf(o.stage);
  const nextStage = currentStageIdx >= 0 && currentStageIdx < STAGES.length - 1
    ? STAGES[currentStageIdx + 1]
    : null;

  return (
    <div className="min-h-0 flex-1 overflow-y-auto p-5 text-sm">
      {/* Back button */}
      {onBack && (
        <button
          onClick={onBack}
          className="mb-4 flex items-center gap-1 text-[13px] text-ink-muted transition hover:text-ink"
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M9 2L4 7l5 5" />
          </svg>
          Back to board
        </button>
      )}

      {/* Logo + Title Header */}
      <div className="mb-2 flex items-start gap-4">
        <div className="flex h-12 w-12 flex-none items-center justify-center rounded-lg bg-accent-tint text-[15px] font-bold text-accent">
          {(o.organization || o.title).slice(0, 2).toUpperCase()}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2.5">
            <h1 className="m-0 text-[23px] font-bold tracking-tight text-ink">{o.title}</h1>
            {o.fit_score != null && (
              <span className="rounded-md bg-accent-tint px-2 py-0.5 text-[11.5px] font-semibold text-accent">
                Fit {o.fit_score}
              </span>
            )}
            {o.url && (
              <a
                href={o.url}
                target="_blank"
                rel="noreferrer"
                className="rounded-md border border-line px-2 py-0.5 text-[11.5px] text-ink-muted transition hover:text-ink"
              >
                link ↗
              </a>
            )}
          </div>
          <div className="mt-1 text-[14px] text-ink-muted">
            {[o.organization, o.location, detail.company?.industry].filter(Boolean).join(" · ")}
          </div>
        </div>
      </div>

      {/* Stage Stepper */}
      <div className="my-5 flex flex-wrap gap-1.5">
        {STAGES.map((st) => (
          <button
            key={st}
            onClick={() => updateStage(o.id, st, "moved from detail").then(load)}
            className={`rounded-md px-3 py-1.5 text-[12.5px] font-semibold capitalize transition ${
              o.stage === st
                ? "bg-accent text-white"
                : "border border-line bg-surface text-ink-muted hover:bg-accent-tint hover:text-accent"
            }`}
          >
            {st.replace("_", " ")}
          </button>
        ))}
      </div>

      {/* Two-column body */}
      <div className="flex flex-wrap items-start gap-5">
        {/* Left column */}
        <div className="flex min-w-[340px] flex-1 flex-col gap-4">

          {/* Role overview */}
          {o.summary && (
            <Card>
              <SectionLabel>Role overview</SectionLabel>
              <p className="text-ink-body">{o.summary}</p>
            </Card>
          )}

          {/* Company */}
          {(detail.company || detail.source) && (
            <Card>
              <SectionLabel>Company &amp; source</SectionLabel>
              {detail.company && (
                <div className="mb-2 flex flex-col gap-0.5">
                  <div className="font-semibold text-ink">{detail.company.name}</div>
                  <div className="text-[13px] text-ink-muted">
                    {[
                      detail.company.industry,
                      detail.company.size && detail.company.size !== "unknown" ? detail.company.size : null,
                      detail.company.hq_location,
                      detail.company.ats_vendor ? `ATS: ${detail.company.ats_vendor}` : null,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </div>
                  {detail.company.careers_url && (
                    <a
                      href={detail.company.careers_url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-[12.5px] text-accent underline"
                    >
                      Careers page ↗
                    </a>
                  )}
                  {detail.company.linkedin_url && (
                    <a
                      href={detail.company.linkedin_url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-[12.5px] text-accent underline"
                    >
                      LinkedIn ↗
                    </a>
                  )}
                  {detail.company.summary && (
                    <p className="mt-1 text-[13px] text-ink-body">{detail.company.summary}</p>
                  )}
                </div>
              )}
              {detail.source && (
                <div className="mt-1 border-t border-line pt-2 text-[13px] text-ink-muted">
                  Source: <span className="font-medium text-ink">{detail.source.name}</span>
                  {detail.source.kind && ` · ${detail.source.kind}`}
                  {detail.source.url && (
                    <>
                      {" · "}
                      <a
                        href={detail.source.url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-accent underline"
                      >
                        link ↗
                      </a>
                    </>
                  )}
                </div>
              )}
            </Card>
          )}

          {/* Briefing */}
          {detail.briefing && (
            <Card>
              <SectionLabel>Briefing</SectionLabel>
              {detail.briefing.summary && (
                <p className="mb-3 text-ink-body">{detail.briefing.summary}</p>
              )}
              {detail.briefing.facts.length > 0 && (
                <div className="flex flex-col gap-2">
                  {detail.briefing.facts.map((f, i) => (
                    <div key={i} className="rounded-lg border border-line bg-white p-3">
                      <div className="font-semibold text-ink">{f.question}</div>
                      <div className="mt-0.5 text-ink-body">{f.answer}</div>
                      <div className="mt-1 font-mono text-[10.5px] text-ink-subtle">
                        {f.confidence != null && `confidence ${f.confidence.toFixed(2)}`}
                        {f.source && ` · source: ${f.source}`}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          )}

          {/* Communications */}
          <Card>
            <SectionLabel>Communications ({detail.communications.length})</SectionLabel>
            {detail.communications.length === 0 ? (
              <Empty label="communications" />
            ) : (
              <div className="flex flex-col gap-2">
                {detail.communications.map((c) => (
                  <div key={c.id} className="rounded-lg border border-line bg-white p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="rounded bg-surface-alt px-1.5 py-0.5 text-[11.5px] font-medium uppercase text-ink-subtle">
                        {c.direction}
                      </span>
                      <span className="rounded bg-surface-alt px-1.5 py-0.5 text-[11.5px] font-medium uppercase text-ink-subtle">
                        {c.channel}
                      </span>
                      <span className="font-medium text-ink">{c.subject || "(no subject)"}</span>
                    </div>
                    <div className="mt-1 font-mono text-[10.5px] text-ink-subtle">
                      {new Date(c.occurred_at).toLocaleDateString()}
                      {c.follow_up_due_at && (
                        <span
                          className={
                            new Date(c.follow_up_due_at) < new Date()
                              ? "text-error"
                              : "text-ink-subtle"
                          }
                        >
                          {" · follow-up "}
                          {new Date(c.follow_up_due_at).toLocaleDateString()}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>

          {/* Contacts */}
          <Card>
            <SectionLabel>Contacts ({detail.contacts.length})</SectionLabel>
            {detail.contacts.length === 0 ? (
              <Empty label="contacts" />
            ) : (
              <div className="mb-3 flex flex-col gap-2">
                {detail.contacts.map((c) => (
                  <div key={c.id} className="rounded-lg border border-line bg-white p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-semibold text-ink">{c.name}</span>
                      {c.role && <span className="text-[13px] text-ink-muted">{c.role}</span>}
                      {c.link && (
                        <a
                          href={c.link}
                          target="_blank"
                          rel="noreferrer"
                          className="text-[12.5px] text-accent underline"
                        >
                          link ↗
                        </a>
                      )}
                    </div>
                    {c.notes && <p className="mt-0.5 text-[12.5px] text-ink-muted">{c.notes}</p>}
                  </div>
                ))}
              </div>
            )}
            {/* Add contact form */}
            <div className="flex flex-wrap items-center gap-1.5 border-t border-line pt-3">
              <input
                value={cName}
                onChange={(e) => setCName(e.target.value)}
                placeholder="name"
                className="rounded-md border border-line px-2 py-1 text-[12.5px] focus:border-accent focus:outline-none"
              />
              <input
                value={cRole}
                onChange={(e) => setCRole(e.target.value)}
                placeholder="role"
                className="rounded-md border border-line px-2 py-1 text-[12.5px] focus:border-accent focus:outline-none"
              />
              <input
                value={cLink}
                onChange={(e) => setCLink(e.target.value)}
                placeholder="link"
                className="rounded-md border border-line px-2 py-1 text-[12.5px] focus:border-accent focus:outline-none"
              />
              <button
                onClick={addContact}
                disabled={!cName.trim()}
                className="rounded-md bg-accent px-3 py-1 text-[12.5px] font-semibold text-white disabled:opacity-50"
              >
                Add
              </button>
            </div>
          </Card>

        </div>

        {/* Right column */}
        <div className="flex w-[360px] flex-none flex-col gap-4">

          {/* What automation handled */}
          {(detail.artifacts.length > 0 || detail.decisions.length > 0) && (
            <Card>
              <SectionLabel>What automation handled</SectionLabel>
              <div className="flex flex-col gap-1.5">
                {detail.artifacts.map((a) => (
                  <div key={`art-${a.id}`} className="flex items-start gap-2">
                    <span className="mt-0.5 rounded bg-accent-tint px-1.5 py-0.5 text-[10.5px] font-semibold text-accent">
                      ✓
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="text-[13px] font-medium text-ink">{a.title}</div>
                      <div className="font-mono text-[10.5px] text-ink-subtle">
                        {a.kind} v{a.version} · {a.review_status}
                        {a.provenance && ` · ${a.provenance}`}
                      </div>
                    </div>
                  </div>
                ))}
                {detail.decisions.map((d) => (
                  <div key={`dec-${d.id}`} className="flex items-start gap-2">
                    <span className="mt-0.5 rounded bg-accent-tint px-1.5 py-0.5 text-[10.5px] font-semibold text-accent">
                      ✓
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="text-[13px] font-medium text-ink">{d.summary}</div>
                      <div className="font-mono text-[10.5px] text-ink-subtle">
                        {d.kind} · {new Date(d.created_at).toLocaleDateString()}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          )}

          {/* Quick actions */}
          <Card>
            <SectionLabel>Quick actions</SectionLabel>
            <div className="flex flex-col gap-2">
              {nextStage && (
                <button
                  onClick={() => updateStage(o.id, nextStage, "advanced from detail").then(load)}
                  className="w-full rounded-md bg-accent px-3 py-2 text-[13px] font-semibold text-white transition hover:bg-accent-ink"
                >
                  Advance to &ldquo;{nextStage.replace("_", " ")}&rdquo;
                </button>
              )}
              {detail.actions
                .filter((a) => a.status === "open")
                .map((a) => (
                  <button
                    key={a.id}
                    onClick={() => completeAction(a.id).then(load)}
                    className="w-full rounded-md border border-line bg-surface px-3 py-2 text-left text-[13px] text-ink transition hover:bg-accent-tint hover:text-accent"
                  >
                    ✓ {a.title}
                  </button>
                ))}
            </div>
          </Card>

          {/* Applications */}
          <Card>
            <SectionLabel>Applications ({detail.applications.length})</SectionLabel>
            {detail.applications.length === 0 ? (
              <Empty label="applications" />
            ) : (
              <div className="flex flex-col gap-2">
                {detail.applications.map((a) => (
                  <div key={a.id} className="flex flex-wrap items-center gap-2 rounded-lg border border-line bg-white p-2.5">
                    <span className="rounded bg-surface-alt px-1.5 py-0.5 text-[11.5px] font-medium uppercase text-ink-subtle">
                      {a.status}
                    </span>
                    {a.portal_url && (
                      <a
                        href={a.portal_url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-[12.5px] text-accent underline"
                      >
                        portal ↗
                      </a>
                    )}
                    {a.submitted_at && (
                      <span className="font-mono text-[10.5px] text-ink-subtle">
                        {new Date(a.submitted_at).toLocaleDateString()}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </Card>

          {/* Actions */}
          <Card>
            <SectionLabel>Actions ({detail.actions.length})</SectionLabel>
            {detail.actions.length === 0 ? (
              <Empty label="actions" />
            ) : (
              <div className="flex flex-col gap-2">
                {detail.actions.map((a) => (
                  <div
                    key={a.id}
                    className="flex items-center gap-2 rounded-lg border border-line bg-white p-2.5"
                  >
                    <span className="rounded bg-surface-alt px-1.5 py-0.5 text-[11.5px] font-medium uppercase text-ink-subtle">
                      {a.status}
                    </span>
                    <span className="flex-1 text-ink">{a.title}</span>
                    <span className="font-mono text-[10.5px] text-ink-subtle">{a.kind}</span>
                    {a.due_at && (
                      <span className="font-mono text-[10.5px] text-ink-subtle">
                        due {new Date(a.due_at).toLocaleDateString()}
                      </span>
                    )}
                    {a.status === "open" && (
                      <button
                        onClick={() => completeAction(a.id).then(load)}
                        className="rounded-md bg-surface-alt px-2 py-0.5 text-[11.5px] font-medium text-ink transition hover:bg-accent-tint hover:text-accent"
                      >
                        Done
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </Card>

          {/* Artifacts (full list) */}
          <Card>
            <SectionLabel>Artifacts ({detail.artifacts.length})</SectionLabel>
            {detail.artifacts.length === 0 ? (
              <Empty label="artifacts" />
            ) : (
              <div className="flex flex-col gap-2">
                {detail.artifacts.map((a) => (
                  <div key={a.id} className="flex items-center gap-2 rounded-lg border border-line bg-white p-2.5">
                    <span className="rounded bg-surface-alt px-1.5 py-0.5 text-[11.5px] font-medium uppercase text-ink-subtle">
                      {a.review_status}
                    </span>
                    <span className="flex-1 text-ink">{a.title}</span>
                    <span className="font-mono text-[10.5px] text-ink-subtle">
                      {a.kind} v{a.version}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </Card>

          {/* Decisions */}
          <Card>
            <SectionLabel>Decisions ({detail.decisions.length})</SectionLabel>
            {detail.decisions.length === 0 ? (
              <Empty label="decisions" />
            ) : (
              <div className="flex flex-col gap-2">
                {detail.decisions.map((d) => (
                  <div key={d.id} className="rounded-lg border border-line bg-white p-2.5">
                    <div className="flex items-center gap-2">
                      <span className="rounded bg-surface-alt px-1.5 py-0.5 text-[11.5px] font-medium uppercase text-ink-subtle">
                        {d.kind}
                      </span>
                      <span className="text-ink">{d.summary}</span>
                    </div>
                    {d.rationale && (
                      <p className="mt-1 text-[12.5px] text-ink-muted">{d.rationale}</p>
                    )}
                    <div className="mt-1 font-mono text-[10.5px] text-ink-subtle">
                      {new Date(d.created_at).toLocaleDateString()}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>

        </div>
      </div>
    </div>
  );
}
