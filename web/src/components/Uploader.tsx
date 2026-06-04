"use client";

import { useCallback, useRef, useState } from "react";
import { useAgent, useAgentContext } from "@copilotkit/react-core/v2";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { Badge } from "@/components/ui/badge";

interface UploadResult {
  document_id: string;
  chunks: number;
  filename: string;
}

type Status = "idle" | "uploading" | "ready" | "error";

/**
 * PDF uploader + agent kickoff.
 *
 * Flow:
 *   1. User selects a PDF → POST /api/upload (server-side proxy to the Python
 *      agent's /upload). Response carries { document_id, chunks, filename }.
 *   2. On success we seed the shared AG-UI agent state with `document_id` and
 *      start a run. The graph's entry expects `document_id` and then runs the
 *      plan map-reduce, eventually surfacing a `plan_approval` interrupt
 *      (handled by the Phase 5B PlanApproval widget).
 *
 * Mirrors the example's shared-state pattern (example-canvas / headless-chat):
 *   const { agent } = useAgent();   // default agent, keyed "default" in route
 *   agent.setState({ ... });        // push shared state to the agent
 *   agent.runAgent();               // start a run (AG-UI over HTTP)
 */
export function Uploader() {
  // useAgent() with no agentId resolves to the default agent (keyed "default"
  // in api/copilotkit route.ts), exactly like the example's ExampleCanvas.
  const { agent } = useAgent();

  const [status, setStatus] = useState<Status>("idle");
  const [result, setResult] = useState<UploadResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Expose the uploaded document as readable context for the agent (one-way).
  useAgentContext({
    description: "The uploaded study document",
    value: { document_id: result?.document_id ?? null },
  });

  const handleFile = useCallback(
    async (file: File) => {
      setStatus("uploading");
      setError(null);
      setResult(null);

      try {
        const formData = new FormData();
        formData.append("file", file);

        const res = await fetch("/api/upload", {
          method: "POST",
          body: formData,
        });

        if (!res.ok) {
          throw new Error(`Upload failed (${res.status})`);
        }

        const data: UploadResult = await res.json();
        setResult(data);
        setStatus("ready");

        // Kick off the agent: seed shared state with document_id and run.
        // The graph plans over the document and then emits a plan_approval
        // interrupt (resolved by the 5B PlanApproval widget via useInterrupt).
        // NOTE: agent.setState({ document_id }) is the load-bearing call that
        // seeds the LangGraph graph state (read by plan_node / route_entry).
        // useAgentContext above is supplementary LLM-visible context only —
        // do NOT remove setState thinking it's redundant.
        agent.setState({ document_id: data.document_id });
        agent.runAgent();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Upload failed");
        setStatus("error");
      }
    },
    [agent],
  );

  const onInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) void handleFile(file);
    },
    [handleFile],
  );

  const onDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      const file = e.dataTransfer.files?.[0];
      if (file && file.type === "application/pdf") void handleFile(file);
    },
    [handleFile],
  );

  const isUploading = status === "uploading";

  // Hidden file input shared by both the full drop zone and the collapsed
  // "Change" affordance. Always mounted so `inputRef.current?.click()` works.
  const fileInput = (
    <Input
      ref={inputRef}
      type="file"
      accept="application/pdf,.pdf"
      className="hidden"
      onChange={onInputChange}
      disabled={isUploading}
    />
  );

  // ── Collapsed state ──────────────────────────────────────────────────────
  // Once a PDF is ingested, shrink the big drop zone to a slim strip so the
  // lesson surface below takes focus. "Change" re-opens the picker (a new
  // upload re-kicks the agent via handleFile).
  if (status === "ready" && result) {
    return (
      <div className="flex items-center gap-3 rounded-[var(--radius)] border border-[var(--border)] bg-[var(--card)] px-3.5 py-2.5 text-sm">
        {fileInput}
        <span aria-hidden className="text-base">
          📄
        </span>
        <span className="truncate font-medium text-[var(--foreground)]">
          {result.filename}
        </span>
        <Badge variant="secondary" className="shrink-0">
          {result.chunks} chunks
        </Badge>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="ml-auto shrink-0 text-[var(--muted-foreground)]"
          onClick={() => inputRef.current?.click()}
        >
          Change
        </Button>
      </div>
    );
  }

  return (
    <Card className="w-full">
      <CardHeader>
        <CardTitle>Upload a study document</CardTitle>
        <CardDescription>
          Drop a PDF to start an interactive Socratic lesson.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div
          onDrop={onDrop}
          onDragOver={(e) => e.preventDefault()}
          className="flex flex-col items-center justify-center gap-3 rounded-[var(--radius)] border border-dashed border-[var(--border)] bg-[var(--background)] px-6 py-10 text-center"
        >
          {fileInput}

          {isUploading ? (
            <div className="flex items-center gap-2 text-sm text-[var(--muted-foreground)]">
              <Spinner size="sm" />
              <span>Ingesting PDF…</span>
            </div>
          ) : (
            <>
              <p className="text-sm text-[var(--muted-foreground)]">
                Drag &amp; drop a PDF here, or
              </p>
              <Button
                type="button"
                onClick={() => inputRef.current?.click()}
                disabled={isUploading}
              >
                Choose PDF
              </Button>
            </>
          )}

          {status === "error" && error && (
            <p className="text-sm text-[var(--destructive)]">{error}</p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
