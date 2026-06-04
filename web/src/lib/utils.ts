import { clsx } from "clsx";
import type { ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Parse the `value` of an AG-UI interrupt (CUSTOM) event.
 *
 * The `ag-ui-langgraph` bridge emits the LangGraph `interrupt(...)` payload as a
 * CUSTOM event whose `value` is a **JSON STRING**, e.g.
 *   `'{"type":"plan_approval","plan":[ ... ]}'`
 * If we read `.type` straight off that string it is `undefined`, the interrupt
 * never matches `enabled`, and the card never renders. So parse the string here
 * before reading it. The bridge may also (in other transports) hand us the
 * already-parsed object, so accept that too.
 *
 * Defensive: returns `null` when `value` is a malformed JSON string or anything
 * that isn't an object — callers treat `null` as "not my interrupt".
 */
export function parseInterruptValue(raw: unknown): Record<string, unknown> | null {
  let payload: unknown = raw;
  if (typeof raw === "string") {
    try {
      payload = JSON.parse(raw);
    } catch {
      return null;
    }
  }
  if (payload && typeof payload === "object") {
    return payload as Record<string, unknown>;
  }
  return null;
}
