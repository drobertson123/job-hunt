"use client";

import { useCallback, useEffect, useState } from "react";
import { Contact, createContact, fetchContacts, importGoogleContacts } from "@/lib/api";
import FetchError from "./FetchError";

export default function ContactsTab({ onOpen }: { onOpen: (oppId: string) => void }) {
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [error, setError] = useState(false);
  const [name, setName] = useState("");
  const [org, setOrg] = useState("");
  const [role, setRole] = useState("");
  const [email, setEmail] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    fetchContacts()
      .then((c) => { setContacts(c); setError(false); })
      .catch(() => { setContacts([]); setError(true); });
  }, []);
  useEffect(() => { load(); }, [load]);

  const add = async () => {
    if (!name.trim()) return;
    await createContact({ name: name.trim(), organization: org.trim() || null, role: role.trim() || null, email: email.trim() || null });
    setName(""); setOrg(""); setRole(""); setEmail("");
    load();
  };

  const importGoogle = async () => {
    setBusy(true);
    try {
      const r = await importGoogleContacts();
      setMsg(`${r.imported} imported`);
      load();
    } catch {
      setMsg("Connect Google in Settings first");
    } finally {
      setBusy(false);
    }
  };

  if (error) return <FetchError onRetry={load} />;

  // group by organization
  const groups = new Map<string, Contact[]>();
  for (const c of contacts) {
    const k = c.organization?.trim() || "Unaffiliated";
    (groups.get(k) ?? groups.set(k, []).get(k)!).push(c);
  }
  const sorted = [...groups.entries()].sort((a, b) => a[0].localeCompare(b[0]));

  return (
    <div className="min-h-0 flex-1 overflow-y-auto p-5">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <h1 className="text-[22px] font-bold tracking-tight text-ink">Contacts</h1>
          <p className="text-[13.5px] text-ink-muted">{contacts.length} people across {sorted.length} companies</p>
        </div>
        <div className="flex items-center gap-2">
          {msg && <span className="text-[12px] text-ok-deep">{msg}</span>}
          <button onClick={importGoogle} disabled={busy} className="rounded-md border border-line bg-surface px-3.5 py-2 text-[13px] font-semibold text-ink transition hover:bg-surface-sunk disabled:opacity-50">
            {busy ? "Importing…" : "Import Google contacts"}
          </button>
        </div>
      </div>

      {/* add row */}
      <div className="mb-5 flex flex-wrap items-center gap-2 rounded-xl border border-line bg-surface p-3">
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name" className="flex-1 rounded-md border border-line px-3 py-2 text-[13px] focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent" />
        <input value={role} onChange={(e) => setRole(e.target.value)} placeholder="Role" className="w-36 rounded-md border border-line px-3 py-2 text-[13px]" />
        <input value={org} onChange={(e) => setOrg(e.target.value)} placeholder="Company" className="w-44 rounded-md border border-line px-3 py-2 text-[13px]" />
        <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Email" className="w-52 rounded-md border border-line px-3 py-2 text-[13px]" />
        <button onClick={add} disabled={!name.trim()} className="rounded-md bg-accent px-3.5 py-2 text-[13px] font-semibold text-white hover:bg-accent-ink disabled:opacity-50">Add</button>
      </div>

      {sorted.length === 0 ? (
        <p className="text-[13px] text-ink-subtle">No contacts yet — import from Google or add one above.</p>
      ) : (
        <div className="grid gap-3.5 [grid-template-columns:repeat(auto-fill,minmax(320px,1fr))]">
          {sorted.map(([orgName, people]) => (
            <div key={orgName} className="rounded-xl border border-line bg-surface p-4">
              <div className="mb-2.5 flex items-center gap-2">
                <span className="flex h-8 w-8 flex-none items-center justify-center rounded-md bg-accent-tint text-[11px] font-bold text-accent">{orgName.slice(0, 2).toUpperCase()}</span>
                <span className="truncate text-[14px] font-semibold text-ink">{orgName}</span>
                <span className="ml-auto rounded-full bg-surface-sunk px-2 text-[11px] font-semibold text-ink-muted">{people.length}</span>
              </div>
              <div className="flex flex-col gap-2">
                {people.map((c) => (
                  <div key={c.id} className="rounded-lg border border-line-soft bg-surface-alt p-2.5">
                    <div className="text-[13px] font-semibold text-ink">{c.name}</div>
                    <div className="text-[12px] text-ink-muted">{[c.role, c.email].filter(Boolean).join(" · ") || "—"}</div>
                    {c.opportunity_id && (
                      <button onClick={() => onOpen(c.opportunity_id as string)} className="mt-1 text-[11.5px] text-accent hover:underline">View opportunity →</button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
