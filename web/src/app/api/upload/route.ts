import { NextRequest, NextResponse } from "next/server";

// Server-side proxy for PDF ingestion. The browser posts the file here so we
// avoid cross-origin requests to the Python agent (uvicorn on :8123). We
// forward the raw multipart/form-data through to the agent's /upload endpoint
// and relay its JSON ({ document_id, chunks, filename }) back to the client.
const AGENT_URL = process.env.AGENT_URL || "http://localhost:8123";

export async function POST(req: NextRequest) {
  const formData = await req.formData();

  const upstream = await fetch(`${AGENT_URL}/upload`, {
    method: "POST",
    body: formData,
  });

  const text = await upstream.text();
  return new NextResponse(text, {
    status: upstream.status,
    headers: {
      "content-type":
        upstream.headers.get("content-type") || "application/json",
    },
  });
}
