"use client";

import { useCallback, useEffect, useRef } from "react";

import { Button } from "@/components/ui/button";

/**
 * A large, clean modal that renders the uploaded PDF in an <iframe> (browsers
 * render PDFs natively). Opened by clicking the collapsed file strip's filename.
 *
 * Reuses the hand-rolled modal pattern from LessonSettings: fixed overlay +
 * centered card, focus moved into the dialog, Esc and overlay-click to close,
 * `role="dialog"` + `aria-modal`, and the house motion tokens.
 */
export function PdfViewerModal({
  fileUrl,
  fileName,
  onClose,
}: {
  fileUrl: string;
  fileName: string;
  onClose: () => void;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);

  // Esc to close + lock background scroll while open.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    // Move focus into the dialog (the close button) for keyboard users.
    closeRef.current?.focus();
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [onClose]);

  // Only close on a click that starts AND ends on the overlay (not a drag from
  // inside the card).
  const onOverlayMouseDown = useCallback(
    (e: React.MouseEvent) => {
      if (e.target === e.currentTarget) onClose();
    },
    [onClose],
  );

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 animate-overlay-in"
      onMouseDown={onOverlayMouseDown}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="pdf-viewer-title"
        className="flex h-[85vh] w-[90vw] max-w-5xl flex-col gap-4 rounded-[var(--radius)] border border-[var(--border)] bg-[var(--card)] p-5 shadow-xl animate-modal-in"
      >
        <div className="flex items-center justify-between gap-4">
          <h2
            id="pdf-viewer-title"
            className="flex min-w-0 items-center gap-2 font-[family-name:var(--font-display)] text-lg font-medium"
          >
            <span aria-hidden className="shrink-0 text-base">
              📄
            </span>
            <span className="truncate">{fileName}</span>
          </h2>
          <Button
            ref={closeRef}
            type="button"
            variant="ghost"
            size="sm"
            className="shrink-0 text-[var(--muted-foreground)]"
            onClick={onClose}
            aria-label="Close PDF viewer"
          >
            Close
          </Button>
        </div>

        <iframe
          src={fileUrl}
          title={fileName}
          className="h-full w-full rounded-[var(--radius)] border border-[var(--border)] bg-[var(--background)]"
        />
      </div>
    </div>
  );
}
