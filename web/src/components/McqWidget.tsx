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
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Spinner } from "@/components/ui/spinner";
import { cn, parseInterruptValue } from "@/lib/utils";

export interface Mcq {
  id: string;
  objective_id: string;
  question: string;
  options: string[];
  correct_index: number;
  explanation: string;
  hint: string;
  source_pages?: number[];
}

/**
 * Reads a parsed interrupt payload (see `parseInterruptValue`) and returns the
 * `mcq` object, or `null` if this isn't an MCQ event.
 */
function readMcqPayload(raw: unknown): Mcq | null {
  const payload = parseInterruptValue(raw);
  if (!payload || payload.type !== "mcq") return null;
  const mcq = payload.mcq;
  if (mcq && typeof mcq === "object") return mcq as Mcq;
  return null;
}

/**
 * Interactive MCQ card.
 *
 * Runs its OWN retry loop and stays suspended (never calls `resolve`) until the
 * learner either gets it right, or explicitly skips. This keeps the Python
 * `interrupt()` paused — the agent only regains control on resolve.
 *
 * Resolve contract (BYTE-for-BYTE with the agent):
 *   correct   → resolve({ chosen_index, correct: true,  attempts })
 *   skip      → resolve({ chosen_index, correct: false, attempts })
 *
 * Retry: on a wrong answer we show the hint + a "Try again" button that clears
 * the submitted state WITHOUT resolving — no penalty, agent stays suspended.
 */
export function McqCard({
  mcq,
  resolve,
}: {
  mcq: Mcq;
  resolve: (response: unknown) => void;
}) {
  // The currently picked radio option (index into mcq.options), as a string so
  // it plugs straight into RadioGroup's value/onValueChange.
  const [selected, setSelected] = useState<string>("");
  // Whether the current selection has been submitted (frozen, showing result).
  const [submitted, setSubmitted] = useState(false);
  // Cumulative attempts across the retry loop (each Submit counts).
  const [attempts, setAttempts] = useState(0);
  // Set once the learner answers correctly or skips — locks the widget.
  const [resolved, setResolved] = useState(false);

  // Tutor (Socratic hint) affordance state.
  const [tutorQuestion, setTutorQuestion] = useState("");
  const [tutorReply, setTutorReply] = useState<string | null>(null);
  const [tutorLoading, setTutorLoading] = useState(false);
  const [tutorError, setTutorError] = useState<string | null>(null);

  const selectedIndex = selected === "" ? -1 : Number(selected);
  const isCorrect = submitted && selectedIndex === mcq.correct_index;
  const isWrong = submitted && selectedIndex !== mcq.correct_index;

  const onSubmit = () => {
    if (selectedIndex < 0 || resolved) return;
    setAttempts((a) => a + 1);
    setSubmitted(true);
  };

  // Re-arm after a wrong answer: clear the frozen/submitted state but KEEP the
  // attempts counter. Does not call resolve — the interrupt stays suspended.
  const onTryAgain = () => {
    setSubmitted(false);
    setSelected("");
  };

  const onContinue = () => {
    if (resolved) return;
    setResolved(true);
    resolve({ chosen_index: selectedIndex, correct: true, attempts });
  };

  const onSkip = () => {
    if (resolved) return;
    setResolved(true);
    resolve({ chosen_index: selectedIndex, correct: false, attempts });
  };

  const askTutor = async () => {
    const message = tutorQuestion.trim();
    if (!message || tutorLoading) return;
    setTutorLoading(true);
    setTutorError(null);
    setTutorReply(null);
    try {
      const res = await fetch("/api/tutor", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          question: mcq.question,
          options: mcq.options,
          correct_index: mcq.correct_index,
          user_message: message,
        }),
      });
      if (!res.ok) throw new Error(`Tutor request failed (${res.status})`);
      const data: { reply?: string } = await res.json();
      setTutorReply(data.reply ?? "(no reply)");
    } catch (err) {
      setTutorError(
        err instanceof Error ? err.message : "Could not reach the tutor",
      );
    } finally {
      setTutorLoading(false);
    }
  };

  return (
    <Card className="w-full">
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <Badge variant="secondary" className="w-fit">
            Step 2 · Quiz
          </Badge>
          {attempts > 0 && !resolved && (
            <Badge variant="outline">
              Attempt{attempts === 1 ? "" : "s"}: {attempts}
            </Badge>
          )}
        </div>
        <CardTitle className="text-lg leading-snug">{mcq.question}</CardTitle>
        <CardDescription>Pick the best answer.</CardDescription>
      </CardHeader>

      <CardContent className="flex flex-col gap-5">
        <RadioGroup
          value={selected}
          onValueChange={setSelected}
          disabled={submitted || resolved}
          className="gap-2.5"
        >
          {mcq.options.map((option, i) => {
            const optionId = `${mcq.id}-opt-${i}`;
            const isThisCorrect = submitted && i === mcq.correct_index;
            const isThisChosenWrong =
              submitted && i === selectedIndex && i !== mcq.correct_index;
            return (
              <Label
                key={optionId}
                htmlFor={optionId}
                className={cn(
                  "flex cursor-pointer items-center gap-3 rounded-[var(--radius)] border border-[var(--border)] p-3.5 text-sm transition-colors",
                  !submitted &&
                    !resolved &&
                    "hover:border-[var(--ring)] hover:bg-[var(--secondary)]",
                  // Correct option → green (shown after submit)
                  isThisCorrect &&
                    "border-green-500 bg-green-50 text-green-900 dark:bg-green-950 dark:text-green-100",
                  // The wrong option the learner chose → red
                  isThisChosenWrong &&
                    "border-red-500 bg-red-50 text-red-900 dark:bg-red-950 dark:text-red-100",
                )}
              >
                <RadioGroupItem
                  id={optionId}
                  value={String(i)}
                  disabled={submitted || resolved}
                />
                <span className="flex-1">{option}</span>
                {isThisCorrect && (
                  <span aria-hidden className="font-semibold text-green-600">
                    ✓
                  </span>
                )}
                {isThisChosenWrong && (
                  <span aria-hidden className="font-semibold text-red-600">
                    ✕
                  </span>
                )}
              </Label>
            );
          })}
        </RadioGroup>

        {/* ── Result / actions ──────────────────────────────────────────── */}
        {!submitted && !resolved && (
          <Button
            type="button"
            onClick={onSubmit}
            disabled={selectedIndex < 0}
            className="self-start"
          >
            Submit answer
          </Button>
        )}

        {isCorrect && !resolved && (
          <div className="flex flex-col gap-3 rounded-[var(--radius)] border border-green-500 bg-green-50 p-4 text-sm text-green-900 dark:bg-green-950 dark:text-green-100">
            <p className="font-semibold">Correct!</p>
            {mcq.explanation && (
              <p className="text-green-800 dark:text-green-200">
                {mcq.explanation}
              </p>
            )}
            <Button type="button" onClick={onContinue} className="self-start">
              Continue
            </Button>
          </div>
        )}

        {isWrong && !resolved && (
          <div className="flex flex-col gap-3 rounded-[var(--radius)] border border-red-500 bg-red-50 p-4 text-sm text-red-900 dark:bg-red-950 dark:text-red-100">
            <p className="font-semibold">Not quite.</p>
            {mcq.hint && (
              <p className="text-red-800 dark:text-red-200">
                <span className="font-medium">Hint:</span> {mcq.hint}
              </p>
            )}
            <div className="flex flex-wrap gap-2">
              <Button type="button" onClick={onTryAgain} className="self-start">
                Try again
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={onSkip}
                className="self-start"
              >
                Skip
              </Button>
            </div>
          </div>
        )}

        {resolved && (
          <p className="text-sm text-[var(--muted-foreground)]">
            Answer submitted — back to the tutor…
          </p>
        )}

        {/* ── Socratic tutor affordance (does NOT resolve the interrupt) ─── */}
        {!resolved && (
          <>
            <Separator />
            <div className="flex flex-col gap-2">
              <label
                htmlFor={`${mcq.id}-tutor`}
                className="text-sm font-medium text-[var(--foreground)]"
              >
                Stuck? Ask the tutor for a hint
              </label>
              <div className="flex gap-2">
                <Input
                  id={`${mcq.id}-tutor`}
                  placeholder="e.g. how should I think about this?"
                  value={tutorQuestion}
                  onChange={(e) => setTutorQuestion(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      void askTutor();
                    }
                  }}
                  disabled={tutorLoading}
                />
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => void askTutor()}
                  disabled={tutorLoading || tutorQuestion.trim() === ""}
                >
                  {tutorLoading ? <Spinner size="sm" /> : "Ask"}
                </Button>
              </div>
              {tutorReply && (
                <p className="rounded-[var(--radius)] bg-[var(--secondary)] p-3 text-sm text-[var(--secondary-foreground)]">
                  {tutorReply}
                </p>
              )}
              {tutorError && (
                <p className="text-sm text-[var(--destructive)]">
                  {tutorError}
                </p>
              )}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

/**
 * Registers the MCQ interrupt handler with `renderInChat: false`, so the hook
 * RETURNS the card element (or `null` when idle) instead of publishing it into
 * `<CopilotChat>`. The caller places the returned element in the main lesson
 * panel.
 *
 * The AG-UI bridge delivers the interrupt payload as a JSON STRING in
 * `event.value`; `readMcqPayload` (via `parseInterruptValue`) parses it before
 * reading `.type` / `.mcq` in BOTH `enabled` and `render`.
 */
export function useMcq() {
  return useInterrupt<never, false>({
    renderInChat: false,
    enabled: (event) => readMcqPayload(event.value) !== null,
    render: ({ event, resolve }) => {
      const mcq = readMcqPayload(event.value);
      // `enabled` guaranteed a match, but stay defensive.
      if (!mcq) return <></>;
      return <McqCard mcq={mcq} resolve={resolve} />;
    },
  });
}
