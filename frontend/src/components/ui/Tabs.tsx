"use client";

import * as RadixTabs from "@radix-ui/react-tabs";
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export interface TabItem {
  value: string;
  label: ReactNode;
  content: ReactNode;
}

export interface TabsProps {
  /** Accessible name of the tab list. */
  label: string;
  items: TabItem[];
  value: string;
  onValueChange: (value: string) => void;
  className?: string;
}

/**
 * Tabs on Radix Tabs: one tab stop for the list, arrow keys move between
 * tabs, Home/End jump to the ends, and each panel is linked to its tab.
 * The selected tab is marked with a heavier weight and a bar, not colour alone.
 */
export function Tabs({ label, items, value, onValueChange, className }: TabsProps) {
  return (
    <RadixTabs.Root value={value} onValueChange={onValueChange} className={className}>
      <RadixTabs.List aria-label={label} className="flex flex-col gap-1 border-b border-line-strong sm:flex-row sm:gap-0">
        {items.map((item) => (
          <RadixTabs.Trigger
            key={item.value}
            value={item.value}
            className={cn(
              "min-h-11 border-l-4 border-transparent px-4 py-2 text-left font-semibold text-ink-muted hover:bg-sunken hover:text-ink",
              "sm:-mb-px sm:border-b-4 sm:border-l-0",
              "data-[state=active]:border-accent data-[state=active]:bg-accent-soft data-[state=active]:text-accent-strong",
            )}
          >
            {item.label}
          </RadixTabs.Trigger>
        ))}
      </RadixTabs.List>
      {items.map((item) => (
        <RadixTabs.Content key={item.value} value={item.value} className="pt-5 focus-visible:outline-offset-4">
          {item.content}
        </RadixTabs.Content>
      ))}
    </RadixTabs.Root>
  );
}
