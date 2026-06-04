"use client";

import { cn } from "@/lib/utils";

/** The four orientation steps of the guided lesson. */
export type Step = "upload" | "plan" | "quiz" | "summary";

const STEPS: { id: Step; label: string }[] = [
  { id: "upload", label: "Upload" },
  { id: "plan", label: "Plan" },
  { id: "quiz", label: "Quiz" },
  { id: "summary", label: "Results" },
];

/**
 * Slim horizontal stepper that orients the learner: where am I in the flow?
 *
 * The `current` step is highlighted; completed steps read as done; upcoming
 * steps are muted. Purely presentational — the parent derives `current` from
 * the agent's active interrupt / phase.
 */
export function Stepper({ current }: { current: Step }) {
  const currentIndex = STEPS.findIndex((s) => s.id === current);

  return (
    <ol className="flex items-center gap-1.5 sm:gap-2" aria-label="Lesson progress">
      {STEPS.map((step, i) => {
        const state =
          i < currentIndex ? "done" : i === currentIndex ? "current" : "upcoming";
        return (
          <li key={step.id} className="flex items-center gap-1.5 sm:gap-2">
            <div className="flex items-center gap-2">
              <span
                className={cn(
                  "flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold transition-colors duration-200",
                  state === "current" &&
                    "bg-[var(--primary)] text-[var(--primary-foreground)]",
                  state === "done" &&
                    "bg-[var(--secondary)] text-[var(--secondary-foreground)]",
                  state === "upcoming" &&
                    "border border-[var(--border)] text-[var(--muted-foreground)]",
                )}
                aria-current={state === "current" ? "step" : undefined}
              >
                {state === "done" ? "✓" : i + 1}
              </span>
              <span
                className={cn(
                  "hidden text-sm transition-colors duration-200 sm:inline",
                  state === "current"
                    ? "font-medium text-[var(--foreground)]"
                    : "text-[var(--muted-foreground)]",
                )}
              >
                {step.label}
              </span>
            </div>
            {i < STEPS.length - 1 && (
              <span
                aria-hidden
                className={cn(
                  "h-px w-4 transition-colors duration-200 sm:w-8",
                  i < currentIndex
                    ? "bg-[var(--muted-foreground)]"
                    : "bg-[var(--border)]",
                )}
              />
            )}
          </li>
        );
      })}
    </ol>
  );
}
