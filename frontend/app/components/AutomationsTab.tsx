"use client";

import { useCallback, useEffect, useState } from "react";
import { JobSource, Profile, fetchJobSources, fetchProfile, updatePreferences } from "@/lib/api";

type RuleKind = "dealbreakers" | "must_haves" | "nice_to_haves";

const RULES: { key: RuleKind; label: string; hint: string }[] = [
  { key: "dealbreakers", label: "Dealbreakers", hint: "any match → flag / skip" },
  { key: "must_haves", label: "Must-haves", hint: "required to rank High" },
  { key: "nice_to_haves", label: "Nice-to-haves", hint: "bonus signals" },
];

export default function AutomationsTab({ onNavigate }: { onNavigate?: (tab: string) => void }) {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [sources, setSources] = useState<JobSource[]>([]);
  const [drafts, setDrafts] = useState<Record<string, string>>({});

  const load = useCallback(() => {
    fetchProfile().then(setProfile).catch(() => setProfile(null));
    fetchJobSources().then(setSources).catch(() => setSources([]));
  }, []);
  useEffect(() => { load(); }, [load]);

  const autoSources = sources.filter((s) => s.auto_search);

  const addRule = async (key: RuleKind) => {
    const v = (drafts[key] || "").trim();
    if (!v || !profile) return;
    const next = [...(profile[key] || []), v];
    const updated = await updatePreferences({ [key]: next } as any);
    setProfile(updated);
    setDrafts((d) => ({ ...d, [key]: "" }));
  };
  const removeRule = async (key: RuleKind, val: string) => {
    if (!profile) return;
    const next = (profile[key] || []).filter((x) => x !== val);
    setProfile(await updatePreferences({ [key]: next } as any));
  };

  const Dot = ({ on }: { on: boolean }) => (
    <span className={`h-2 w-2 flex-none rounded-full ${on ? "bg-ok" : "bg-ink-subtle"}`} />
  );

  return (
    <div className="min-h-0 flex-1 overflow-y-auto p-5">
      <h1 className="text-[22px] font-bold tracking-tight text-ink">Automations</h1>
      <p className="mb-5 text-[13.5px] text-ink-muted">You stay in control — every rule is editable and every action can be overridden.</p>

      {/* Active automations */}
      <div className="mb-5 rounded-xl border border-line bg-surface px-5 py-1">
        {[
          { on: autoSources.length > 0, label: "Daily job discovery", sub: autoSources.length > 0 ? `${autoSources.length} source${autoSources.length === 1 ? "" : "s"} scanned daily` : "No sources opted in yet", cta: "Manage sources", to: "sources" },
          { on: true, label: "Follow-up capture", sub: "Inbound emails/texts logged with follow-up actions", cta: "View actions", to: "actions" },
          { on: true, label: "Grounded output", sub: "Generated documents are auto-checked against your corpus and gated for review", cta: "Open documents", to: "documents" },
        ].map((row) => (
          <div key={row.label} className="flex items-center gap-3 border-b border-line-soft py-4 last:border-0">
            <Dot on={row.on} />
            <div className="min-w-0 flex-1">
              <div className="text-[14px] font-semibold text-ink">{row.label}</div>
              <div className="text-[12.5px] text-ink-muted">{row.sub}</div>
            </div>
            {onNavigate && (
              <button onClick={() => onNavigate(row.to)} className="flex-none text-[12.5px] font-semibold text-accent hover:underline">{row.cta} →</button>
            )}
          </div>
        ))}
      </div>

      {/* Decision rules (preferences) */}
      <div className="mb-3 text-[13px] font-bold uppercase tracking-wide text-ink-subtle">Decision rules</div>
      <div className="flex flex-col gap-4">
        {RULES.map((r) => (
          <div key={r.key} className="rounded-xl border border-line bg-surface p-4">
            <div className="mb-2 flex items-baseline gap-2">
              <span className="text-[14px] font-semibold text-ink">{r.label}</span>
              <span className="text-[12px] text-ink-subtle">{r.hint}</span>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {(profile?.[r.key] || []).map((val) => (
                <span key={val} className="flex items-center gap-1 rounded-md bg-accent-tint px-2 py-1 text-[12px] font-medium text-accent">
                  {val}
                  <button onClick={() => removeRule(r.key, val)} className="text-accent/70 hover:text-accent">×</button>
                </span>
              ))}
              <input
                value={drafts[r.key] || ""}
                onChange={(e) => setDrafts((d) => ({ ...d, [r.key]: e.target.value }))}
                onKeyDown={(e) => e.key === "Enter" && addRule(r.key)}
                placeholder="Add…"
                className="w-32 rounded-md border border-line px-2.5 py-1 text-[12px] focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
              />
            </div>
          </div>
        ))}
      </div>
      <p className="mt-3 text-[12px] text-ink-subtle">These rules drive the Fit-analysis rating and pipeline triage.</p>
    </div>
  );
}
