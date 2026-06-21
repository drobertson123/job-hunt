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
import IconRail from "./components/IconRail";
import LibraryTab from "./components/LibraryTab";
import ContactsTab from "./components/ContactsTab";
import MetricsTab from "./components/MetricsTab";
import SettingsBadge from "./components/SettingsBadge";

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
    "workspace" | "profile" | "applications" | "briefing" | "detail" | "board" | "attention" | "companies" | "actions" | "interviews" | "sources" | "weekly" | "library" | "contacts" | "metrics"
  >("workspace");
  const [applications, setApplications] = useState<Application[]>([]);
  const [attentionCount, setAttentionCount] = useState(0);
  const [companyCount, setCompanyCount] = useState(0);
  const [openActionCount, setOpenActionCount] = useState(0);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [drawerWidth, setDrawerWidth] = useState(440);

  useEffect(() => {
    const saved = Number(localStorage.getItem("jh.assistantWidth"));
    if (saved >= 320 && saved <= 760) setDrawerWidth(saved);
  }, []);

  const startDrawerResize = useCallback((e: React.PointerEvent) => {
    e.preventDefault();
    const onMove = (ev: PointerEvent) => {
      const w = Math.min(Math.max(window.innerWidth - ev.clientX, 320), Math.min(760, window.innerWidth * 0.92));
      setDrawerWidth(w);
    };
    const onUp = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      setDrawerWidth((w) => {
        localStorage.setItem("jh.assistantWidth", String(Math.round(w)));
        return w;
      });
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  }, []);

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
    setAssistantOpen(true);
    const prompt = input.trim();
    if (!prompt) return;
    setInput("");
    await runStream(prompt, (onEvent) => streamChat(prompt, onEvent));
  }, [input, runStream]);

  const invoke = useCallback(
    async (cap: Capability) => {
      setAssistantOpen(true);
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
    <main className="flex h-screen flex-col bg-bg text-ink">
      <header className="flex h-[68px] flex-none items-center justify-between gap-5 border-b border-line bg-bg px-7">
        <div className="min-w-0">
          <div className="text-[21px] font-bold tracking-tight text-ink">Good morning</div>
          <div className="mt-0.5 text-[13px] text-ink-muted">
            Your hunt ·{" "}
            <span className="font-semibold text-error">{attentionCount} decisions</span> need you today
          </div>
        </div>
        <div className="flex flex-none items-center gap-3">
          <SettingsBadge settings={settings} onSaved={setSettings} />
          <button
            onClick={() => setCanvasTab("board")}
            className="flex items-center gap-1.5 rounded-md bg-accent px-4 py-2.5 text-[13.5px] font-semibold text-white shadow-accent transition hover:bg-accent-ink"
          >
            <svg width="15" height="15" viewBox="0 0 15 15" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round"><path d="M7.5 3v9M3 7.5h9"/></svg>
            Add job
          </button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <IconRail active={canvasTab} onSelect={(t) => setCanvasTab(t as typeof canvasTab)} />
        <div className="flex min-h-0 flex-1 flex-col">
          {/* Canvas pane — now full width (unchanged inner content) */}
          <section className="flex min-h-0 flex-1 flex-col bg-white">
            {canvasTab === "profile" ? (
              <ProfileTab />
            ) : canvasTab === "applications" ? (
              <ApplicationsTab />
            ) : canvasTab === "briefing" ? (
              <BriefingTab opportunityId={selectedOpp} />
            ) : canvasTab === "detail" ? (
              <OpportunityDetailTab opportunityId={selectedOpp} onBack={() => setCanvasTab("board")} />
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
            ) : canvasTab === "library" ? (
              <LibraryTab />
            ) : canvasTab === "contacts" ? (
              <ContactsTab onOpen={(id) => { setSelectedOpp(id); setCanvasTab("detail"); }} />
            ) : canvasTab === "metrics" ? (
              <MetricsTab />
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

        {/* Edge launcher (visible when the drawer is closed) */}
        {!assistantOpen && (
          <button
            onClick={() => setAssistantOpen(true)}
            title="Assistant"
            className="fixed right-0 top-1/2 z-30 flex -translate-y-1/2 items-center gap-2 rounded-l-md bg-accent py-3 pl-3 pr-2.5 text-white shadow-accent transition hover:bg-accent-ink"
          >
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="#fff" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M4 4h10v7H8l-3 3v-3H4z"/></svg>
            <span className="text-[11px] font-semibold [writing-mode:vertical-rl]">Assistant</span>
          </button>
        )}

        {/* Assistant drawer (right edge) — resizable via the left-edge handle */}
        <aside
          style={{ width: drawerWidth }}
          className={`fixed top-0 right-0 z-40 flex h-full max-w-[92vw] flex-col border-l border-line bg-surface shadow-card transition-transform duration-200 ${
            assistantOpen ? "translate-x-0" : "translate-x-full"
          }`}
        >
          {/* drag-to-resize handle (left edge) */}
          <div
            onPointerDown={startDrawerResize}
            title="Drag to resize"
            className="absolute left-0 top-0 z-10 h-full w-1.5 -translate-x-1/2 cursor-col-resize hover:bg-accent/40"
          />
          <div className="flex flex-none items-center justify-between border-b border-line px-4 py-3">
            <span className="text-[13.5px] font-semibold text-ink">Assistant</span>
            <button
              onClick={() => setAssistantOpen(false)}
              title="Close"
              className="flex h-7 w-7 items-center justify-center rounded-sm text-ink-muted transition hover:bg-surface-sunk"
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"><path d="M4 4l8 8M12 4l-8 8"/></svg>
            </button>
          </div>
          {/* Capability bar */}
          <div className="flex flex-wrap items-center gap-2 border-b border-line bg-surface-alt px-3 py-2">
            <select
              className="rounded-sm border border-line px-2 py-1 text-xs"
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
                className="rounded-sm border border-line bg-surface px-2.5 py-1 text-[11.5px] font-medium text-ink transition hover:bg-surface-sunk disabled:opacity-40"
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
          <div className="flex gap-2 border-t border-line bg-white p-3">
            <input
              className="flex-1 rounded-sm border border-line px-3 py-2 text-[12.5px] focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
              placeholder="Message the agent…"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && send()}
              disabled={running}
            />
            <button
              className="rounded-sm bg-accent px-4 py-2 text-[12.5px] font-medium text-white transition hover:bg-accent-ink disabled:opacity-50"
              onClick={send}
              disabled={running || !input.trim()}
            >
              {running ? "…" : "Send"}
            </button>
          </div>
        </aside>
      </div>
    </main>
  );
}

function Bubble({ item }: { item: ChatItem }) {
  if (item.kind === "user") {
    return (
      <div className="ml-auto max-w-[85%] rounded-lg bg-accent px-3 py-2 text-sm text-white">
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

