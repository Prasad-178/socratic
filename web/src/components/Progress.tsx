"use client";

import { useAgent } from "@copilotkit/react-core/v2";

import { Spinner } from "@/components/ui/spinner";

/** Subset of the agent's shared state this component reads (read-only). */
interface SocraticState {
  phase?: string;
}

// Keys match the exact phase strings written by the agent:
//   "awaiting_approval" — plan_node (graph.py) after map-reduce planning
//   "quizzing"          — approve_plan_node / select_objective_node (quiz.py)
//   "summarizing"       — select_objective_node when objectives exhausted (quiz.py)
//   "done"              — summarize_node; Progress hides itself at this phase
// Before any phase is set, isRunning → "Planning your lesson…" (see label below).
const PHASE_LABEL: Record<string, string> = {
  awaiting_approval: "Review your lesson plan",
  quizzing: "Quiz in progress",
  summarizing: "Wrapping up…",
  // "done" is intentionally absent — Progress returns null for phase === "done".
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
    (isRunning ? "Planning your lesson…" : "Ready");

  return (
    <div className="flex items-center gap-2 rounded-[var(--radius)] border border-[var(--border)] bg-[var(--card)] px-3 py-2 text-sm text-[var(--muted-foreground)]">
      {isRunning && <Spinner size="sm" />}
      <span>{label}</span>
    </div>
  );
}
