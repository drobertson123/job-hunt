"use client";

import { useCallback, useEffect, useState } from "react";
import { RelCluster, fetchRelationships } from "@/lib/api";
import FetchError from "./FetchError";

export default function RelationshipsTab({ onOpen }: { onOpen: (oppId: string) => void }) {
  const [clusters, setClusters] = useState<RelCluster[]>([]);
  const [warmIntroCount, setWarmIntroCount] = useState(0);
  const [error, setError] = useState(false);

  const load = useCallback(() => {
    fetchRelationships()
      .then((d) => {
        setClusters(d.clusters);
        setWarmIntroCount(d.warm_intro_count);
        setError(false);
      })
      .catch(() => {
        setClusters([]);
        setError(true);
      });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (error) return <FetchError onRetry={load} />;

  return (
    <div className="min-h-0 flex-1 overflow-y-auto p-5">
      <div className="mb-5">
        <h1 className="text-[22px] font-bold tracking-tight text-ink">Relationships</h1>
        <p className="text-[13.5px] text-ink-muted">
          <span className="font-semibold text-accent">{warmIntroCount} warm intros</span>
          {" "}— companies where you know someone AND track a role
        </p>
      </div>

      {clusters.length === 0 ? (
        <p className="text-[13px] text-ink-subtle">
          No network clusters yet — add contacts and opportunities linked to companies to see your network here.
        </p>
      ) : (
        <div className="grid gap-3.5 [grid-template-columns:repeat(auto-fill,minmax(340px,1fr))]">
          {clusters.map((cluster) => (
            <NetworkCard key={cluster.name} cluster={cluster} onOpen={onOpen} />
          ))}
        </div>
      )}
    </div>
  );
}

function NetworkCard({ cluster, onOpen }: { cluster: RelCluster; onOpen: (oppId: string) => void }) {
  const isWarm = cluster.warm;

  return (
    <div
      className={`rounded-xl border bg-surface p-4 ${
        isWarm ? "border-accent" : "border-line"
      }`}
    >
      {/* Warm badge */}
      {isWarm && (
        <div className="mb-3 flex items-center gap-1.5">
          <span className="rounded-full bg-accent-tint px-2.5 py-0.5 text-[11.5px] font-semibold text-accent">
            ⚡ warm intro
          </span>
        </div>
      )}

      {/* Hub: company chip */}
      <div className="mb-4 flex justify-center">
        <span className="rounded-md bg-panel px-4 py-2 text-[14px] font-semibold text-white">
          {cluster.name}
        </span>
      </div>

      {/* Spokes */}
      <div className="flex flex-col gap-3">
        {/* Contacts spoke */}
        {cluster.contacts.length > 0 && (
          <div>
            <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-ink-subtle">
              Contacts
            </div>
            <div className="flex flex-wrap gap-1.5">
              {cluster.contacts.map((ct) => (
                <span
                  key={ct.id}
                  className="rounded-md bg-accent-tint px-2.5 py-1 text-[12px] font-medium text-accent"
                >
                  {ct.name}
                  {ct.role ? <span className="ml-1 opacity-70">· {ct.role}</span> : null}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Roles spoke */}
        {cluster.opportunities.length > 0 && (
          <div>
            <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-ink-subtle">
              Roles
            </div>
            <div className="flex flex-wrap gap-1.5">
              {cluster.opportunities.map((opp) => (
                <button
                  key={opp.id}
                  onClick={() => onOpen(opp.id)}
                  className="flex items-center gap-1.5 rounded-md border border-line bg-surface-alt px-2.5 py-1 text-[12px] font-medium text-ink transition hover:border-accent hover:text-accent"
                >
                  {opp.title}
                  <span className="rounded-sm bg-surface-sunk px-1.5 py-0.5 text-[10px] font-semibold text-ink-muted capitalize">
                    {opp.stage}
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
