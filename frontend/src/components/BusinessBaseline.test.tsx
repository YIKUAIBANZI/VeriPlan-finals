import { cleanup, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, expect, it } from "vitest";

import { BusinessBaselinePanel } from "./BusinessBaseline";

afterEach(cleanup);

it("shows known values, unknown values and grouped collection work", () => {
  render(
    <BusinessBaselinePanel
      baseline={{
        monthly_ticket_volume: 500,
        repetitive_ticket_rate: null,
        average_handle_minutes: 6,
        loaded_hourly_cost: null,
        expected_ai_resolution_rate: null,
        review_minutes_per_ai_ticket: null,
        monthly_tool_cost: null,
        max_acceptable_error_rate: null,
      }}
      analysis={{
        known_field_count: 2,
        total_field_count: 8,
        is_calculable: false,
        automatable_ticket_volume: null,
        monthly_hours_saved: null,
        estimated_monthly_net_savings: null,
        collection_tasks: ["抽样最近 7 天售后工单。"],
        disclaimer: "用户输入试算，不是已验证收益",
      }}
    />,
  );

  expect(screen.getByText("2 / 8 已知")).toBeVisible();
  expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "2");
  expect(screen.getByText("500 条")).toBeVisible();
  expect(screen.getAllByText("未知").length).toBeGreaterThan(0);
  expect(screen.getByText("抽样最近 7 天售后工单。")).toBeVisible();
  expect(screen.getByText(/输入不完整，本次不计算收益/)).toBeVisible();
});

it("shows the deterministic estimate with its disclaimer", () => {
  render(
    <BusinessBaselinePanel
      baseline={{
        monthly_ticket_volume: 1000,
        repetitive_ticket_rate: 60,
        average_handle_minutes: 8,
        loaded_hourly_cost: 40,
        expected_ai_resolution_rate: 70,
        review_minutes_per_ai_ticket: 1,
        monthly_tool_cost: 800,
        max_acceptable_error_rate: 2,
      }}
      analysis={{
        known_field_count: 8,
        total_field_count: 8,
        is_calculable: true,
        automatable_ticket_volume: 420,
        monthly_hours_saved: 49,
        estimated_monthly_net_savings: 1160,
        collection_tasks: [],
        disclaimer: "用户输入试算，不是已验证收益",
      }}
    />,
  );

  expect(screen.getByText("¥1,160")).toBeVisible();
  expect(screen.getByText("用户输入试算，不是已验证收益")).toBeVisible();
});
