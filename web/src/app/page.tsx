"use client";

import { CopilotChat, useAgent } from "@copilotkit/react-core/v2";

import { Uploader } from "@/components/Uploader";
import { usePlanApproval } from "@/components/PlanApproval";
import { useMcq } from "@/components/McqWidget";
import { Summary } from "@/components/Summary";
import { Spinner } from "@/components/ui/spinner";

/** Subset of the agent's shared state the active-step machine reads. */
interface SocraticState {
  phase?: string;
}

/**
 * Socratic — PDF → interactive Socratic lesson.
 *
 * Layout: a wide LEFT column is the primary "lesson surface" (header, uploader,
 * and a single active-step area), and a narrower RIGHT column is the tutor chat
 * (`<CopilotChat>`). The shared AG-UI agent (keyed "default" in
 * api/copilotkit/route.ts, the Python `socratic` graph) is kicked off by the
 * Uploader once a PDF is ingested.
 *
 * The lesson widgets are NO LONGER published into the chat. `usePlanApproval`
 * and `useMcq` register `useInterrupt({ renderInChat: false })`, which RETURNS
 * the card element (or `null` when that interrupt isn't active). We place those
 * returned elements in the active-step area below — so the plan / MCQ / summary
 * live in the main panel, not as cards inside the conversation.
 */
export default function HomePage() {
  // Returned interrupt elements (non-null only while that interrupt is active).
  const planElement = usePlanApproval();
  const mcqElement = useMcq();

  const { agent } = useAgent();
  const phase = (agent.state as SocraticState | undefined)?.phase;
  const isRunning = agent.isRunning;

  // ── Active-step state machine ──────────────────────────────────────────────
  // Show EXACTLY ONE of these, in priority order:
  //   1. plan      — plan-approval interrupt active (planElement non-null)
  //   2. mcq       — MCQ interrupt active (mcqElement non-null)
  //   3. summary   — agent reports phase === "done"
  //   4. planning  — agent is running with no active interrupt yet
  //   5. (idle)    — nothing has started; the uploader drop zone is the CTA
  // An interrupt element being non-null is the most reliable "active" signal,
  // so it takes precedence over the phase field (which the agent may still be
  // catching up on).
  let activeStep: React.ReactNode = null;
  if (planElement) {
    activeStep = planElement;
  } else if (mcqElement) {
    activeStep = mcqElement;
  } else if (phase === "done") {
    activeStep = <Summary />;
  } else if (isRunning || (phase && phase !== "done")) {
    activeStep = <PlanningStatus />;
  }

  return (
    <div className="flex h-full flex-row">
      {/* ── Lesson surface (primary) ──────────────────────────────────────── */}
      <div className="flex w-3/5 flex-col gap-6 overflow-y-auto p-6 max-lg:w-full">
        <header className="flex items-baseline gap-2">
          <h1 className="text-2xl font-extrabold tracking-tight">Socratic</h1>
          <span className="text-sm text-[var(--muted-foreground)]">
            PDF → interactive lesson tutor
          </span>
        </header>

        <Uploader />

        {/* Single active-step area — always renders exactly one state once the
            lesson has started; before that, the uploader above is the CTA. */}
        {activeStep}
      </div>

      {/* ── Tutor chat ────────────────────────────────────────────────────── */}
      <div className="flex w-2/5 flex-col border-l border-[var(--border)] max-lg:hidden">
        <div className="border-b border-[var(--border)] px-4 py-3 text-sm font-medium text-[var(--muted-foreground)]">
          Tutor
        </div>
        <CopilotChat
          className="min-h-0 flex-1"
          input={{ disclaimer: () => null, className: "pb-6" }}
        />
      </div>
    </div>
  );
}

/** "Planning your lesson…" placeholder shown while the agent runs with no
 *  active interrupt — guarantees the surface is never blank/ambiguous. */
function PlanningStatus() {
  return (
    <div className="flex items-center gap-3 rounded-[var(--radius)] border border-[var(--border)] bg-[var(--card)] px-4 py-6 text-sm text-[var(--muted-foreground)]">
      <Spinner size="sm" />
      <span>Planning your lesson…</span>
    </div>
  );
}
