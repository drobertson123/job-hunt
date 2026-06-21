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

function Card({ opp, onOpen }: { opp: OpportunityFull; onOpen: (id: string) => void }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: opp.id,
  });
  const style = transform
    ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)` }
    : undefined;
  return (
    <div
      ref={setNodeRef}
      style={style}
      {...listeners}
      {...attributes}
      onClick={() => onOpen(opp.id)}
      className={`cursor-grab rounded border border-slate-200 bg-white p-2 text-sm shadow-sm ${
        isDragging ? "opacity-50" : ""
      }`}
    >
      <div className="font-medium">{opp.title}</div>
      <div className="flex items-center gap-2 text-xs text-slate-500">
        {opp.organization}
        {opp.fit_score != null && (
          <span className="rounded bg-slate-100 px-1.5 py-0.5">Fit {opp.fit_score}</span>
        )}
      </div>
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
  return (
    <div
      ref={setNodeRef}
      className={`flex w-56 shrink-0 flex-col gap-2 rounded p-2 ${
        isOver ? "bg-slate-100" : "bg-slate-50"
      }`}
    >
      <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
        {stage} ({opps.length})
      </h3>
      {opps.map((o) => (
        <Card key={o.id} opp={o} onOpen={onOpen} />
      ))}
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
    return <p className="p-4 text-sm text-slate-400">Loading…</p>;
  }

  const total = board.columns.reduce((n, s) => n + (board.by_stage[s]?.length ?? 0), 0);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex gap-1 p-2">
        {(["all", "job", "business"] as Filter[]).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`rounded px-2 py-1 text-xs capitalize ${
              filter === f ? "bg-accent text-white" : "bg-slate-100 text-slate-600"
            }`}
          >
            {f}
          </button>
        ))}
      </div>
      {total === 0 ? (
        <p className="p-4 text-sm text-slate-400">No opportunities in this view.</p>
      ) : (
        <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
          <div className="flex min-h-0 flex-1 gap-2 overflow-x-auto p-2">
            {board.columns.map((stage) => (
              <Column key={stage} stage={stage} opps={board.by_stage[stage] ?? []} onOpen={onOpen} />
            ))}
          </div>
        </DndContext>
      )}
    </div>
  );
}
