import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "Before You Buy — fictional simulation",
  description:
    "A fictional simulation that checks a proposed portfolio purchase against rules the investor explicitly confirmed, and shows the evidence. Not financial advice.",
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#16202b",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <noscript>
          <p className="m-4 rounded-md border-l-4 border-unknown bg-unknown-soft px-4 py-3 text-ink">
            Simulation — fictional portfolio, not advice. This page needs JavaScript to run the simulation.
          </p>
        </noscript>
        {children}
      </body>
    </html>
  );
}
