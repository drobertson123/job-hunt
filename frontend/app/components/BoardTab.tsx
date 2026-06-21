"use client";

import { useCallback, useEffect, useState } from "react";
import {
  DndContext,
  DragEndEvent,
  PointerSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import { OpportunityFull, PipelineBoard, fetchPipeline, updateStage } from "@/lib/api";
import FetchError from "@/app/components/FetchError";

type Filter = "all" | "job" | "business";

/** Derive two-letter initials from an org or title string. */
function getInitials(text: string | null | undefined): string {
  if (!text) return "?";
  const words = text.trim().split(/\s+/);
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[1][0]).toUpperCase();
}

function Card({ opp, onOpen }: { opp: OpportunityFull; onOpen: (id: string) => void }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: opp.id,
  });
  const style = transform
    ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)` }
    : undefined;

  const initials = getInitials(opp.organization || opp.title);

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...listeners}
      {...attributes}
      onClick={() => onOpen(opp.id)}
      className={`relative cursor-grab overflow-hidden rounded-lg border border-line bg-surface p-3.5 transition hover:-translate-y-px hover:shadow-card ${
        isDragging ? "opacity-50" : ""
      }`}
    >
      {/* Left accent stripe */}
      <div className="absolute left-0 top-0 h-full w-[3px] rounded-l-lg bg-accent" />

      {/* Header row: initials chip + company + fit pill */}
      <div className="flex items-start gap-2.5">
        <span className="flex h-8 w-8 flex-none items-center justify-center rounded-md bg-accent-tint text-[11px] font-bold text-accent">
          {initials}
        </span>
        <div className="min-w-0 flex-1">
          <div className="truncate text-[13px] font-semibold text-ink">
            {opp.organization ?? "—"}
          </div>
        </div>
        {opp.fit_score != null && (
          <span className="flex-none rounded-xs bg-accent-tint px-1.5 py-0.5 text-[11px] font-semibold text-accent">
            Fit {opp.fit_score}
          </span>
        )}
      </div>

      {/* Role / title */}
      <div className="mt-2 text-[13.5px] font-semibold text-ink">{opp.title}</div>

      {/* Meta: location or stage hint */}
      {opp.location && (
        <div className="mt-1 truncate text-[12px] text-ink-muted">{opp.location}</div>
      )}
    </div>
  );
}

function Column({
  stage,
  opps,
  onOpen,
}: {
  stage: string;
  opps: OpportunityFull[];
  onOpen: (id: string) => void;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: stage });

  // Capitalise the stage label
  const label = stage.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

  return (
    <div
      ref={setNodeRef}
      className={`w-[290px] flex-none flex flex-col rounded-xl border border-line-strong p-2.5 transition ${
        isOver ? "bg-accent-tint/40" : "bg-paper"
      }`}
    >
      {/* Column header */}
      <div className="mb-2.5 flex items-center justify-between px-1">
        <h3 className="text-[13.5px] font-bold text-ink">{label}</h3>
        <span className="rounded-xs bg-surface px-1.5 py-0.5 text-[11px] font-semibold text-ink-muted">
          {opps.length}
        </span>
      </div>

      {/* Cards */}
      <div className="flex flex-col gap-2">
        {opps.map((o) => (
          <Card key={o.id} opp={o} onOpen={onOpen} />
        ))}
      </div>

      {/* Add job dashed button */}
      <button className="mt-2.5 w-full rounded-lg border border-dashed border-line-strong py-2 text-[12px] text-ink-faint transition hover:border-accent hover:text-accent">
        + Add job
      </button>
    </div>
  );
}

export default function BoardTab({ onOpen }: { onOpen: (oppId: string) => void }) {
  const [board, setBoard] = useState<PipelineBoard | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [error, setError] = useState(false);
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
  );

  const load = useCallback(() => {
    fetchPipeline(filter === "all" ? undefined : filter)
      .then((b) => { setError(false); setBoard(b); })
      .catch(() => { setError(true); setBoard(null); });
  }, [filter]);

  useEffect(() => {
    load();
  }, [load]);

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || !board) return;
    const oppId = String(active.id);
    const newStage = String(over.id);
    // find the card + its current stage
    let from: string | null = null;
    let card: OpportunityFull | undefined;
    for (const [stage, opps] of Object.entries(board.by_stage)) {
      const found = opps.find((o) => o.id === oppId);
      if (found) {
        from = stage;
        card = found;
        break;
      }
    }
    if (!card || from === null || from === newStage) return;
    // optimistic move
    const next: PipelineBoard = {
      columns: board.columns,
      by_stage: Object.fromEntries(
        board.columns.map((s) => [s, [...(board.by_stage[s] ?? [])]]),
      ),
    };
    next.by_stage[from] = next.by_stage[from].filter((o) => o.id !== oppId);
    next.by_stage[newStage] = [...(next.by_stage[newStage] ?? []), { ...card, stage: newStage }];
    setBoard(next);
    updateStage(oppId, newStage, "moved via board").catch(() => load());
  };

  if (error) return <FetchError onRetry={load} />;
  if (!board) {
    return <p className="p-4 text-sm text-ink-muted">Loading…</p>;
  }

  const total = board.columns.reduce((n, s) => n + (board.by_stage[s]?.length ?? 0), 0);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {/* Filter pills */}
      <div className="flex gap-1 px-4 pt-3 pb-2">
        {(["all", "job", "business"] as Filter[]).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`rounded-md px-3 py-1 text-xs capitalize transition ${
              filter === f
                ? "bg-accent text-white"
                : "bg-surface text-ink-muted hover:bg-accent-tint hover:text-accent"
            }`}
          >
            {f}
          </button>
        ))}
      </div>

      {/* Auto-discovery strip */}
      <div className="mx-4 mb-3 flex items-center gap-3.5 rounded-md border border-line bg-surface px-4 py-2.5">
        <span className="h-2 w-2 flex-none animate-pulse rounded-full bg-accent" />
        <span className="text-[13px] font-semibold text-ink">Auto-discovery</span>
        <div className="flex-1 h-[5px] rounded bg-accent-tint">
          <div className="h-full w-[60%] rounded bg-accent" />
        </div>
        <span className="font-mono text-[11.5px] text-ink-muted">Scanning sources…</span>
      </div>

      {total === 0 ? (
        <p className="p-4 text-sm text-ink-muted">No opportunities in this view.</p>
      ) : (
        <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
          <div className="flex min-h-0 flex-1 gap-3 overflow-x-auto px-4 pb-4">
            {board.columns.map((stage) => (
              <Column key={stage} stage={stage} opps={board.by_stage[stage] ?? []} onOpen={onOpen} />
            ))}
          </div>
        </DndContext>
      )}
    </div>
  );
}
