import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { recorded } from "@/test/probes";
import { PurchaseExposureExplorerSlot, VerdictExposureExplorerSlot } from "./ExposureExplorerSlots";

describe("3D exposure explorer slots", () => {
  it("render nothing until the explorer is wired in", () => {
    const verdict = render(<VerdictExposureExplorerSlot result={recorded.robertResult()} />);
    expect(verdict.container).toBeEmptyDOMElement();
    verdict.unmount();

    const purchase = render(<PurchaseExposureExplorerSlot result={recorded.robertResult()} />);
    expect(purchase.container).toBeEmptyDOMElement();
    purchase.unmount();

    const waiting = render(<PurchaseExposureExplorerSlot result={null} />);
    expect(waiting.container).toBeEmptyDOMElement();
  });
});
