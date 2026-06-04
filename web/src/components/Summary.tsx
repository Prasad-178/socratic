"use client";

import { useAgent } from "@copilotkit/react-core/v2";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";

/** One learning objective as stored in agent state (for id → title mapping). */
interface Objective {
  id: string;
  title: string;
}

/** Per-objective aggregate from the structured report. */
interface ByObjective {
  attempts: number;
  correct: number;
  n: number;
}

/** Subset of the agent's shared state this component reads (read-only). */
interface SocraticState {
  phase?: string;
  objectives?: Objective[];
  // New structured summary state (replaces the old `summary` markdown blob).
  headline?: string;
  study_tips?: string[];
  report?: {
    total: number;
    correct: number;
    by_objective: Record<string, ByObjective>;
    weak_objectives: string[];
  };
}

/**
 * Final lesson summary. Renders only once the agent reports `phase === "done"`.
 *
 * Reads the agent's STRUCTURED summary state:
 *   - `headline`   — a warm one-line title.
 *   - `report`     — { total, correct, by_objective, weak_objectives }.
 *   - `study_tips` — an array of plain strings (NO markdown), rendered as a
 *                    clean list rather than a raw markdown blob.
 *
 * The per-topic breakdown maps `by_objective`'s objective ids to human titles
 * via `agent.state.objectives`; if an id can't be mapped, that row is dropped
 * so we never surface raw UUIDs.
 */
export function Summary() {
  const { agent } = useAgent();
  const state = (agent.state ?? {}) as SocraticState;

  if (state.phase !== "done") return null;

  const report = state.report;
  const total = report?.total ?? 0;
  const correct = report?.correct ?? 0;
  const pct = total > 0 ? Math.round((correct / total) * 100) : 0;

  const headline = state.headline?.trim();
  const tips = (state.study_tips ?? []).filter((t) => !!t && t.trim().length > 0);

  // Map objective id → title. We only show a per-topic row when we can resolve
  // a real title, so raw UUIDs never leak into the UI.
  const titleById = new Map(
    (state.objectives ?? []).map((o) => [o.id, o.title]),
  );
  const perTopic = Object.entries(report?.by_objective ?? {})
    .map(([id, agg]) => ({ title: titleById.get(id), agg }))
    .filter((row): row is { title: string; agg: ByObjective } => !!row.title);

  return (
    <Card className="w-full">
      <CardHeader className="gap-2">
        <span
          aria-hidden
          className="text-2xl"
        >
          🎉
        </span>
        <CardTitle className="font-[family-name:var(--font-display)] text-2xl font-medium leading-snug">
          {headline || "Lesson complete"}
        </CardTitle>
        {total > 0 && (
          <CardDescription>
            You answered {correct} of {total} questions correctly.
          </CardDescription>
        )}
      </CardHeader>

      <CardContent className="flex flex-col gap-6">
        {/* ── Score ──────────────────────────────────────────────────────── */}
        {total > 0 && (
          <div className="flex items-center justify-between gap-4 rounded-[var(--radius)] border border-[var(--border)] bg-[var(--background)] px-5 py-4">
            <div className="flex items-baseline gap-2">
              <span className="font-[family-name:var(--font-display)] text-4xl font-semibold tabular-nums">
                {correct}
              </span>
              <span className="text-xl text-[var(--muted-foreground)]">
                / {total}
              </span>
            </div>
            <Badge variant="secondary" className="text-sm tabular-nums">
              {pct}%
            </Badge>
          </div>
        )}

        {/* ── Per-topic breakdown (only when titles resolve) ─────────────── */}
        {perTopic.length > 0 && (
          <div className="flex flex-col gap-2.5">
            <p className="text-sm font-medium text-[var(--foreground)]">
              How you did, by topic
            </p>
            <ul className="flex flex-col gap-2">
              {perTopic.map(({ title, agg }) => (
                <li
                  key={title}
                  className="flex items-center justify-between gap-3 text-sm"
                >
                  <span className="truncate text-[var(--foreground)]">
                    {title}
                  </span>
                  <Badge variant="outline" className="shrink-0 tabular-nums">
                    {agg.correct}/{agg.n} correct
                  </Badge>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* ── Study tips (plain strings → tidy list, no markdown) ─────────── */}
        {tips.length > 0 && (
          <>
            <Separator />
            <div className="flex flex-col gap-3">
              <p className="text-sm font-medium text-[var(--foreground)]">
                What to study next
              </p>
              <ul className="flex flex-col gap-3">
                {tips.map((tip, i) => (
                  <li
                    key={i}
                    className="flex items-start gap-3 rounded-[var(--radius)] border border-[var(--border)] bg-[var(--background)] px-4 py-3"
                  >
                    <span
                      aria-hidden
                      className="mt-0.5 shrink-0 text-base leading-none text-[var(--primary)]"
                    >
                      💡
                    </span>
                    <span className="text-sm leading-relaxed text-[var(--foreground)]">
                      {tip}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          </>
        )}

        {/* ── Start over ─────────────────────────────────────────────────────
            The agent's run is finished (`phase === "done"`) with the previous
            plan/objectives still in its state, so an in-place re-upload would
            skip planning (route_entry sees an existing plan). A full reload is
            the cleanest reliable reset: fresh upload screen + fresh agent
            thread. */}
        <Separator />
        <div className="flex justify-center pt-1">
          <Button
            type="button"
            size="lg"
            onClick={() => window.location.reload()}
          >
            Start a new lesson
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
