"use client";

export default function FetchError({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="p-4 text-sm text-slate-500">
      Couldn't load.{" "}
      <button onClick={onRetry} className="text-blue-600 underline">
        Retry
      </button>
    </div>
  );
}
