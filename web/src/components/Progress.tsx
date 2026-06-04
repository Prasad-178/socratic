"use client";

import { useAgent } from "@copilotkit/react-core/v2";

import { Spinner } from "@/components/ui/spinner";

/** Subset of the agent's shared state this component reads (read-only). */
interface SocraticState {
  phase?: string;
}

const PHASE_LABEL: Record<string, string> = {
  planning: "Planning your lesson…",
  plan_approval: "Waiting for plan approval…",
  generating: "Generating questions…",
  quiz: "Quiz in progress",
  done: "Lesson complete",
};

/**
 * Small read-only status line driven by `agent.state.phase` and
 * `agent.isRunning`. Renders nothing before the agent has a phase and isn't
 * running (so the surface stays clean pre-upload).
 */
export function Progress() {
  const { agent } = useAgent();
  const state = (agent.state ?? {}) as SocraticState;
  const phase = state.phase;
  const isRunning = agent.isRunning;

  if (!phase && !isRunning) return null;

  // "done" gets its own Summary card; keep the progress line quiet there.
  if (phase === "done") return null;

  const label =
    (phase && PHASE_LABEL[phase]) ??
    (isRunning ? "Working…" : "Ready");

  return (
    <div className="flex items-center gap-2 rounded-[var(--radius)] border border-[var(--border)] bg-[var(--card)] px-3 py-2 text-sm text-[var(--muted-foreground)]">
      {isRunning && <Spinner size="sm" />}
      <span>{label}</span>
    </div>
  );
}
