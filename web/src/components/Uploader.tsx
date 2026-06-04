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
          <Input
            ref={inputRef}
            type="file"
            accept="application/pdf,.pdf"
            className="hidden"
            onChange={onInputChange}
            disabled={isUploading}
          />

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

          {status === "ready" && result && (
            <p className="text-sm text-[var(--primary)]">
              Ingested <span className="font-medium">{result.filename}</span> —{" "}
              {result.chunks} chunks. The tutor is planning your lesson…
            </p>
          )}

          {status === "error" && error && (
            <p className="text-sm text-[var(--destructive)]">{error}</p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
