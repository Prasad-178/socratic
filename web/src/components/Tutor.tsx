"use client";

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { Markdown } from "@/components/Markdown";

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
  /** Tutor turns reveal progressively (FIX 5). While `streaming` is true only
   *  `revealed` words of `text` are shown; once done it equals the full text. */
  streaming?: boolean;
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
export function Tutor({
  question,
  options,
  correct_index,
  onAsk,
}: TutorContext & {
  /** Called with the learner's message text whenever they send a tutor
   *  message — lets the parent (McqWidget) record `tutor_questions`. */
  onAsk?: (question: string) => void;
}) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // ── Typewriter reveal (FIX 5) ──────────────────────────────────────────────
  // The backend returns the FULL reply (it must run an answer-leak guard before
  // anything is shown, so true token-streaming isn't safe). We reveal it
  // client-side, WORD BY WORD, through <Markdown> so bold/lists resolve cleanly
  // as partial text becomes valid markdown. We track the streaming turn's index
  // + how many words are revealed; an interval bumps the count on a brisk tick.
  const [streamIdx, setStreamIdx] = useState<number | null>(null);
  const [revealCount, setRevealCount] = useState(0);
  const fullTextRef = useRef<string>("");
  const wordsRef = useRef<string[]>([]);

  useEffect(() => {
    if (streamIdx === null) return;
    const words = wordsRef.current;
    if (revealCount >= words.length) {
      // Fully revealed: drop the streaming flag so the final markdown is the
      // canonical text and the bubble is no longer "in progress".
      setTurns((prev) =>
        prev.map((t, i) =>
          i === streamIdx
            ? { ...t, text: fullTextRef.current, streaming: false }
            : t,
        ),
      );
      setStreamIdx(null);
      return;
    }
    // Reveal a small chunk (2 words) per tick at a brisk pace — short replies
    // finish in well under a second while still reading as a typewriter.
    const id = window.setTimeout(() => {
      const next = Math.min(revealCount + 2, words.length);
      const partial = words.slice(0, next).join(" ");
      setTurns((prev) =>
        prev.map((t, i) =>
          i === streamIdx ? { ...t, text: partial } : t,
        ),
      );
      setRevealCount(next);
      // Keep the newest words in view as they stream.
      requestAnimationFrame(() => {
        scrollRef.current?.scrollTo({
          top: scrollRef.current.scrollHeight,
          behavior: "smooth",
        });
      });
    }, 40);
    return () => window.clearTimeout(id);
  }, [streamIdx, revealCount]);

  // True while a request is in flight OR a reply is still revealing. The input
  // is locked in both windows so a new message can't clobber the active reveal.
  const busy = loading || streamIdx !== null;

  const send = async () => {
    const text = message.trim();
    if (!text || busy) return;

    // FIX 4: surface the learner's question to the parent so it can be recorded
    // in the MCQ resolve payload as `tutor_questions`.
    onAsk?.(text);

    // Capture the conversation so far (before adding this turn) so the tutor
    // builds on it instead of repeating itself.
    const history = turns.map((t) => ({
      role: t.role === "you" ? "user" : "tutor",
      content: t.text,
    }));

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
          history,
        }),
      });
      if (!res.ok) throw new Error(`Tutor request failed (${res.status})`);
      const data: { reply?: string } = await res.json();
      const reply = data.reply ?? "(no reply)";

      // Begin the typewriter reveal: push an empty streaming tutor turn, then
      // let the effect above reveal it word-by-word. We compute the new turn's
      // index from the current length so the interval targets the right bubble.
      fullTextRef.current = reply;
      // Split on whitespace runs; keeping word boundaries means partial markdown
      // (e.g. an unclosed `**`) resolves within a word or two.
      wordsRef.current = reply.split(/\s+/).filter(Boolean);
      setTurns((prev) => {
        setStreamIdx(prev.length);
        return [...prev, { role: "tutor", text: "", streaming: true }];
      });
      setRevealCount(0);
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
          {turns.map((turn, i) => {
            // Don't render the streaming tutor bubble until its first chunk
            // appears — the "Thinking…" spinner below covers that gap so the
            // reveal starts only once there's text to show.
            if (turn.role === "tutor" && turn.streaming && turn.text === "") {
              return null;
            }
            return (
              <div
                key={i}
                className={
                  turn.role === "you"
                    ? "ml-auto max-w-[85%] animate-fade-in rounded-[var(--radius)] bg-[var(--primary)] px-3.5 py-2 text-sm text-[var(--primary-foreground)]"
                    : "mr-auto max-w-[90%] animate-fade-in rounded-[var(--radius)] bg-[var(--secondary)] px-3.5 py-2 text-sm text-[var(--secondary-foreground)]"
                }
              >
                {/* User messages stay plain; the tutor reply is LLM-generated
                    markdown (bold, numbered steps) and is rendered as such —
                    including during the progressive reveal, so partial markdown
                    formats correctly step by step. */}
                {turn.role === "tutor" ? (
                  <Markdown>{turn.text}</Markdown>
                ) : (
                  turn.text
                )}
              </div>
            );
          })}
          {/* Spinner persists until the first revealed chunk: while the request
              is in flight (`loading`), AND while the streaming turn is still
              empty (the request resolved but no word has been revealed yet). */}
          {(loading ||
            (turns[turns.length - 1]?.streaming === true &&
              turns[turns.length - 1]?.text === "")) && (
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
          disabled={busy}
        />
        <Button
          type="button"
          variant="secondary"
          onClick={() => void send()}
          disabled={busy || message.trim() === ""}
        >
          {busy ? <Spinner size="sm" /> : "Send"}
        </Button>
      </div>

      {error && <p className="text-sm text-[var(--destructive)]">{error}</p>}

      <p className="text-xs text-[var(--muted-foreground)]">
        Your tutor gives hints, never the answer.
      </p>
    </div>
  );
}
