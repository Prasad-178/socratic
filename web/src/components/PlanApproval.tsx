"use client";

import { useState } from "react";
import { useInterrupt } from "@copilotkit/react-core/v2";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";

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

interface PlanApprovalPayload {
  type: "plan_approval";
  plan: Objective[];
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
 * Editable todo-list card for the plan-approval interrupt.
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
    <Card className="my-4 w-full">
      <CardHeader>
        <CardTitle>Review your lesson plan</CardTitle>
        <CardDescription>
          Edit the learning objectives below, then approve to start the quiz —
          or send feedback to regenerate the plan.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {objectives.length === 0 ? (
          <p className="text-sm text-[var(--muted-foreground)]">
            No objectives left. Add feedback and regenerate, or approve an empty
            plan.
          </p>
        ) : (
          <ul className="flex flex-col gap-3">
            {objectives.map((o, i) => (
              <li
                key={o.id}
                className="flex flex-col gap-2 rounded-[var(--radius)] border border-[var(--border)] p-3"
              >
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-[var(--muted-foreground)]">
                    {i + 1}.
                  </span>
                  <Input
                    aria-label={`Objective ${i + 1} title`}
                    value={o.title}
                    onChange={(e) => updateTitle(o.id, e.target.value)}
                    disabled={submitted}
                    className="flex-1"
                  />
                  {o.difficulty && (
                    <Badge variant={difficultyVariant(o.difficulty)}>
                      {o.difficulty}
                    </Badge>
                  )}
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    aria-label={`Remove objective ${i + 1}`}
                    onClick={() => removeObjective(o.id)}
                    disabled={submitted}
                  >
                    ✕
                  </Button>
                </div>

                {o.description && (
                  <p className="pl-6 text-sm text-[var(--muted-foreground)]">
                    {o.description}
                  </p>
                )}

                {o.key_points && o.key_points.length > 0 && (
                  <ul className="list-disc pl-10 text-sm text-[var(--muted-foreground)]">
                    {o.key_points.map((kp, kpi) => (
                      <li key={kpi}>{kp}</li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        )}

        <Separator />

        <div className="flex flex-col gap-2">
          <label
            htmlFor="plan-feedback"
            className="text-sm font-medium text-[var(--foreground)]"
          >
            Feedback (only used when regenerating)
          </label>
          <Textarea
            id="plan-feedback"
            placeholder="e.g. focus more on chapter 3, make objectives harder…"
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            disabled={submitted}
          />
        </div>

        <div className="flex flex-wrap gap-2">
          <Button type="button" onClick={approve} disabled={submitted}>
            Approve &amp; start quiz
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={regenerate}
            disabled={submitted}
          >
            Regenerate plan
          </Button>
        </div>

        {submitted && (
          <p className="text-sm text-[var(--muted-foreground)]">
            Sent to the tutor…
          </p>
        )}
      </CardContent>
    </Card>
  );
}

/**
 * Registers the plan-approval interrupt handler. Renders nothing itself — the
 * card is published into the chat surface by `useInterrupt` (renderInChat
 * default), so the agent-driven UI appears inline in the conversation.
 */
export function PlanApproval() {
  useInterrupt<never>({
    enabled: (event) =>
      (event.value as PlanApprovalPayload | undefined)?.type ===
      "plan_approval",
    render: ({ event, resolve }) => {
      const value = event.value as PlanApprovalPayload;
      return <PlanApprovalCard plan={value.plan} resolve={resolve} />;
    },
  });

  return null;
}
