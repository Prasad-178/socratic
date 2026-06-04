"use client";

import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";

/**
 * The current question's context, passed down from the active MCQ. The tutor is
 * only meaningful during the quiz — it needs the question + options + answer
 * index so the backend guardrail can structurally prevent answer leaks.
 */
export interface TutorContext {
  question: string;
  options: string[];
  correct_index: number;
}

/** One turn in the short on-screen conversation. */
interface Turn {
  role: "you" | "tutor";
  text: string;
}

/**
 * Guardrailed Socratic tutor panel.
 *
 * POSTs to `/api/tutor` (server proxy → Python `/tutor`) with the CURRENT
 * question's context plus the learner's message. The backend never reveals the
 * correct option (structural answer-leak guard), so this surface is safe to keep
 * open during the quiz.
 *
 * It keeps a couple of turns of history on screen, an input + send, and a
 * loading state. It is intentionally self-contained — drop it under the MCQ.
 */
export function Tutor({ question, options, correct_index }: TutorContext) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const send = async () => {
    const text = message.trim();
    if (!text || loading) return;

    setMessage("");
    setError(null);
    setTurns((prev) => [...prev, { role: "you", text }]);
    setLoading(true);

    try {
      const res = await fetch("/api/tutor", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          question,
          options,
          correct_index,
          user_message: text,
        }),
      });
      if (!res.ok) throw new Error(`Tutor request failed (${res.status})`);
      const data: { reply?: string } = await res.json();
      setTurns((prev) => [
        ...prev,
        { role: "tutor", text: data.reply ?? "(no reply)" },
      ]);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not reach the tutor",
      );
    } finally {
      setLoading(false);
      // Keep the latest turn in view after the DOM updates.
      requestAnimationFrame(() => {
        scrollRef.current?.scrollTo({
          top: scrollRef.current.scrollHeight,
          behavior: "smooth",
        });
      });
    }
  };

  return (
    <div className="flex flex-col gap-3">
      {turns.length > 0 && (
        <div
          ref={scrollRef}
          className="flex max-h-64 flex-col gap-2.5 overflow-y-auto pr-1"
        >
          {turns.map((turn, i) => (
            <div
              key={i}
              className={
                turn.role === "you"
                  ? "ml-auto max-w-[85%] animate-fade-in rounded-[var(--radius)] bg-[var(--primary)] px-3.5 py-2 text-sm text-[var(--primary-foreground)]"
                  : "mr-auto max-w-[90%] animate-fade-in rounded-[var(--radius)] bg-[var(--secondary)] px-3.5 py-2 text-sm text-[var(--secondary-foreground)]"
              }
            >
              {turn.text}
            </div>
          ))}
          {loading && (
            <div className="mr-auto flex items-center gap-2 rounded-[var(--radius)] bg-[var(--secondary)] px-3.5 py-2 text-sm text-[var(--muted-foreground)]">
              <Spinner size="sm" />
              <span>Thinking…</span>
            </div>
          )}
        </div>
      )}

      <div className="flex gap-2">
        <Input
          aria-label="Ask your tutor"
          placeholder="e.g. how should I think about this?"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              void send();
            }
          }}
          disabled={loading}
        />
        <Button
          type="button"
          variant="secondary"
          onClick={() => void send()}
          disabled={loading || message.trim() === ""}
        >
          {loading ? <Spinner size="sm" /> : "Send"}
        </Button>
      </div>

      {error && <p className="text-sm text-[var(--destructive)]">{error}</p>}

      <p className="text-xs text-[var(--muted-foreground)]">
        Your tutor gives hints, never the answer.
      </p>
    </div>
  );
}
