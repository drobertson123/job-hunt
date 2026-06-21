"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AgentEvent,
  Application,
  Artifact,
  Capability,
  Note,
  Opportunity,
  SettingsView,
  fetchActions,
  fetchApplications,
  fetchArtifacts,
  fetchAttention,
  fetchCapabilities,
  fetchCompanies,
  fetchNotes,
  fetchOpportunities,
  getSettings,
  invokeCapability,
  streamChat,
  updateSettings,
} from "@/lib/api";
import ProfileTab from "./components/ProfileTab";
import ApplicationsTab from "./components/ApplicationsTab";
import MarkdownView from "./components/MarkdownView";
import ArtifactCard from "./components/ArtifactCard";
import BriefingTab from "./components/BriefingTab";
import OpportunityDetailTab from "./components/OpportunityDetailTab";
import BoardTab from "./components/BoardTab";
import AttentionTab from "./components/AttentionTab";
import CompaniesTab from "./components/CompaniesTab";
import ActionsTab from "./components/ActionsTab";
import InterviewsTab from "./components/InterviewsTab";
import SourcesTab from "./components/SourcesTab";
import WeeklyTab from "./components/WeeklyTab";
import CanvasNav from "./components/CanvasNav";

type ChatItem =
  | { kind: "user"; text: string }
  | { kind: "assistant"; text: string }
  | { kind: "tool"; text: string }
  | { kind: "error"; text: string };

export default function Home() {
  const [items, setItems] = useState<ChatItem[]>([]);
  const [input, setInput] = useState("");
  const [running, setRunning] = useState(false);
  const [notes, setNotes] = useState<Note[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [caps, setCaps] = useState<Capability[]>([]);
  const [opps, setOpps] = useState<Opportunity[]>([]);
  const [selectedOpp, setSelectedOpp] = useState("");
  const [settings, setSettings] = useState<SettingsView | null>(null);
  const [canvasTab, setCanvasTab] = useState<
    "workspace" | "profile" | "applications" | "briefing" | "detail" | "board" | "attention" | "companies" | "actions" | "interviews" | "sources" | "weekly"
  >("workspace");
  const [applications, setApplications] = useState<Application[]>([]);
  const [attentionCount, setAttentionCount] = useState(0);
  const [companyCount, setCompanyCount] = useState(0);
  const [openActionCount, setOpenActionCount] = useState(0);
  const scrollRef = useRef<HTMLDivElement>(null);

  const refreshCanvas = useCallback(async () => {
    try {
      const [n, a, o, apps, att, companies, openActions] = await Promise.all([
        fetchNotes(),
        fetchArtifacts(),
        fetchOpportunities(),
        fetchApplications(),
        fetchAttention(),
        fetchCompanies(),
        fetchActions("open"),
      ]);
      setNotes(n);
      setArtifacts(a);
      setOpps(o);
      setApplications(apps);
      setAttentionCount(att.counts.total);
      setCompanyCount(companies.length);
      setOpenActionCount(openActions.length);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    getSettings().then(setSettings).catch(() => setSettings(null));
    fetchCapabilities().then(setCaps).catch(() => setCaps([]));
    refreshCanvas();
  }, [refreshCanvas]);

  useEffect(() => {
    scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight);
  }, [items]);

  const makeOnEvent = useCallback(() => {
    return (e: AgentEvent) => {
      setItems((prev) => {
        const next = [...prev];
        if (e.type === "token") {
          // append to the trailing assistant bubble
          for (let i = next.length - 1; i >= 0; i--) {
            if (next[i].kind === "assistant") {
              next[i] = { kind: "assistant", text: next[i].text + e.content };
              break;
            }
          }
        } else if (e.type === "tool_use") {
          let name = e.content;
          try {
            name = JSON.parse(e.content).name ?? e.content;
          } catch {
            /* keep raw */
          }
          next.push({ kind: "tool", text: `🔧 ${name}` });
          next.push({ kind: "assistant", text: "" });
        } else if (e.type === "error") {
          next.push({ kind: "error", text: e.content });
        }
        return next;
      });
      if (e.type === "tool_result" || e.type === "result") refreshCanvas();
    };
  }, [refreshCanvas]);

  const runStream = useCallback(
    async (
      bubble: string,
      start: (onEvent: (e: AgentEvent) => void) => Promise<void>,
    ) => {
      if (running) return;
      setRunning(true);
      setItems((prev) => [
        ...prev,
        { kind: "user", text: bubble },
        { kind: "assistant", text: "" },
      ]);
      try {
        await start(makeOnEvent());
      } catch (err) {
        setItems((prev) => [...prev, { kind: "error", text: String(err) }]);
      } finally {
        setRunning(false);
        refreshCanvas();
      }
    },
    [running, makeOnEvent, refreshCanvas],
  );

  const send = useCallback(async () => {
    const prompt = input.trim();
    if (!prompt) return;
    setInput("");
    await runStream(prompt, (onEvent) => streamChat(prompt, onEvent));
  }, [input, runStream]);

  const invoke = useCallback(
    async (cap: Capability) => {
      const text = input.trim();
      if (cap.requires_input && !text) {
        setItems((prev) => [
          ...prev,
          {
            kind: "error",
            text: `"${cap.label}" needs input — paste it into the message box first.`,
          },
        ]);
        return;
      }
      if (cap.requires_input) setInput("");
      await runStream(`▶ ${cap.label}`, (onEvent) =>
        invokeCapability(
          cap.name,
          { opportunity_id: selectedOpp || undefined, input: text },
          onEvent,
        ),
      );
    },
    [input, selectedOpp, runStream],
  );

  return (
    <main className="flex h-screen flex-col">
      <header className="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-2.5">
        <div className="flex items-center gap-2.5">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-600 text-sm font-bold text-white">
            O
          </span>
          <div className="leading-tight">
            <h1 className="text-base font-semibold text-slate-900">Opportunity Hunter</h1>
            <p className="text-[11px] text-slate-400">Your job-hunt command center</p>
          </div>
        </div>
        <SettingsBadge settings={settings} onSaved={setSettings} />
      </header>

      <div className="flex min-h-0 flex-1 flex-col md:flex-row">
        {/* Chat pane */}
        <section className="flex min-h-0 flex-1 flex-col border-r">
          {/* Capability bar */}
          <div className="flex flex-wrap items-center gap-2 border-b bg-slate-50 px-3 py-2">
            <select
              className="rounded border px-2 py-1 text-xs"
              value={selectedOpp}
              onChange={(e) => setSelectedOpp(e.target.value)}
            >
              <option value="">— opportunity —</option>
              {opps.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.organization ? `${o.organization} — ${o.title}` : o.title}
                </option>
              ))}
            </select>
            {caps.map((c) => (
              <button
                key={c.name}
                title={c.description}
                className="rounded-md bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-700 transition hover:bg-indigo-50 hover:text-indigo-700 disabled:opacity-40"
                onClick={() => invoke(c)}
                disabled={running || (c.requires_opportunity && !selectedOpp)}
              >
                {c.label}
              </button>
            ))}
          </div>

          <div ref={scrollRef} className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
            {items.length === 0 && (
              <p className="text-sm text-slate-500">
                Message the agent, or pick an opportunity and press a capability
                button. &ldquo;Add by paste&rdquo; uses whatever you&rsquo;ve typed
                in the message box.
              </p>
            )}
            {items.map((it, i) => (
              <Bubble key={i} item={it} />
            ))}
          </div>
          <div className="flex gap-2 border-t bg-white p-3">
            <input
              className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              placeholder="Message the agent…"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && send()}
              disabled={running}
            />
            <button
              className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-500 disabled:opacity-50"
              onClick={send}
              disabled={running || !input.trim()}
            >
              {running ? "…" : "Send"}
            </button>
          </div>
        </section>

        {/* Canvas pane */}
        <section className="flex min-h-0 flex-1 flex-col bg-white">
          <CanvasNav
            active={canvasTab}
            onSelect={(t) => setCanvasTab(t as typeof canvasTab)}
            counts={{
              board: opps.length,
              attention: attentionCount,
              applications: applications.length,
              actions: openActionCount,
              companies: companyCount,
              workspace: artifacts.length + notes.length,
            }}
          />
          {canvasTab === "profile" ? (
            <ProfileTab />
          ) : canvasTab === "applications" ? (
            <ApplicationsTab />
          ) : canvasTab === "briefing" ? (
            <BriefingTab opportunityId={selectedOpp} />
          ) : canvasTab === "detail" ? (
            <OpportunityDetailTab opportunityId={selectedOpp} />
          ) : canvasTab === "board" ? (
            <BoardTab
              onOpen={(id) => {
                setSelectedOpp(id);
                setCanvasTab("detail");
              }}
            />
          ) : canvasTab === "attention" ? (
            <AttentionTab
              onOpen={(id) => {
                setSelectedOpp(id);
                setCanvasTab("detail");
              }}
            />
          ) : canvasTab === "companies" ? (
            <CompaniesTab
              onOpen={(id) => {
                setSelectedOpp(id);
                setCanvasTab("detail");
              }}
            />
          ) : canvasTab === "actions" ? (
            <ActionsTab
              onOpen={(id) => {
                setSelectedOpp(id);
                setCanvasTab("detail");
              }}
            />
          ) : canvasTab === "interviews" ? (
            <InterviewsTab
              onOpen={(id) => {
                setSelectedOpp(id);
                setCanvasTab("detail");
              }}
            />
          ) : canvasTab === "sources" ? (
            <SourcesTab />
          ) : canvasTab === "weekly" ? (
            <WeeklyTab
              onOpen={(id) => {
                setSelectedOpp(id);
                setCanvasTab("detail");
              }}
            />
          ) : (
            <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
              {artifacts.length === 0 && notes.length === 0 && (
                <p className="text-sm text-slate-400">
                  Artifacts and notes the agent saves will appear here.
                </p>
              )}
              {artifacts.map((a) => (
                <ArtifactCard key={`a-${a.id}`} artifact={a} onChanged={refreshCanvas} />
              ))}
              {notes.map((n) => (
                <article key={`n-${n.id}`} className="rounded border bg-slate-50 p-3">
                  <h3 className="text-sm font-semibold">{n.title}</h3>
                  <MarkdownView className="mt-1" text={n.body} />
                </article>
              ))}
            </div>
          )}
        </section>
      </div>
    </main>
  );
}

function Bubble({ item }: { item: ChatItem }) {
  if (item.kind === "user") {
    return (
      <div className="ml-auto max-w-[85%] rounded-lg bg-slate-900 px-3 py-2 text-sm text-white">
        {item.text}
      </div>
    );
  }
  if (item.kind === "tool") {
    return <div className="text-xs font-medium text-amber-700">{item.text}</div>;
  }
  if (item.kind === "error") {
    return (
      <div className="max-w-[85%] rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
        {item.text}
      </div>
    );
  }
  if (!item.text) return null;
  return (
    <div className="max-w-[85%] whitespace-pre-wrap rounded-lg bg-slate-100 px-3 py-2 text-sm">
      {item.text}
    </div>
  );
}

function SettingsBadge({
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
  const configured = settings?.anthropic_key_configured;

  const save = async () => {
    const body: Record<string, string> = {};
    if (key.trim()) body.anthropic_api_key = key.trim();
    if (openaiKey.trim()) body.openai_api_key = openaiKey.trim();
    if (model.trim()) body.agent_model = model.trim();
    const updated = await updateSettings(body);
    onSaved(updated);
    setKey("");
    setOpenaiKey("");
    setOpen(false);
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
          <button
            className="w-full rounded bg-slate-900 py-1.5 text-sm font-medium text-white"
            onClick={save}
          >
            Save
          </button>
          <p className="text-[11px] text-slate-400">
            Stored locally. If left blank, the local Claude CLI&rsquo;s own auth is used.
          </p>
        </div>
      )}
    </div>
  );
}
