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
import { Separator } from "@/components/ui/separator";

/** One graded answer, as recorded by the agent in `state.results`. */
interface Result {
  mcq_id: string;
  objective_id: string;
  chosen_index: number;
  correct: boolean;
  attempts: number;
}

/** One learning objective as stored in agent state. */
interface Objective {
  id: string;
  title: string;
}

/** Subset of the agent's shared state this component reads (read-only). */
interface SocraticState {
  phase?: string;
  results?: Result[];
  objectives?: Objective[];
  study_tips?: string;
  summary?: string;
  report?: {
    total: number;
    correct: number;
    by_objective: Record<string, { attempts: number; correct: number; n: number }>;
    weak_objectives: string[];
  };
}

/** Minimal shape we need off an AG-UI message for the final-tips fallback. */
interface MessageLike {
  role?: string;
  content?: string;
}

/**
 * Final lesson summary. Renders only once the agent reports `phase === "done"`.
 *
 * Score is computed from `state.results`:
 *   - total questions, number correct
 *   - per-objective attempt counts
 * Final study tips are read from `state.study_tips` / `state.summary` if
 * present, otherwise the last assistant message in `agent.messages`.
 */
export function Summary() {
  const { agent } = useAgent();
  const state = (agent.state ?? {}) as SocraticState;

  if (state.phase !== "done") return null;

  // Build a lookup from objective id → human title using agent.state.objectives.
  // Falls back to the raw id string if the objective isn't found (shouldn't
  // happen in normal flow, but keeps the component safe against missing data).
  const objectiveTitle = (id: string): string => {
    const match = (state.objectives ?? []).find((o) => o.id === id);
    return match?.title ?? id;
  };

  // Prefer the persisted report from state (set by summarize_node) so we
  // don't have to recompute from raw results client-side.
  const report = state.report;
  const results = state.results ?? [];
  const total = report?.total ?? results.length;
  const correct = report?.correct ?? results.filter((r) => r.correct).length;

  // Per-objective breakdown: use state.report.by_objective when available,
  // otherwise fall back to computing from state.results.
  const perObjective = new Map<
    string,
    { attempts: number; correct: number; total: number }
  >();
  if (report?.by_objective) {
    for (const [id, agg] of Object.entries(report.by_objective)) {
      perObjective.set(id, { attempts: agg.attempts, correct: agg.correct, total: agg.n });
    }
  } else {
    for (const r of results) {
      const entry = perObjective.get(r.objective_id) ?? {
        attempts: 0,
        correct: 0,
        total: 0,
      };
      entry.attempts += r.attempts;
      entry.correct += r.correct ? 1 : 0;
      entry.total += 1;
      perObjective.set(r.objective_id, entry);
    }
  }

  // Final study tips: prefer state.summary (plain text set by summarize_node),
  // then legacy study_tips field, then fall back to last assistant message.
  const messages = (agent.messages ?? []) as MessageLike[];
  const lastAssistant = [...messages]
    .reverse()
    .find((m) => m.role === "assistant" && !!m.content);
  const studyTips =
    state.summary ?? state.study_tips ?? lastAssistant?.content ?? null;

  const pct = total > 0 ? Math.round((correct / total) * 100) : 0;

  return (
    <Card className="w-full">
      <CardHeader>
        <CardTitle className="font-[family-name:var(--font-display)] text-2xl font-medium">
          Lesson complete 🎉
        </CardTitle>
        <CardDescription>
          {total > 0
            ? `Nice work — you got ${correct} of ${total} right.`
            : "You've reached the end of this lesson."}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        {total > 0 && (
          <div className="flex items-baseline gap-3 rounded-[var(--radius)] border border-[var(--border)] bg-[var(--background)] px-5 py-4">
            <span className="font-[family-name:var(--font-display)] text-4xl font-semibold tabular-nums">
              {pct}%
            </span>
            <span className="text-sm text-[var(--muted-foreground)]">
              {correct} of {total} correct
            </span>
          </div>
        )}

        {perObjective.size > 0 && (
          <>
            <Separator />
            <div className="flex flex-col gap-2.5">
              <p className="text-sm font-medium text-[var(--foreground)]">
                How you did, by topic
              </p>
              <ul className="flex flex-col gap-2">
                {[...perObjective.entries()].map(([objectiveId, agg]) => (
                  <li
                    key={objectiveId}
                    className="flex items-center justify-between gap-2 text-sm"
                  >
                    <span className="truncate text-[var(--foreground)]">
                      {objectiveTitle(objectiveId)}
                    </span>
                    <span className="flex shrink-0 items-center gap-2">
                      <Badge variant="outline">
                        {agg.correct}/{agg.total} correct
                      </Badge>
                      <Badge variant="secondary">
                        {agg.attempts} attempt{agg.attempts === 1 ? "" : "s"}
                      </Badge>
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          </>
        )}

        {studyTips && (
          <>
            <Separator />
            <div className="flex flex-col gap-2">
              <p className="text-sm font-medium text-[var(--foreground)]">
                What to study next
              </p>
              <p className="whitespace-pre-wrap text-sm text-[var(--muted-foreground)]">
                {studyTips}
              </p>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
