import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, expect, it, vi } from "vitest";
import { AssumptionEditor } from "./AssumptionEditor";
afterEach(cleanup);
it("states the confidence meaning and constrains its slider", () => {
  const onChange = vi.fn();
  render(<AssumptionEditor value={[{ label: "收入", category: "revenue", value: 0, unit: "元", confidence: 50 }]} onChange={onChange} />);
  expect(screen.getByText(/±20%/)).toBeVisible();
  const slider = screen.getByRole("slider");
  expect(slider).toHaveAttribute("min", "50");
  expect(slider).toHaveAttribute("max", "95");
  fireEvent.change(slider, { target: { value: "80" } });
  expect(onChange).toHaveBeenCalledWith([expect.objectContaining({ confidence: 80, value: 0 })]);
});
