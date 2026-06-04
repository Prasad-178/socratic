"use client";

import { CopilotChat } from "@copilotkit/react-core/v2";

import { Uploader } from "@/components/Uploader";

/**
 * Socratic — PDF → interactive Socratic lesson.
 *
 * Layout: a left column with the uploader + lesson surface (where the 5B
 * widgets mount), and the CopilotChat on the right. The shared AG-UI agent
 * (keyed "default" in api/copilotkit/route.ts, the Python `socratic` graph)
 * is kicked off by the Uploader once a PDF is ingested.
 */
export default function HomePage() {
  // ── Phase 5B interrupt hooks mount here ──────────────────────────────────
  // The agent surfaces two interrupt types over AG-UI:
  //   { type: "plan_approval", plan: [...] }  → PlanApproval widget
  //   { type: "mcq", mcq: {...} }             → McqWidget
  // Wire them with useInterrupt from "@copilotkit/react-core/v2", e.g.:
  //
  //   const planApproval = useInterrupt({
  //     enabled: ({ value }) => value?.type === "plan_approval",
  //     render: ({ event, resolve }) => (
  //       <PlanApproval plan={event.value.plan} onResolve={resolve} />
  //     ),
  //   });
  //   const mcq = useInterrupt({
  //     enabled: ({ value }) => value?.type === "mcq",
  //     render: ({ event, resolve }) => (
  //       <McqWidget mcq={event.value.mcq} onResolve={resolve} />
  //     ),
  //   });
  //
  // (Resolve contracts — plan: { action, plan, feedback }; mcq:
  //  { chosen_index, correct, attempts }.) Left unregistered in 5A.

  return (
    <div className="flex h-full flex-row">
      {/* Lesson surface (uploader + 5B widgets) */}
      <div className="flex w-1/2 flex-col gap-6 overflow-y-auto p-6 max-lg:w-full">
        <header className="flex items-center gap-2">
          <h1 className="text-2xl font-extrabold tracking-tight">Socratic</h1>
          <span className="text-sm text-[var(--muted-foreground)]">
            PDF → interactive lesson tutor
          </span>
        </header>

        <Uploader />

        {/* ── Phase 5B widget mount points ──────────────────────────────────
            Render the interrupt elements returned by useInterrupt above, plus
            agent-state-driven panels read from `useAgent().agent.state`:
              <PlanApproval />   plan-approval interrupt UI
              <McqWidget />      MCQ interrupt UI (uses /api/tutor for hints)
              <Progress />       objectives / quiz progress from agent.state
              <Summary />        final lesson summary from agent.state
        */}
      </div>

      {/* Chat */}
      <div className="flex w-1/2 flex-col border-l border-[var(--border)] max-lg:hidden">
        <CopilotChat
          className="h-full"
          input={{ disclaimer: () => null, className: "pb-6" }}
        />
      </div>
    </div>
  );
}
