import { describe, expect, it } from "vitest";
import { barPositions, newPrCount, prMark, rankOf } from "./ride-data";

describe("barPositions", () => {
  it("puts the PR at the left end and scales to the slower of average and today", () => {
    // span = 60 s, bar covers 75 s
    expect(barPositions({ pr_s: 100, avg_s: 130, elapsed_s: 160 })).toEqual({
      avgPct: 40,
      todayPct: 80,
    });
  });

  it("puts today on the left end when it is the PR", () => {
    expect(barPositions({ pr_s: 100, avg_s: 120, elapsed_s: 100 })).toEqual({
      avgPct: 80,
      todayPct: 0,
    });
  });

  it("keeps everything at 0 when PR, average and today coincide", () => {
    expect(barPositions({ pr_s: 100, avg_s: 100, elapsed_s: 100 })).toEqual({
      avgPct: 0,
      todayPct: 0,
    });
  });

  it("clamps an average below the PR (inconsistent data) into the bar", () => {
    expect(barPositions({ pr_s: 100, avg_s: 90, elapsed_s: 110 }).avgPct).toBe(0);
  });
});

describe("labels", () => {
  it("formats rank as 8 / 24", () => {
    expect(rankOf({ rank: 8, of: 24 })).toBe("8 / 24");
  });

  it("marks PR at the time as NEW PR, a bare current PR as PR, others not at all", () => {
    expect(prMark({ is_pr: true, is_pr_at_time: true })).toBe("NEW PR");
    expect(prMark({ is_pr: false, is_pr_at_time: true })).toBe("NEW PR");
    expect(prMark({ is_pr: true, is_pr_at_time: false })).toBe("PR");
    expect(prMark({ is_pr: false, is_pr_at_time: false })).toBeNull();
  });

  it("counts new PRs", () => {
    expect(newPrCount([{ is_pr_at_time: true }, { is_pr_at_time: false }] as never)).toBe(1);
  });
});
