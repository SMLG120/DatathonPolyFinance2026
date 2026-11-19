"use client";

import { createContext, useContext } from "react";
import type { AppMode } from "@/lib/config";
import { cn } from "@/lib/cn";
import { t } from "@/lib/i18n";

/**
 * Whether the figures on screen are recorded test data. Provided by the
 * runtime; a component rendered outside it shows no tag.
 */
const DataModeContext = createContext<AppMode>("live");

export const DataModeProvider = DataModeContext.Provider;

export function useIsTestData(): boolean {
  return useContext(DataModeContext) === "fixtures";
}

export const TEST_DATA_LABEL = "Test data";

/**
 * The marker every block of figures carries in fixtures mode, so a cropped
 * screenshot of one card still says what its numbers are. Renders nothing on
 * the live service.
 */
export function TestDataTag({ className }: { className?: string }) {
  const isTestData = useIsTestData();
  if (!isTestData) return null;
  return (
    <span
      data-testid="test-data-tag"
      className={cn(
        "inline-flex flex-none items-center rounded-md border border-dashed border-unknown bg-unknown-soft px-1.5 text-xs font-semibold uppercase leading-5 tracking-wide text-unknown",
        className,
      )}
    >
      {t(TEST_DATA_LABEL)}
    </span>
  );
}
