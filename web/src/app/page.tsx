"use client";

import { useAgent } from "@copilotkit/react-core/v2";

import { Uploader } from "@/components/Uploader";
import { usePlanApproval } from "@/components/PlanApproval";
import { useMcq } from "@/components/McqWidget";
import { Summary } from "@/components/Summary";
import { Stepper, type Step } from "@/components/Stepper";
import { LessonSettings } from "@/components/LessonSettings";
import { LessonSettingsProvider } from "@/hooks/use-lesson-settings";
import { DocumentProvider } from "@/hooks/use-document";
import { Spinner } from "@/components/ui/spinner";

/** Subset of the agent's shared state the active-step machine reads. */
interface SocraticState {
  phase?: string;
  /** All generated MCQs (set once the quiz is prepared). */
  all_mcqs?: unknown[];
  /** Index of the question currently being asked; === all_mcqs.length when the
   *  last question has been answered and the agent is summarizing. */
  current_mcq_idx?: number;
}

/**
 * Socratic — PDF → interactive Socratic lesson.
 *
 * Layout: a SINGLE centered column (~760px) presenting one step at a time —
 * a slim stepper up top for orientation, then the active step below it.
 *
 * There is NO chat surface. The lesson is driven entirely by `useAgent`
 * (kickoff + shared state) and `useInterrupt` (plan / MCQ widgets). The
 * guardrailed tutor lives inside the MCQ step as its own `/api/tutor` panel.
 *
 * `usePlanApproval` and `useMcq` register `useInterrupt({ renderInChat:false })`,
 * which RETURNS the card element (or `null` when that interrupt isn't active).
 * We place those returned elements in the active-step area below.
 */
export default function HomePage() {
  // Returned interrupt elements (non-null only while that interrupt is active).
  const planElement = usePlanApproval();
  const mcqElement = useMcq();

  const { agent } = useAgent();
  const state = agent.state as SocraticState | undefined;
  const phase = state?.phase;
  const isRunning = agent.isRunning;
  const allMcqs = state?.all_mcqs;
  const currentMcqIdx = state?.current_mcq_idx;

  // ── Active-step state machine ──────────────────────────────────────────────
  // Show EXACTLY ONE step, in priority order. An interrupt element being
  // non-null is the most reliable "active" signal, so it takes precedence over
  // the phase field (which the agent may still be catching up on).
  //
  // The Uploader is a SINGLE persistent instance rendered below (it collapses
  // to its slim file strip once a PDF is ingested), so `activeStep` here is only
  // the plan / MCQ / planning / summary widget — never the Uploader.
  let step: Step = "upload";
  let activeStep: React.ReactNode = null;

  // Phase buckets. `preparing_quiz`/`quizzing` mean the agent has approved the
  // plan and is generating ALL questions up front — there's a few-second gap
  // before the first MCQ interrupt arrives. Everything earlier (undefined,
  // `planning`, `awaiting_approval`) is the plan-building window.
  const isPreparing = phase === "preparing_quiz" || phase === "quizzing";
  // After the LAST question is answered the agent runs `summarize` (an LLM call
  // for study tips) before the Summary renders. During that window the phase is
  // `summarizing` with NO interrupt active — distinct from the pre-quiz
  // "preparing questions" window, so it gets its own calm status below.
  //
  // We don't rely on `phase === "summarizing"` alone: the phase field can lag
  // behind the resume, leaving a window where the last MCQ is answered but the
  // phase still reads `quizzing`. That window used to fall through to the
  // pre-quiz "Preparing your questions…" copy — the bug we're fixing. So we
  // ALSO treat "running, all questions answered, not yet done" as summarizing.
  const lastQuestionAnswered =
    isRunning &&
    Array.isArray(allMcqs) &&
    allMcqs.length > 0 &&
    typeof currentMcqIdx === "number" &&
    currentMcqIdx >= allMcqs.length &&
    phase !== "done";
  const isSummarizing = phase === "summarizing" || lastQuestionAnswered;
  // Planning window: the explicit planning phases, OR the brief kickoff gap
  // before the agent has reported any phase at all (phase undefined + running).
  const isPlanning =
    phase === "planning" || phase === "awaiting_approval" || phase === undefined;

  if (planElement) {
    // Plan-approval card is showing → mark the stepper's Plan step current
    // (Upload reads as completed, Plan as current).
    step = "plan";
    activeStep = planElement;
  } else if (mcqElement) {
    step = "quiz";
    activeStep = mcqElement;
  } else if (phase === "done") {
    step = "summary";
    activeStep = <Summary />;
  } else if (isSummarizing) {
    // Last question answered; the agent is generating study tips. Show a calm
    // "finishing up" state — NOT the pre-quiz "preparing questions" copy. This
    // sits ABOVE the `isPreparing` branch so the summary copy always wins.
    step = "summary";
    activeStep = <SummarizingStatus />;
  } else if (isRunning && isPlanning) {
    // Agent running with no interrupt yet, in the planning window → planning.
    step = "plan";
    activeStep = <PlanningStatus />;
  } else if (isPreparing) {
    // Plan approved; ALL questions are being generated, but no MCQ interrupt is
    // active yet. Show a calm, distinct "preparing questions" state.
    step = "quiz";
    activeStep = <PreparingQuestionsStatus />;
  }

  return (
    <LessonSettingsProvider>
      <DocumentProvider>
      <div className="min-h-full overflow-y-auto">
        <div className="mx-auto flex w-full max-w-[760px] flex-col gap-8 px-5 py-10 sm:py-14">
          {/* ── Masthead ────────────────────────────────────────────────── */}
          <header className="flex items-start justify-between gap-4">
            <div className="flex flex-col gap-1.5">
              <h1 className="font-[family-name:var(--font-display)] text-3xl font-semibold tracking-tight">
                Socratic
              </h1>
              <p className="text-sm text-[var(--muted-foreground)]">
                Turn a PDF into a guided, interactive lesson.
              </p>
            </div>
            <div className="shrink-0">
              <LessonSettings />
            </div>
          </header>

          {/* ── Orientation stepper ─────────────────────────────────────── */}
          <Stepper current={step} />

          {/* ── Uploader (persistent: drop zone → slim file strip) ──────── */}
          <Uploader />

          {/* ── Active step ─────────────────────────────────────────────── */}
          {activeStep && (
            <div key={step} className="animate-step-enter">
              {activeStep}
            </div>
          )}
        </div>
      </div>
      </DocumentProvider>
    </LessonSettingsProvider>
  );
}

/** Calm "Planning your lesson…" state shown while the agent runs with no
 *  active interrupt yet — keeps the surface clear and reassuring. */
function PlanningStatus() {
  return (
    <div className="flex flex-col items-center gap-4 rounded-[var(--radius)] border border-[var(--border)] bg-[var(--card)] px-6 py-16 text-center">
      <Spinner size="lg" />
      <div className="flex flex-col gap-1">
        <p className="font-[family-name:var(--font-display)] text-lg font-medium">
          Planning your lesson…
        </p>
        <p className="max-w-sm text-sm text-[var(--muted-foreground)]">
          Reading your document and choosing the topics to cover. This takes a
          moment.
        </p>
      </div>
    </div>
  );
}

/** Calm "Preparing your questions…" state shown after the plan is approved,
 *  while the agent generates ALL questions up front (a few seconds) before the
 *  first MCQ interrupt arrives. Distinct copy from the planning state. */
function PreparingQuestionsStatus() {
  return (
    <div className="flex flex-col items-center gap-4 rounded-[var(--radius)] border border-[var(--border)] bg-[var(--card)] px-6 py-16 text-center">
      <Spinner size="lg" />
      <div className="flex flex-col gap-1">
        <p className="font-[family-name:var(--font-display)] text-lg font-medium">
          Preparing your questions…
        </p>
        <p className="max-w-sm text-sm text-[var(--muted-foreground)]">
          Writing grounded questions for each topic. Your first one is on its
          way.
        </p>
      </div>
    </div>
  );
}

/** Calm "Finishing up…" state shown after the LAST question is answered, while
 *  the agent generates the personalized study tips that feed the Summary. Same
 *  style as the other status states; distinct copy so it never reads as the
 *  pre-quiz "Preparing your questions…" window. */
function SummarizingStatus() {
  return (
    <div className="flex flex-col items-center gap-4 rounded-[var(--radius)] border border-[var(--border)] bg-[var(--card)] px-6 py-16 text-center">
      <Spinner size="lg" />
      <div className="flex flex-col gap-1">
        <p className="font-[family-name:var(--font-display)] text-lg font-medium">
          Generating your summary and next steps…
        </p>
        <p className="max-w-sm text-sm text-[var(--muted-foreground)]">
          Reviewing how you did and writing personalized study tips. Almost
          there.
        </p>
      </div>
    </div>
  );
}
