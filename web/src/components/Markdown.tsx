import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/utils";

/**
 * Thin, dark-theme-aware wrapper around `react-markdown` for the SHORT,
 * LLM-generated bodies in this app (tutor replies, MCQ explanation/hint).
 *
 * These are conversational replies, not documents — so the element overrides
 * stay compact and inherit the surrounding small text size. We hand-style the
 * handful of elements the model actually emits (paragraphs, bold, lists, links,
 * inline code, tiny headings) via the existing CSS-variable tokens + Tailwind,
 * rather than pulling in `@tailwindcss/typography`.
 *
 * `remark-gfm` is enabled so `1. 2. 3.` ordered lists, `-` bullet lists, and
 * `**bold**` render as real markup instead of literal characters.
 */

const components: Components = {
  // Paragraphs: small, tight vertical rhythm so multi-paragraph replies don't
  // balloon the bubble.
  p: ({ children }) => <p className="my-1 first:mt-0 last:mb-0">{children}</p>,
  strong: ({ children }) => (
    <strong className="font-semibold">{children}</strong>
  ),
  em: ({ children }) => <em className="italic">{children}</em>,
  ol: ({ children }) => (
    <ol className="my-1 list-decimal space-y-1 pl-5">{children}</ol>
  ),
  ul: ({ children }) => (
    <ul className="my-1 list-disc space-y-1 pl-5">{children}</ul>
  ),
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="text-[var(--ring)] underline underline-offset-2 hover:opacity-80"
    >
      {children}
    </a>
  ),
  // Inline code (block code is unlikely in these short replies, but the same
  // treatment reads fine for either).
  code: ({ children }) => (
    <code className="rounded bg-[var(--muted)] px-1 py-0.5 font-[family-name:var(--font-code)] text-[0.85em]">
      {children}
    </code>
  ),
  // Headings: these are short replies, not documents — render only slightly
  // larger than body and semibold so an stray `#` doesn't blow out the layout.
  h1: ({ children }) => (
    <h1 className="my-1 text-[1.05em] font-semibold">{children}</h1>
  ),
  h2: ({ children }) => (
    <h2 className="my-1 text-[1.05em] font-semibold">{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 className="my-1 text-[1em] font-semibold">{children}</h3>
  ),
};

export function Markdown({
  children,
  className,
}: {
  children: string;
  className?: string;
}) {
  return (
    // Keep the font size consistent with the surrounding small text; the
    // overrides above tune only spacing/weight, not the base size.
    <div className={cn("text-sm [&>:first-child]:mt-0 [&>:last-child]:mb-0", className)}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {children}
      </ReactMarkdown>
    </div>
  );
}
