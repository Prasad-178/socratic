import {
  CopilotRuntime,
  createCopilotEndpoint,
  InMemoryAgentRunner,
} from "@copilotkit/runtime/v2";
import { handle } from "hono/vercel";
import { LangGraphHttpAgent } from "@copilotkit/runtime/langgraph";

// FastAPI-specific: the agent runs under uvicorn + ag-ui-langgraph, which
// speaks AG-UI directly. We talk to it via HttpAgent, not LangGraphAgent
// (LangGraphAgent targets the LangGraph Platform / langgraph-cli dev
// surface, which is a different protocol).
//
// We deliberately keep this runtime MINIMAL. The agent uses function-calling
// for its structured plan/MCQ generation; with `openGenerativeUI` on, those
// internal tool calls render as raw JSON accordion cards in the chat. We don't
// use a chat surface at all (the lesson is driven by `useInterrupt` widgets and
// a dedicated `/api/tutor` panel), so we disable generative UI and drop the
// leftover example MCP app (excalidraw) and a2ui wiring entirely.
const defaultAgent = new LangGraphHttpAgent({
  url: `${process.env.AGENT_URL || "http://localhost:8123"}/`,
});

const runtime = new CopilotRuntime({
  agents: { default: defaultAgent },
  runner: new InMemoryAgentRunner(),
  openGenerativeUI: false,
});

const app = createCopilotEndpoint({
  runtime,
  basePath: "/api/copilotkit",
});

export const GET = handle(app);
export const POST = handle(app);
