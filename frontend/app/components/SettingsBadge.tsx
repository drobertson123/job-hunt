"use client";

import { useState } from "react";
import { SettingsView, syncGmail, updateSettings } from "@/lib/api";

export default function SettingsBadge({
  settings,
  onSaved,
}: {
  settings: SettingsView | null;
  onSaved: (s: SettingsView) => void;
}) {
  const [open, setOpen] = useState(false);
  const [key, setKey] = useState("");
  const [openaiKey, setOpenaiKey] = useState("");
  const [model, setModel] = useState("");
  const [googleClientId, setGoogleClientId] = useState("");
  const [googleClientSecret, setGoogleClientSecret] = useState("");
  const [syncResult, setSyncResult] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);

  const configured = settings?.anthropic_key_configured;
  const google = settings?.google;

  const save = async () => {
    const body: Record<string, string> = {};
    if (key.trim()) body.anthropic_api_key = key.trim();
    if (openaiKey.trim()) body.openai_api_key = openaiKey.trim();
    if (model.trim()) body.agent_model = model.trim();
    if (googleClientId.trim()) body.google_client_id = googleClientId.trim();
    if (googleClientSecret.trim()) body.google_client_secret = googleClientSecret.trim();
    const updated = await updateSettings(body);
    onSaved(updated);
    setKey("");
    setOpenaiKey("");
    setGoogleClientId("");
    setGoogleClientSecret("");
    setOpen(false);
  };

  const doSync = async () => {
    setSyncing(true);
    setSyncResult(null);
    try {
      const r = await syncGmail();
      setSyncResult(`fetched ${r.fetched}, created ${r.created}, skipped ${r.skipped}`);
    } catch (e) {
      setSyncResult(String(e));
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div className="relative">
      <button
        className={`rounded px-3 py-1 text-xs font-medium ${
          configured ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"
        }`}
        onClick={() => setOpen((o) => !o)}
      >
        {configured ? `✓ ${settings?.agent_model}` : "⚠ Configure API key"}
      </button>
      {open && (
        <div className="absolute right-0 z-10 mt-2 w-80 space-y-2 rounded border bg-white p-3 shadow">
          <label className="block text-xs font-medium text-slate-600">Anthropic API key</label>
          <input
            type="password"
            className="w-full rounded border px-2 py-1 text-sm"
            placeholder={configured ? "••••• (set)" : "sk-ant-…"}
            value={key}
            onChange={(e) => setKey(e.target.value)}
          />
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
          <label className="block text-xs font-medium text-slate-600">Agent model</label>
          <input
            className="w-full rounded border px-2 py-1 text-sm"
            placeholder={settings?.agent_model ?? "claude-sonnet-4-6"}
            value={model}
            onChange={(e) => setModel(e.target.value)}
          />

          <hr className="border-slate-200" />
          <p className="text-xs font-semibold text-slate-700">Google / Gmail</p>
          {google?.connected && (
            <p className="text-[11px] text-emerald-700">✓ Connected as {google.email}</p>
          )}
          <label className="block text-xs font-medium text-slate-600">Google client ID</label>
          <input
            className="w-full rounded border px-2 py-1 text-sm"
            placeholder={google?.credentials_configured ? "••••• (set)" : "…apps.googleusercontent.com"}
            value={googleClientId}
            onChange={(e) => setGoogleClientId(e.target.value)}
          />
          <label className="block text-xs font-medium text-slate-600">Google client secret</label>
          <input
            type="password"
            className="w-full rounded border px-2 py-1 text-sm"
            placeholder={google?.credentials_configured ? "••••• (set)" : "GOCSPX-…"}
            value={googleClientSecret}
            onChange={(e) => setGoogleClientSecret(e.target.value)}
          />

          <button
            className="w-full rounded bg-accent py-1.5 text-sm font-medium text-white"
            onClick={save}
          >
            Save
          </button>

          {google?.credentials_configured && (
            <a
              href="/api/google/oauth/start"
              target="_blank"
              rel="noopener noreferrer"
              className="block w-full rounded border border-blue-300 py-1.5 text-center text-sm font-medium text-blue-700 hover:bg-blue-50"
            >
              {google.connected ? "Re-connect Google" : "Connect Google"}
            </a>
          )}
          {google?.connected && (
            <button
              className="w-full rounded border border-slate-300 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              onClick={doSync}
              disabled={syncing}
            >
              {syncing ? "Syncing…" : "Sync Gmail"}
            </button>
          )}
          {syncResult && (
            <p className="text-[11px] text-slate-500">{syncResult}</p>
          )}

          <p className="text-[11px] text-slate-400">
            Stored locally. If left blank, the local Claude CLI&rsquo;s own auth is used.
          </p>
        </div>
      )}
    </div>
  );
}
