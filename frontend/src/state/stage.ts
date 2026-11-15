"use client";

import { useSyncExternalStore } from "react";

/**
 * The six stages of the one workflow, in order. `short` is shown where space is
 * tight and is always a word taken from `title`, so the visible label is part
 * of the link's accessible name (WCAG 2.5.3 Label in Name).
 */
export const STAGES = [
  { id: "persona", number: 1, title: "Persona & portfolio", short: "Persona" },
  { id: "goals", number: 2, title: "Goals & rules", short: "Rules" },
  { id: "purchase", number: 3, title: "Proposed purchase", short: "Purchase" },
  { id: "investigation", number: 4, title: "Investigation steps", short: "Steps" },
  { id: "verdict", number: 5, title: "Verdict & evidence", short: "Verdict" },
  { id: "challenge", number: 6, title: "Challenge", short: "Challenge" },
] as const;

export type StageId = (typeof STAGES)[number]["id"];
export type Stage = (typeof STAGES)[number];

export const FIRST_STAGE: StageId = "persona";

export function isStageId(value: string): value is StageId {
  return STAGES.some((stage) => stage.id === value);
}

export function stageById(id: StageId): Stage {
  return STAGES.find((stage) => stage.id === id) ?? STAGES[0];
}

const STAGE_LIST: readonly Stage[] = STAGES;

export function nextStage(id: StageId): Stage | null {
  return STAGE_LIST[stageById(id).number] ?? null;
}

export function previousStage(id: StageId): Stage | null {
  return STAGE_LIST[stageById(id).number - 2] ?? null;
}

/**
 * The stage lives in the URL hash (`#/verdict`), so the browser's Back and
 * Forward buttons move between stages and a stage can be linked, while the
 * app stays one static page whose in-memory state survives every stage change.
 */
export function stageHref(id: StageId): string {
  return `#/${id}`;
}

/** A hash that is not a stage (or no hash) keeps the stage we were on. */
let lastStage: StageId = FIRST_STAGE;

function readStage(): StageId {
  const hash = window.location.hash;
  if (hash === "" || hash === "#") {
    lastStage = FIRST_STAGE;
    return lastStage;
  }
  const candidate = hash.startsWith("#/") ? hash.slice(2) : "";
  if (isStageId(candidate)) lastStage = candidate;
  return lastStage;
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener("hashchange", onChange);
  window.addEventListener("popstate", onChange);
  return () => {
    window.removeEventListener("hashchange", onChange);
    window.removeEventListener("popstate", onChange);
  };
}

export function useStage(): StageId {
  return useSyncExternalStore(subscribe, readStage, () => FIRST_STAGE);
}

export function goToStage(id: StageId): void {
  if (window.location.hash === stageHref(id)) return;
  window.location.hash = stageHref(id);
}
