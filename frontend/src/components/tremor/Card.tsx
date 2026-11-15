// Adapted from Tremor Card v1.0.0 (Apache-2.0; see licenses/tremor.txt).
// Application palette replaces upstream colors; asChild preserves landmarks.
import { forwardRef, type ComponentPropsWithoutRef } from "react";
import { Slot } from "@radix-ui/react-slot";
import { cn } from "@/lib/cn";

export interface CardProps extends ComponentPropsWithoutRef<"div"> { asChild?: boolean }
export const Card = forwardRef<HTMLDivElement, CardProps>(
  ({ className, asChild, ...props }, ref) => {
    const Component = asChild ? Slot : "div";
    return <Component ref={ref} data-tremor="card" className={cn("relative w-full rounded-lg border border-line bg-surface p-6 text-left shadow-xs", className)} {...props} />;
  },
);
Card.displayName = "Card";
