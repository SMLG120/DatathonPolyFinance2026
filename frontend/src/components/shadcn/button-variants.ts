// Adapted from shadcn/ui button (MIT; see licenses/shadcn-ui.txt).
// Keep the application's public variants, touch targets and contrast tokens.
import { cva } from "class-variance-authority";

export const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 rounded-lg font-medium text-left transition-colors shadow-xs focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:pointer-events-none [&_svg]:pointer-events-none [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primary: "bg-[linear-gradient(135deg,#2f5bdb_0%,#4f46e5_45%,#7c3aed_100%)] text-on-accent border border-transparent shadow-sm hover:brightness-110",
        secondary: "bg-[linear-gradient(180deg,#ffffff_0%,#edf3ff_100%)] text-ink border border-line-strong hover:bg-[linear-gradient(180deg,#f5f9ff_0%,#e9f0ff_100%)]",
        quiet: "text-accent underline decoration-1 underline-offset-4 hover:text-accent-strong hover:decoration-2 shadow-none",
      },
      size: {
        md: "min-h-11 px-4 py-2 text-base",
        sm: "min-h-9 px-3 py-1.5 text-sm",
      },
    },
    compoundVariants: [{ variant: "quiet", className: "px-1" }],
    defaultVariants: { variant: "secondary", size: "md" },
  },
);
