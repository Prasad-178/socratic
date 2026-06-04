"use client";

import { useAgent } from "@copilotkit/react-core/v2";

import { Uploader } from "@/components/Uploader";
import { usePlanApproval } from "@/components/PlanApproval";
import { useMcq } from "@/components/McqWidget";
import { Summary } from "@/components/Summary";
import { Stepper, type Step } from "@/components/Stepper";
import { Spinner } from "@/components/ui/spinner";

/** Subset of the agent's shared state the active-step machine reads. */
interface SocraticState {
  phase?: string;
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
  const phase = (agent.state as SocraticState | undefined)?.phase;
  const isRunning = agent.isRunning;

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

  if (planElement) {
    step = "plan";
    activeStep = planElement;
  } else if (mcqElement) {
    step = "quiz";
    activeStep = mcqElement;
  } else if (phase === "done") {
    step = "summary";
    activeStep = <Summary />;
  } else if (isRunning || (phase && phase !== "done")) {
    // Agent running with no interrupt yet → planning the lesson.
    step = "plan";
    activeStep = <PlanningStatus />;
  }

  return (
    <div className="min-h-full overflow-y-auto">
      <div className="mx-auto flex w-full max-w-[760px] flex-col gap-8 px-5 py-10 sm:py-14">
        {/* ── Masthead ──────────────────────────────────────────────────── */}
        <header className="flex flex-col gap-1.5">
          <h1 className="font-[family-name:var(--font-display)] text-3xl font-semibold tracking-tight">
            Socratic
          </h1>
          <p className="text-sm text-[var(--muted-foreground)]">
            Turn a PDF into a guided, interactive lesson.
          </p>
        </header>

        {/* ── Orientation stepper ───────────────────────────────────────── */}
        <Stepper current={step} />

        {/* ── Uploader (persistent: drop zone → slim file strip) ────────── */}
        <Uploader />

        {/* ── Active step ───────────────────────────────────────────────── */}
        {activeStep && (
          <div key={step} className="animate-step-enter">
            {activeStep}
          </div>
        )}
      </div>
    </div>
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
          Reading your document and drafting the learning objectives. This takes
          a moment.
        </p>
      </div>
    </div>
  );
}
