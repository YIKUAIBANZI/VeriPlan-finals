import type { Decision } from "./types";

/** "A1 月新增订单收入" — ids alone are unreadable on a projector. */
export function assumptionName(decision: Decision, id: string): string {
  const label = decision.assumptions?.find(item => item.id === id)?.label;
  return label ? `${id} ${label}` : id;
}
