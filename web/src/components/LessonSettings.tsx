"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { useLessonSettings } from "@/hooks/use-lesson-settings";
import { cn } from "@/lib/utils";

/**
 * "Lesson settings" — a small header button that opens an accessible modal with
 * two friendly, non-technical controls:
 *   • Questions per topic   (1–5, default 2)  → questions_per_objective
 *   • Number of topics       (1–8, default 6)  → max_objectives
 *
 * Values live in the LessonSettings context and are read by the Uploader at
 * kickoff, so they apply to the NEXT lesson. Changing them mid-lesson does not
 * alter the current run.
 *
 * `@radix-ui/react-dialog` is NOT installed, so this is a small hand-rolled
 * modal: fixed overlay + centered card, focus moved into the dialog, Esc and
 * overlay-click to close, `role="dialog"` + `aria-modal`. Motion follows the
 * house tokens (overlay fade; card fade + translateY(8px)→0, ~200ms ease-out).
 */
export function LessonSettings() {
  const [open, setOpen] = useState(false);

  return (
    <>
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => setOpen(true)}
        aria-haspopup="dialog"
      >
        <span aria-hidden>⚙</span> Lesson settings
      </Button>
      {open && <SettingsModal onClose={() => setOpen(false)} />}
    </>
  );
}

function SettingsModal({ onClose }: { onClose: () => void }) {
  const {
    questionsPerObjective,
    maxObjectives,
    setQuestionsPerObjective,
    setMaxObjectives,
  } = useLessonSettings();

  const cardRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  // Esc to close + lock background scroll while open.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    // Move focus into the dialog (the Done button) for keyboard users.
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
        ref={cardRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="lesson-settings-title"
        className="flex w-full max-w-md flex-col gap-5 rounded-[var(--radius)] border border-[var(--border)] bg-[var(--card)] p-6 shadow-xl animate-modal-in"
      >
        <div className="flex flex-col gap-1">
          <h2
            id="lesson-settings-title"
            className="font-[family-name:var(--font-display)] text-xl font-medium"
          >
            Lesson settings
          </h2>
          <p className="text-sm text-[var(--muted-foreground)]">
            Fine-tune the length and depth of your next lesson.
          </p>
        </div>

        <Stepper
          label="Questions per topic"
          helper="How many quiz questions to ask for each topic."
          value={questionsPerObjective}
          min={1}
          max={5}
          onChange={setQuestionsPerObjective}
        />

        <Stepper
          label="Number of topics"
          helper="How many topics to break your document into."
          value={maxObjectives}
          min={1}
          max={8}
          onChange={setMaxObjectives}
        />

        <p className="text-xs text-[var(--muted-foreground)]">
          Applies to your next lesson.
        </p>

        <div className="flex justify-end">
          <Button ref={closeRef} type="button" onClick={onClose}>
            Done
          </Button>
        </div>
      </div>
    </div>
  );
}

/**
 * A friendly − value + stepper. The +/− buttons press-scale (via the shared
 * `press` utility on Button) and disable at the bounds. Clamps to [min, max].
 */
function Stepper({
  label,
  helper,
  value,
  min,
  max,
  onChange,
}: {
  label: string;
  helper: string;
  value: number;
  min: number;
  max: number;
  onChange: (n: number) => void;
}) {
  const dec = () => onChange(Math.max(min, value - 1));
  const inc = () => onChange(Math.min(max, value + 1));

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-col gap-0.5">
        <span className="text-sm font-medium text-[var(--foreground)]">
          {label}
        </span>
        <span className="text-xs text-[var(--muted-foreground)]">{helper}</span>
      </div>
      <div
        className="flex items-center gap-2"
        role="group"
        aria-label={label}
      >
        <Button
          type="button"
          variant="outline"
          size="icon"
          onClick={dec}
          disabled={value <= min}
          aria-label={`Decrease ${label.toLowerCase()}`}
        >
          −
        </Button>
        <span
          aria-live="polite"
          className={cn(
            "flex h-9 min-w-12 items-center justify-center rounded-[var(--radius)]",
            "border border-[var(--border)] bg-[var(--background)] text-base font-semibold tabular-nums",
          )}
        >
          {value}
        </span>
        <Button
          type="button"
          variant="outline"
          size="icon"
          onClick={inc}
          disabled={value >= max}
          aria-label={`Increase ${label.toLowerCase()}`}
        >
          +
        </Button>
      </div>
    </div>
  );
}
