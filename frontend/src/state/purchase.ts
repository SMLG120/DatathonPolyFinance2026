"use client";

import { useMemo } from "react";
import { percentInputToFraction } from "@/lib/format";
import { readPurchaseForm, type PurchaseForm } from "@/lib/portfolio";
import { useWorkflow } from "./workflow";

/**
 * The purchase form of stage 3, read into a request. Other stages use it too:
 * a threshold preview in stage 2 is tried on the purchase entered here.
 */
export function usePurchaseForm(): PurchaseForm {
  const { state } = useWorkflow();
  const data = state.portfolio.data;
  const { instrumentId, targetText } = state.purchase;
  return useMemo(
    () =>
      readPurchaseForm(
        data?.purchasable_instrument_ids ?? [],
        { instrumentId: instrumentId === "" ? null : instrumentId, target: percentInputToFraction(targetText) },
        data?.scenario.demo_requests.map((request) => request.purchase_request) ?? [],
      ),
    [data, instrumentId, targetText],
  );
}
