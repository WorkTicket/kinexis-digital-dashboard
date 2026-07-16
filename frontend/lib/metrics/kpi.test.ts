import { describe, expect, it } from "vitest";
import { formatKpiValue } from "./kpi";

describe("formatKpiValue", () => {
  it("formats number types", () => {
    expect(formatKpiValue(1234, "number")).toMatch(/1/);
    expect(formatKpiValue(0.045, "percent")).toMatch(/%/);
  });
});
