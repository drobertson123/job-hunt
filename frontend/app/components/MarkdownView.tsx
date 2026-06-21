"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export default function MarkdownView({
  text,
  className = "",
}: {
  text: string;
  className?: string;
}) {
  const [mode, setMode] = useState<"rendered" | "raw">("rendered");
  if (!text || !text.trim()) return null;

  return (
    <div className={className}>
      <div className="mb-1 flex justify-end gap-1 text-xs">
        {(["rendered", "raw"] as const).map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => setMode(m)}
            className={`rounded px-2 py-0.5 capitalize ${
              mode === m
                ? "bg-slate-700 text-white"
                : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            {m}
          </button>
        ))}
      </div>
      {mode === "rendered" ? (
        <div className="prose prose-sm max-w-none text-slate-700">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
        </div>
      ) : (
        <pre className="whitespace-pre-wrap break-words font-mono text-sm text-slate-700">
          {text}
        </pre>
      )}
    </div>
  );
}
