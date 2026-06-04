import { NextRequest, NextResponse } from "next/server";

// Server-side proxy for the Socratic tutor hint endpoint. Used by the MCQ
// widget (Phase 5B) to request a guardrailed hint without leaking the answer.
// Forwards the JSON body to the Python agent's /tutor endpoint and relays the
// JSON ({ reply }) back to the client (avoids browser CORS to :8123).
const AGENT_URL = process.env.AGENT_URL || "http://localhost:8123";

export async function POST(req: NextRequest) {
  const body = await req.text();

  const upstream = await fetch(`${AGENT_URL}/tutor`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body,
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
