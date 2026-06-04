"use client";

import { CopilotChat } from "@copilotkit/react-core/v2";

import { Uploader } from "@/components/Uploader";
import { PlanApproval } from "@/components/PlanApproval";
import { McqWidget } from "@/components/McqWidget";
import { Progress } from "@/components/Progress";
import { Summary } from "@/components/Summary";

/**
 * Socratic — PDF → interactive Socratic lesson.
 *
 * Layout: a left column with the uploader + lesson surface (where the 5B
 * widgets mount), and the CopilotChat on the right. The shared AG-UI agent
 * (keyed "default" in api/copilotkit/route.ts, the Python `socratic` graph)
 * is kicked off by the Uploader once a PDF is ingested.
 */
export default function HomePage() {
  // ── Phase 5B interrupt hooks ─────────────────────────────────────────────
  // PlanApproval and McqWidget register `useInterrupt` handlers (and render
  // null); the interrupt cards they return are published into <CopilotChat>
  // by CopilotKit (renderInChat default). The agent surfaces two interrupt
  // types over AG-UI — { type: "plan_approval", plan } and { type: "mcq", mcq }
  // — resolved with { action, plan, feedback } and
  // { chosen_index, correct, attempts } respectively. Progress and Summary read
  // agent.state (read-only) and render in the lesson surface below.

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

        {/* ── Phase 5B widgets ──────────────────────────────────────────────
            PlanApproval / McqWidget register useInterrupt handlers (render
            null; their cards appear inline in the chat). Progress / Summary
            are agent-state-driven panels rendered in this lesson surface. */}
        <PlanApproval />
        <McqWidget />
        <Progress />
        <Summary />
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
