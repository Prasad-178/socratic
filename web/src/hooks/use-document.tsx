"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";

/**
 * Shared handle on the uploaded PDF so any step can VIEW the original document.
 *
 * The Uploader holds the actual <input type=file>; when a file is selected it
 * mints an object URL (`URL.createObjectURL(file)`) and publishes it here so the
 * collapsed file strip (and the PDF viewer modal it opens) can render the PDF —
 * on every screen, including the Summary.
 *
 * This is purely a CLIENT-side viewing convenience: it has nothing to do with
 * the agent's `document_id` / shared state, which the Uploader still seeds
 * separately at kickoff. We keep it out of `use-lesson-settings` because the
 * lifecycle (mint/revoke object URLs) is different and unrelated.
 *
 * Object URLs are revoked when replaced and on unmount to avoid blob leaks.
 */
interface DocumentValue {
  /** Object URL of the uploaded PDF, or null before any upload. */
  fileUrl: string | null;
  /** Original filename of the uploaded PDF, or null before any upload. */
  fileName: string | null;
  /** Publish a freshly selected file (mints a new object URL, revokes the old). */
  setDocument: (file: File) => void;
}

const DocumentContext = createContext<DocumentValue>({
  fileUrl: null,
  fileName: null,
  setDocument: () => {},
});

export function DocumentProvider({ children }: { children: React.ReactNode }) {
  const [fileUrl, setFileUrl] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  // Track the live object URL in a ref so the unmount cleanup always revokes
  // the latest one without re-running the effect on every change.
  const urlRef = useRef<string | null>(null);

  const setDocument = useCallback((file: File) => {
    // Revoke the previous object URL before replacing it (avoid blob leaks).
    if (urlRef.current) URL.revokeObjectURL(urlRef.current);
    const url = URL.createObjectURL(file);
    urlRef.current = url;
    setFileUrl(url);
    setFileName(file.name);
  }, []);

  // Revoke the outstanding object URL on unmount.
  useEffect(() => {
    return () => {
      if (urlRef.current) URL.revokeObjectURL(urlRef.current);
    };
  }, []);

  return (
    <DocumentContext.Provider value={{ fileUrl, fileName, setDocument }}>
      {children}
    </DocumentContext.Provider>
  );
}

export const useDocument = () => useContext(DocumentContext);
