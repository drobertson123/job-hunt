# Assistant Pop-out Drawer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Move the AI interaction UI (capability bar + message thread + input) out of the fixed left pane into a **slide-out drawer docked on the right edge**, so the canvas fills the main area.

**Architecture:** A single-file change to `frontend/app/page.tsx`: relocate the existing chat `<section>` into a fixed right-edge drawer toggled by `assistantOpen` state, give the canvas full width, and add an edge launcher. All chat handlers/state stay as-is.

## Global Constraints
- Visual/layout only — do NOT change `send`/`invoke`/`runStream`/state logic, the capability bar contents, the message thread (`Bubble`), or the input behavior. Just relocate the markup and add the open/close affordances.
- Tailwind JIT: literal class strings.
- `npm --prefix frontend install` first (no node_modules), then `npm --prefix frontend run build` must succeed.
- Do NOT invoke any finishing/branch skill — stop after committing.

---

### Task 1: Right-edge assistant drawer

**Files:** Modify `frontend/app/page.tsx`.

- [ ] **Step 1: Add open + width state (drawer is resizable)**

Near the other `useState` declarations, add:
```tsx
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
```
(`useEffect`/`useCallback` are already imported in page.tsx; if not, add them.)

- [ ] **Step 2: Auto-open on interaction**

In the `send` function and the `invoke` function (the two places that start agent activity), add `setAssistantOpen(true);` at the top of each so the drawer pops open when the user sends a message or runs a capability. (Find them via `const send =` / `const invoke =` or the handlers that call `runStream`.)

- [ ] **Step 3: Canvas full-width; chat → right drawer**

The current body is:
```tsx
<div className="flex min-h-0 flex-1">
  <IconRail … />
  <div className="flex min-h-0 flex-1 flex-col md:flex-row">
    <section className="flex min-h-0 flex-1 flex-col border-r border-line"> … CHAT … </section>
    {/* Canvas pane */}
    <section …> … CANVAS … </section>
  </div>
</div>
```
Restructure to:
```tsx
<div className="flex min-h-0 flex-1">
  <IconRail … />
  <div className="flex min-h-0 flex-1 flex-col">
    {/* Canvas pane — now full width (unchanged inner content) */}
    <section …> … CANVAS … </section>
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
    {/* MOVE the existing chat content here: the capability bar <div>, the thread
        <div ref={scrollRef}>…</div>, and the input row <div>. Paste them verbatim
        from the old <section>; drop the old section's `border-r` wrapper. They
        keep all their existing handlers (selectedOpp/caps/invoke/items/Bubble/
        input/send/running/scrollRef). */}
  </aside>
</div>
```
Concretely: take the THREE inner blocks of the old chat `<section>` (the capability bar, the `scrollRef` thread, the input row) and place them inside the `<aside>` after its header. Delete the now-empty old `<section className="… border-r …">` wrapper and the `flex-col md:flex-row` wrapper's no-longer-needed row behavior (the canvas section becomes the sole flex child).

- [ ] **Step 4: Build**

Run: `npm --prefix frontend install` then `npm --prefix frontend run build` — must succeed (type-checks). Confirm all 13 canvas render branches and the chat handlers are intact.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/page.tsx
git commit -m "feat(ui): AI assistant as a right-edge slide-out drawer (canvas full-width)"
```
