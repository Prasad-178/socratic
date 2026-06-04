"use client";

import { useState } from "react";
import { useInterrupt } from "@copilotkit/react-core/v2";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Tutor } from "@/components/Tutor";
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
  // Progress fields carried on the MCQ interrupt payload (set by the agent).
  // We prefer THESE for the quiz header — they ship with the interrupt and so
  // never lag behind shared state the way the old state-derived values did.
  objective_title?: string;
  difficulty?: string;
  topic_number?: number;
  topic_total?: number;
  question_number?: number;
  question_total?: number;
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
 * Quiz progress header derived from the MCQ interrupt PAYLOAD.
 *
 * Shows "Topic N of M · Question N of M" plus the topic title and a difficulty
 * badge. These fields ride along with the interrupt, so (unlike the old
 * agent-state derivation) they're always in lockstep with the question shown.
 * If any field is missing it degrades gracefully (e.g. just "Question").
 */
function QuizProgress({ mcq }: { mcq: Mcq }) {
  const {
    topic_number: topicN,
    topic_total: topicTotal,
    question_number: qN,
    question_total: qTotal,
    objective_title: title,
    difficulty,
  } = mcq;

  const haveTopic =
    typeof topicN === "number" && typeof topicTotal === "number" && topicTotal > 0;
  const haveQ =
    typeof qN === "number" && typeof qTotal === "number" && qTotal > 0;

  let label: string;
  if (haveTopic && haveQ) {
    label = `Topic ${topicN} of ${topicTotal} · Question ${qN} of ${qTotal}`;
  } else if (haveQ) {
    label = `Question ${qN} of ${qTotal}`;
  } else {
    label = "Question";
  }

  return (
    <div className="flex flex-col gap-1.5">
      <p className="text-xs font-semibold uppercase tracking-wide text-[var(--muted-foreground)]">
        {label}
      </p>
      <div className="flex items-center gap-2">
        {title && (
          <p className="text-sm font-medium text-[var(--foreground)]">
            {title}
          </p>
        )}
        {difficulty && (
          <Badge variant="secondary" className="shrink-0 capitalize">
            {difficulty}
          </Badge>
        )}
      </div>
    </div>
  );
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
  // The guardrailed tutor panel is tucked away until asked for.
  const [showTutor, setShowTutor] = useState(false);

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

  return (
    <Card className="w-full">
      <CardHeader className="gap-3">
        <div className="flex items-start justify-between gap-3">
          <QuizProgress mcq={mcq} />
          {attempts > 0 && !resolved && (
            <Badge variant="outline" className="shrink-0">
              Attempt {attempts}
            </Badge>
          )}
        </div>
        <CardTitle className="font-[family-name:var(--font-display)] text-xl font-medium leading-snug">
          {mcq.question}
        </CardTitle>
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
            // Green appears ONLY on the option the learner actually chose, and
            // ONLY when that choice is the correct one. We never key the green
            // off `correct_index` directly — doing so would leak the answer on
            // a wrong submit. So both states below are anchored on the CHOSEN
            // option (`i === selectedIndex`):
            //   • chosen + correct  → green ✓
            //   • chosen + wrong    → red ✕
            // Every other (non-chosen) option stays neutral after submit.
            const isChosenCorrect =
              submitted && i === selectedIndex && isCorrect;
            const isChosenWrong =
              submitted && i === selectedIndex && isWrong;
            return (
              <Label
                key={optionId}
                htmlFor={optionId}
                className={cn(
                  "flex cursor-pointer items-center gap-3 rounded-[var(--radius)] border border-[var(--border)] p-4 text-sm transition-[color,background-color,border-color] duration-200",
                  !submitted &&
                    !resolved &&
                    "hover:border-[var(--ring)] hover:bg-[var(--secondary)]",
                  // The chosen option, when correct → green
                  isChosenCorrect &&
                    "border-green-500 bg-green-50 text-green-900 dark:bg-green-950 dark:text-green-100",
                  // The chosen option, when wrong → red (correct option is NOT
                  // revealed — it stays neutral)
                  isChosenWrong &&
                    "border-red-500 bg-red-50 text-red-900 dark:bg-red-950 dark:text-red-100",
                )}
              >
                <RadioGroupItem
                  id={optionId}
                  value={String(i)}
                  disabled={submitted || resolved}
                />
                <span className="flex-1">{option}</span>
                {isChosenCorrect && (
                  <span aria-hidden className="font-semibold text-green-600">
                    ✓
                  </span>
                )}
                {isChosenWrong && (
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
          <div className="flex animate-fade-in flex-col gap-3 rounded-[var(--radius)] border border-green-500 bg-green-50 p-4 text-sm text-green-900 dark:bg-green-950 dark:text-green-100">
            <p className="font-semibold">Correct! Here&apos;s why:</p>
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
          <div className="flex animate-fade-in flex-col gap-3 rounded-[var(--radius)] border border-red-500 bg-red-50 p-4 text-sm text-red-900 dark:bg-red-950 dark:text-red-100">
            <p className="font-semibold">Not quite — here&apos;s a hint:</p>
            {mcq.hint && (
              <p className="text-red-800 dark:text-red-200">{mcq.hint}</p>
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
            Answer saved — moving on…
          </p>
        )}

        {/* ── Guardrailed tutor (tucked away; never resolves the interrupt) ─ */}
        {!resolved && (
          <>
            <Separator />
            {showTutor ? (
              <div className="flex flex-col gap-3">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-medium text-[var(--foreground)]">
                    Ask your tutor
                  </p>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="text-[var(--muted-foreground)]"
                    onClick={() => setShowTutor(false)}
                  >
                    Hide
                  </Button>
                </div>
                <Tutor
                  question={mcq.question}
                  options={mcq.options}
                  correct_index={mcq.correct_index}
                />
              </div>
            ) : (
              <Button
                type="button"
                variant="ghost"
                className="self-start text-[var(--muted-foreground)]"
                onClick={() => setShowTutor(true)}
              >
                Stuck? Ask your tutor
              </Button>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

/**
 * Registers the MCQ interrupt handler with `renderInChat: false`, so the hook
 * RETURNS the card element (or `null` when idle) instead of publishing it into
 * a chat surface. The caller places the returned element in the lesson column.
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
