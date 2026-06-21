"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Application,
  Opportunity,
  fetchApplications,
  fetchOpportunities,
} from "@/lib/api";
import FetchError from "./FetchError";

export default function ApplicationsTab() {
  const [apps, setApps] = useState<Application[]>([]);
  const [opps, setOpps] = useState<Opportunity[]>([]);
  const [error, setError] = useState(false);

  const load = useCallback(() => {
    Promise.all([fetchApplications(), fetchOpportunities()])
      .then(([a, o]) => {
        setApps(a);
        setOpps(o);
        setError(false);
      })
      .catch(() => {
        setApps([]);
        setOpps([]);
        setError(true);
      });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (error) return <FetchError onRetry={load} />;

  if (apps.length === 0) {
    return (
      <p className="p-4 text-sm text-gray-500">
        Applications the agent records will appear here.
      </p>
    );
  }

  const titleFor = (id: string) =>
    opps.find((o) => o.id === id)?.title ?? id;

  return (
    <div className="flex flex-col gap-2 p-2">
      {apps.map((a) => (
        <div key={a.id} className="rounded border border-gray-200 p-3 text-sm">
          <div className="flex items-center justify-between">
            <span className="font-medium">{titleFor(a.opportunity_id)}</span>
            <span className="rounded bg-gray-100 px-2 py-0.5 text-xs uppercase">
              {a.status}
            </span>
          </div>
          {a.submitted_at && (
            <div className="text-xs text-gray-500">
              submitted {new Date(a.submitted_at).toLocaleDateString()}
            </div>
          )}
          {a.portal_url && (
            <a
              href={a.portal_url}
              target="_blank"
              rel="noreferrer"
              className="text-xs text-blue-600 underline"
            >
              portal
            </a>
          )}
          {a.notes && <p className="mt-1 text-xs text-gray-600">{a.notes}</p>}
        </div>
      ))}
    </div>
  );
}
