/**
 * The explorer's single import point for contract types.
 *
 * At the commit this directory was started from, `@/lib/contracts` still
 * re-exported the provisional types. Once the contract-typed frontend lands,
 * change the line below to
 *   export type * from "@/lib/contracts";
 * Nothing else in this directory imports contract types from anywhere else.
 */
export type * from "@/generated/contracts/contracts";
