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

/** Subset of the agent's shared state this component reads (read-only). */
interface SocraticState {
  phase?: string;
  results?: Result[];
  study_tips?: string;
  summary?: string;
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

  const results = state.results ?? [];
  const total = results.length;
  const correct = results.filter((r) => r.correct).length;

  // Per-objective attempt totals (sum of attempts across that objective's qs).
  const perObjective = new Map<
    string,
    { attempts: number; correct: number; total: number }
  >();
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

  // Final study tips: prefer explicit state fields, else last assistant msg.
  const messages = (agent.messages ?? []) as MessageLike[];
  const lastAssistant = [...messages]
    .reverse()
    .find((m) => m.role === "assistant" && !!m.content);
  const studyTips =
    state.study_tips ?? state.summary ?? lastAssistant?.content ?? null;

  return (
    <Card className="my-4 w-full">
      <CardHeader>
        <CardTitle>Lesson summary</CardTitle>
        <CardDescription>
          {total > 0
            ? `You answered ${correct} of ${total} correctly.`
            : "Lesson complete."}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {total > 0 && (
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="default">
              Score: {correct}/{total}
            </Badge>
            <Badge variant="secondary">
              {Math.round((correct / total) * 100)}%
            </Badge>
          </div>
        )}

        {perObjective.size > 0 && (
          <>
            <Separator />
            <div className="flex flex-col gap-2">
              <p className="text-sm font-medium text-[var(--foreground)]">
                By objective
              </p>
              <ul className="flex flex-col gap-1.5">
                {[...perObjective.entries()].map(([objectiveId, agg]) => (
                  <li
                    key={objectiveId}
                    className="flex items-center justify-between gap-2 text-sm"
                  >
                    <span className="truncate text-[var(--muted-foreground)]">
                      {objectiveId}
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
                Study tips
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
