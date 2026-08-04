import { useEffect } from "react";

export type HotkeyHandlers = {
  onNewSession?: () => void;
  onSettings?: () => void;
  onWorkbench?: () => void;
  onEvidence?: () => void;
  onRun?: () => void;
  onEscape?: () => void;
};

function isEditableTarget(t: EventTarget | null): boolean {
  if (!(t instanceof HTMLElement)) return false;
  const tag = t.tagName;
  if (tag === "TEXTAREA" || tag === "INPUT" || tag === "SELECT") return true;
  if (t.isContentEditable) return true;
  return false;
}

/** Global app shortcuts. ⌘Enter still works inside task textarea. */
export function useHotkeys(handlers: HotkeyHandlers) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const meta = e.metaKey || e.ctrlKey;
      const key = e.key.toLowerCase();

      if (e.key === "Escape") {
        handlers.onEscape?.();
        return;
      }

      // ⌘Enter → run (allowed in textarea)
      if (meta && key === "enter") {
        handlers.onRun?.();
        // composer also handles this; don't preventDefault here so both can fire once
        return;
      }

      if (isEditableTarget(e.target) && !(meta && key === "enter")) {
        // allow ⌘, and view switches even from inputs when using meta
        if (!(meta && (key === "," || key === "1" || key === "2" || key === "n"))) {
          return;
        }
      }

      if (!meta) return;

      if (key === "n") {
        e.preventDefault();
        handlers.onNewSession?.();
      } else if (key === ",") {
        e.preventDefault();
        handlers.onSettings?.();
      } else if (key === "1") {
        e.preventDefault();
        handlers.onWorkbench?.();
      } else if (key === "2") {
        e.preventDefault();
        handlers.onEvidence?.();
      }
    };

    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [handlers]);
}
