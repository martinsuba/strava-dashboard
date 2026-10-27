import { describe, expect, it } from "vitest";
import { barLabel, barPositions, newPrCount, prMark, rankOf } from "./ride-data";

describe("barPositions", () => {
  it("runs from the PR (0) to the slowest effort (100)", () => {
    expect(barPositions({ pr_s: 100, median_s: 130, slowest_s: 200, elapsed_s: 160 })).toEqual({
      medianPct: 30,
      todayPct: 60,
    });
  });

  it("puts today on the left end when it is the PR and on the right end when slowest", () => {
    expect(
      barPositions({ pr_s: 100, median_s: 120, slowest_s: 200, elapsed_s: 100 }).todayPct,
    ).toBe(0);
    expect(
      barPositions({ pr_s: 100, median_s: 120, slowest_s: 200, elapsed_s: 200 }).todayPct,
    ).toBe(100);
  });

  it("keeps everything at 0 when PR and slowest coincide (single effort)", () => {
    expect(barPositions({ pr_s: 100, median_s: 100, slowest_s: 100, elapsed_s: 100 })).toEqual({
      medianPct: 0,
      todayPct: 0,
    });
  });

  it("clamps values outside PR..slowest (inconsistent data) into the bar", () => {
    const p = barPositions({ pr_s: 100, median_s: 90, slowest_s: 200, elapsed_s: 300 });
    expect(p).toEqual({ medianPct: 0, todayPct: 100 });
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

describe("barLabel", () => {
  it("spells out today, PR, median and slowest", () => {
    expect(barLabel({ elapsed_s: 377, pr_s: 341, median_s: 374, slowest_s: 456 })).toBe(
      "Today 6:17, PR 5:41, median 6:14, slowest 7:36",
    );
  });
});
