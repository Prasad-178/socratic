"use client";

import { createContext, useContext, useState } from "react";

/**
 * User-tunable lesson settings, surfaced in the "Lesson settings" modal and
 * read by the Uploader at kickoff. These map (snake_cased) to the agent's
 * kickoff state:
 *   questionsPerObjective → questions_per_objective (default 2)
 *   maxObjectives         → max_objectives          (default 6)
 *
 * Defaults MUST match the agent's defaults so an untouched lesson behaves
 * exactly as before. Changing a value only affects the NEXT lesson run.
 */
interface LessonSettings {
  questionsPerObjective: number;
  maxObjectives: number;
  setQuestionsPerObjective: (n: number) => void;
  setMaxObjectives: (n: number) => void;
}

const DEFAULT_QUESTIONS_PER_OBJECTIVE = 2;
const DEFAULT_MAX_OBJECTIVES = 6;

const LessonSettingsContext = createContext<LessonSettings>({
  questionsPerObjective: DEFAULT_QUESTIONS_PER_OBJECTIVE,
  maxObjectives: DEFAULT_MAX_OBJECTIVES,
  setQuestionsPerObjective: () => {},
  setMaxObjectives: () => {},
});

export function LessonSettingsProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const [questionsPerObjective, setQuestionsPerObjective] = useState(
    DEFAULT_QUESTIONS_PER_OBJECTIVE,
  );
  const [maxObjectives, setMaxObjectives] = useState(DEFAULT_MAX_OBJECTIVES);

  return (
    <LessonSettingsContext.Provider
      value={{
        questionsPerObjective,
        maxObjectives,
        setQuestionsPerObjective,
        setMaxObjectives,
      }}
    >
      {children}
    </LessonSettingsContext.Provider>
  );
}

export const useLessonSettings = () => useContext(LessonSettingsContext);
