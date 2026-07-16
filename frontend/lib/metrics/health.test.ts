import { describe, expect, it } from "vitest";
import { gradeFromScore, areasFromBackendPillars, buildHealthFromApi, insightKind } from "./health";

describe("gradeFromScore", () => {
  it("maps score bands", () => {
    expect(gradeFromScore(90)).toBe("Excellent");
    expect(gradeFromScore(75)).toBe("Healthy");
    expect(gradeFromScore(60)).toBe("Needs work");
    expect(gradeFromScore(45)).toBe("At risk");
    expect(gradeFromScore(20, { unresolvedProblems: 1 })).toBe("Critical");
    expect(gradeFromScore(0)).toBe("No data");
  });

  it("uses stabilizing during grace period", () => {
    expect(gradeFromScore(80, { inGracePeriod: true })).toBe("Stabilizing");
  });

  it("uses building baseline when low score with no open issues", () => {
    expect(gradeFromScore(30, { unresolvedProblems: 0, openOpportunities: 0 })).toBe(
      "Building baseline"
    );
  });
});

describe("areasFromBackendPillars", () => {
  it("normalizes pillar points onto 0-100 bars", () => {
    const areas = areasFromBackendPillars({
      search_visibility: 25,
      conversion_performance: 12.5,
      traffic_quality: 7.5,
      efficiency: 10,
      technical: 5,
    });
    expect(areas.find((a) => a.id === "visibility")?.score).toBe(100);
    expect(areas.find((a) => a.id === "conversion")?.score).toBe(50);
    expect(areas.find((a) => a.id === "technical")?.score).toBe(50);
  });
});

describe("buildHealthFromApi", () => {
  it("builds display from authoritative API score", () => {
    const health = buildHealthFromApi({
      health_score: 72,
      risk: "watch",
      risk_reasons: ["CTR lagging"],
      pillars: {
        search_visibility: 20,
        conversion_performance: 15,
        traffic_quality: 10,
        efficiency: 12,
        technical: 8,
      },
      top_action: { title: "Fix title tags", detail: "On top pages" },
    });
    expect(health.score).toBe(72);
    expect(health.grade).toBe("Healthy");
    expect(health.improvements[0]?.title).toBe("Fix title tags");
    expect(health.areas.length).toBe(5);
  });

  it("returns no-data when API score missing", () => {
    const health = buildHealthFromApi(null);
    expect(health.score).toBe(0);
    expect(health.grade).toBe("No data");
  });
});

describe("insightKind", () => {
  it("prefers explicit kind then falls back to type", () => {
    expect(insightKind({ kind: "opportunity", type: "decline_alert" })).toBe("opportunity");
    expect(insightKind({ type: "decline_alert" })).toBe("problem");
    expect(insightKind({ type: "position_opportunity" })).toBe("opportunity");
  });
});
