"use client";

import { useState } from "react";
import { useInterrupt } from "@copilotkit/react-core/v2";

import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { parseInterruptValue } from "@/lib/utils";

/**
 * One learning objective in the proposed lesson plan.
 *
 * The full dict shape is preserved round-trip so the agent receives back the
 * same objective objects it sent (with only `title` possibly edited and rows
 * possibly removed). Unknown/extra keys are carried through via the index
 * signature so we never drop fields the backend cares about.
 */
export interface Objective {
  id: string;
  title: string;
  description?: string;
  difficulty?: string;
  key_points?: string[];
  status?: string;
  [key: string]: unknown;
}

/**
 * Reads a parsed interrupt payload (see `parseInterruptValue`) and returns the
 * `plan_approval` objectives, or `null` if this isn't a plan-approval event.
 */
function readPlanPayload(raw: unknown): Objective[] | null {
  const payload = parseInterruptValue(raw);
  if (!payload || payload.type !== "plan_approval") return null;
  const plan = payload.plan;
  return Array.isArray(plan) ? (plan as Objective[]) : [];
}

const difficultyVariant = (
  difficulty?: string,
): "default" | "secondary" | "outline" => {
  switch ((difficulty ?? "").toLowerCase()) {
    case "hard":
    case "advanced":
      return "default";
    case "easy":
    case "beginner":
      return "outline";
    default:
      return "secondary";
  }
};

/**
 * Editable plan-approval card for the plan-approval interrupt.
 *
 * Resolve contract (BYTE-for-BYTE with the agent):
 *   approve     → resolve({ action: "approve",    plan: <edited objectives> })
 *   regenerate  → resolve({ action: "regenerate", plan: <edited objectives>,
 *                           feedback: <text> })
 */
export function PlanApprovalCard({
  plan,
  resolve,
}: {
  plan: Objective[];
  resolve: (response: unknown) => void;
}) {
  const [objectives, setObjectives] = useState<Objective[]>(() =>
    (plan ?? []).map((o) => ({ ...o })),
  );
  const [feedback, setFeedback] = useState("");
  const [showFeedback, setShowFeedback] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const updateTitle = (id: string, title: string) => {
    setObjectives((prev) =>
      prev.map((o) => (o.id === id ? { ...o, title } : o)),
    );
  };

  const removeObjective = (id: string) => {
    setObjectives((prev) => prev.filter((o) => o.id !== id));
  };

  const approve = () => {
    setSubmitted(true);
    resolve({ action: "approve", plan: objectives });
  };

  const regenerate = () => {
    setSubmitted(true);
    resolve({ action: "regenerate", plan: objectives, feedback });
  };

  return (
    <Card className="w-full">
      <CardHeader>
        <CardTitle className="font-[family-name:var(--font-display)] text-2xl font-medium">
          Your lesson plan
        </CardTitle>
        <CardDescription>
          Here&apos;s what we&apos;ll cover. Rename or remove anything, then
          start the quiz.
        </CardDescription>
      </CardHeader>

      <CardContent className="flex flex-col gap-5">
        {objectives.length === 0 ? (
          <p className="rounded-[var(--radius)] border border-dashed border-[var(--border)] p-4 text-sm text-[var(--muted-foreground)]">
            No topics left. Add a note below and regenerate, or approve an empty
            plan.
          </p>
        ) : (
          <ol className="flex flex-col gap-3">
            {objectives.map((o, i) => (
              <li
                key={o.id}
                style={{ "--stagger-index": i } as React.CSSProperties}
                className="flex animate-card-enter flex-col gap-3 rounded-[var(--radius)] border border-[var(--border)] bg-[var(--card)] p-4"
              >
                <div className="flex items-start gap-3">
                  <span className="mt-2 flex size-6 shrink-0 items-center justify-center rounded-full bg-[var(--primary)] text-xs font-semibold text-[var(--primary-foreground)]">
                    {i + 1}
                  </span>
                  <Input
                    aria-label={`Topic ${i + 1} title`}
                    value={o.title}
                    onChange={(e) => updateTitle(o.id, e.target.value)}
                    disabled={submitted}
                    className="flex-1 font-medium"
                  />
                  {o.difficulty && (
                    <Badge
                      variant={difficultyVariant(o.difficulty)}
                      className="mt-1 shrink-0 capitalize"
                    >
                      {o.difficulty}
                    </Badge>
                  )}
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    aria-label={`Remove topic ${i + 1}`}
                    onClick={() => removeObjective(o.id)}
                    disabled={submitted}
                    className="mt-0.5 shrink-0 text-[var(--muted-foreground)] hover:text-[var(--destructive)]"
                  >
                    ✕
                  </Button>
                </div>

                {o.description && (
                  <p className="pl-9 text-sm text-[var(--muted-foreground)]">
                    {o.description}
                  </p>
                )}

                {o.key_points && o.key_points.length > 0 && (
                  <div className="flex flex-col gap-1.5 pl-9">
                    <p className="text-xs font-semibold uppercase tracking-wide text-[var(--muted-foreground)]">
                      What you&apos;ll learn
                    </p>
                    <ul className="flex flex-col gap-1">
                      {o.key_points.map((kp, kpi) => (
                        <li
                          key={kpi}
                          className="flex gap-2 text-sm text-[var(--muted-foreground)]"
                        >
                          <span
                            aria-hidden
                            className="select-none text-[var(--muted-foreground)]"
                          >
                            •
                          </span>
                          <span>{kp}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </li>
            ))}
          </ol>
        )}

        {/* Regenerate feedback is tucked away — only shown on request. */}
        {showFeedback && (
          <div className="flex animate-fade-in flex-col gap-2">
            <Separator />
            <label
              htmlFor="plan-feedback"
              className="text-sm font-medium text-[var(--foreground)]"
            >
              What should change?{" "}
              <span className="font-normal text-[var(--muted-foreground)]">
                (used when you regenerate)
              </span>
            </label>
            <Textarea
              id="plan-feedback"
              placeholder="e.g. focus more on chapter 3, make it harder…"
              value={feedback}
              onChange={(e) => setFeedback(e.target.value)}
              disabled={submitted}
            />
          </div>
        )}
      </CardContent>

      <CardFooter className="flex flex-col items-stretch gap-2 sm:flex-row sm:items-center">
        <Button
          type="button"
          onClick={approve}
          disabled={submitted}
          className="sm:flex-1"
        >
          Approve &amp; start quiz
        </Button>
        {showFeedback ? (
          <Button
            type="button"
            variant="outline"
            onClick={regenerate}
            disabled={submitted}
          >
            Regenerate
          </Button>
        ) : (
          <Button
            type="button"
            variant="ghost"
            onClick={() => setShowFeedback(true)}
            disabled={submitted}
            className="text-[var(--muted-foreground)]"
          >
            Regenerate instead
          </Button>
        )}
        {submitted && (
          <span className="text-sm text-[var(--muted-foreground)] sm:ml-2">
            Working on it…
          </span>
        )}
      </CardFooter>
    </Card>
  );
}

/**
 * Registers the plan-approval interrupt handler with `renderInChat: false`, so
 * the hook RETURNS the card element (or `null` when idle) instead of publishing
 * it into a chat surface. The caller places the returned element in the lesson
 * column.
 *
 * The AG-UI bridge delivers the interrupt payload as a JSON STRING in
 * `event.value`; `readPlanPayload` (via `parseInterruptValue`) parses it before
 * reading `.type` / `.plan` in BOTH `enabled` and `render`.
 */
export function usePlanApproval() {
  return useInterrupt<never, false>({
    renderInChat: false,
    enabled: (event) => readPlanPayload(event.value) !== null,
    render: ({ event, resolve }) => {
      const plan = readPlanPayload(event.value) ?? [];
      return <PlanApprovalCard plan={plan} resolve={resolve} />;
    },
  });
}
