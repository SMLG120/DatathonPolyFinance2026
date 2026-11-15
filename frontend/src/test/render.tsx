import { render, type RenderResult } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { EvidenceProvider } from "@/components/evidence/EvidenceProvider";
import { AnnouncerProvider } from "@/components/ui/Announcer";
import type { ApiClient } from "@/lib/api";
import { createFixturesClient } from "@/lib/api/fixtures-client";
import type { RuntimeConfig, Timing } from "@/lib/config";
import { RuntimeProvider } from "@/state/runtime";
import { WorkflowProvider } from "@/state/workflow";

export const FIXTURES_CONFIG: RuntimeConfig = { mode: "fixtures", apiBaseUrl: null, fixturesReason: "no-base-url", simulate: null };
export const LIVE_CONFIG: RuntimeConfig = { mode: "live", apiBaseUrl: "https://api.example.test", fixturesReason: null, simulate: null };

/** Short timers so tests do not wait on real debounce and poll intervals. */
export const FAST_TIMING: Timing = { pollIntervalMs: 5, pollDeadlineMs: 2_000, previewDebounceMs: 5 };

export interface AppRenderOptions {
  api?: ApiClient;
  config?: RuntimeConfig;
  timing?: Timing;
  verifyAccessCode?: (code: string) => Promise<void>;
}

export function Providers({ children, api, config = FIXTURES_CONFIG, timing = FAST_TIMING, verifyAccessCode }: AppRenderOptions & { children: ReactNode }) {
  return (
    <RuntimeProvider config={config} api={api ?? createFixturesClient({ latencyMs: 0 })} timing={timing} verifyAccessCode={verifyAccessCode}>
      <AnnouncerProvider>
        <WorkflowProvider>
          <EvidenceProvider>{children}</EvidenceProvider>
        </WorkflowProvider>
      </AnnouncerProvider>
    </RuntimeProvider>
  );
}

/** Renders a component inside the same providers the app uses, on the fixtures client by default. */
export function renderWithApp(ui: ReactElement, options: AppRenderOptions = {}): RenderResult {
  return render(<Providers {...options}>{ui}</Providers>);
}
