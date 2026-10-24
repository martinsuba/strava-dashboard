import { describe, expect, it } from "vitest";
import {
  chartLabel,
  chartModel,
  formatGap,
  medianSeconds,
  metaLine,
  rankLabel,
  sortEfforts,
  summarize,
  yearOf,
  type Effort,
  type SegmentData,
} from "./segment-data";

const T2024 = Date.UTC(2024, 5, 12, 16, 0) / 1000;
const T2026 = Date.UTC(2026, 5, 7, 16, 0) / 1000;
const T2019 = Date.UTC(2019, 4, 4, 8, 0) / 1000;

function effort(id: string, start_t: number, elapsed_s: number, rank = 1): Effort {
  return {
    segment_slug: "s",
    activity_id: id,
    ride_name: `Ride ${id}`,
    start_t,
    elapsed_s,
    distance_m: 2400,
    avg_kmh: 20,
    rank,
    gap_to_pr_s: 0,
    is_pr_at_time: false,
  };
}

const efforts = [effort("a", T2019, 456), effort("b", T2024, 341), effort("c", T2026, 355)];

describe("sortEfforts", () => {
  it("sorts fastest first with ties by earlier ride, without mutating", () => {
    const tie = [effort("x", T2026, 300), effort("y", T2019, 300), effort("z", T2024, 200)];
    expect(sortEfforts(tie, "fastest").map((e) => e.activity_id)).toEqual(["z", "y", "x"]);
    expect(tie[0]?.activity_id).toBe("x");
  });
  it("sorts newest first", () => {
    expect(sortEfforts(efforts, "newest").map((e) => e.activity_id)).toEqual(["c", "b", "a"]);
  });
});

describe("labels", () => {
  it("rank labels", () => {
    expect([1, 2, 3, 4, 12].map(rankLabel)).toEqual(["PR", "2nd", "3rd", "4", "12"]);
  });
  it("gap", () => {
    expect(formatGap(0)).toBe("—");
    expect(formatGap(31)).toBe("+0:31");
    expect(formatGap(3725)).toBe("+1:02:05");
  });
});

describe("yearOf", () => {
  it("uses Europe/Bratislava at the new year", () => {
    expect(yearOf(Date.UTC(2025, 11, 31, 23, 30) / 1000)).toBe(2026);
    expect(yearOf(Date.UTC(2025, 11, 31, 22, 30) / 1000)).toBe(2025);
  });
});

describe("medianSeconds", () => {
  it("odd, even, empty", () => {
    expect(medianSeconds(efforts)).toBe(355);
    expect(medianSeconds([...efforts, effort("d", T2026, 400)])).toBe(Math.round((355 + 400) / 2));
    expect(medianSeconds([])).toBe(0);
  });
});

describe("summarize", () => {
  it("computes PR, latest and this-year figures", () => {
    const s = summarize(efforts, 2026);
    expect(s?.pr.activity_id).toBe("b");
    expect(s?.latest.activity_id).toBe("c");
    expect(s?.medianS).toBe(355);
    expect(s?.yearCount).toBe(1);
    expect(s?.yearBestS).toBe(355);
  });
  it("has no best for a year without efforts, and null without efforts", () => {
    expect(summarize(efforts, 2030)).toMatchObject({ yearCount: 0, yearBestS: null });
    expect(summarize([], 2026)).toBeNull();
  });
});

describe("metaLine and chartLabel", () => {
  const data: SegmentData = { name: "S", ref_length_m: 2400, efforts, per_year: [] };
  it("meta", () => {
    expect(metaLine(data)).toBe("2.40 km · 3 efforts · first ridden 4 May 2019");
    expect(metaLine({ ...data, efforts: [efforts[0] as Effort] })).toContain("1 effort ·");
  });
  it("label contains PR m:ss and the range", () => {
    expect(chartLabel(efforts)).toBe(
      "Elapsed time for 3 efforts from 2019 to 2026; PR 5:41 on 12 Jun 2024",
    );
  });
});

describe("chartModel", () => {
  it("splits the PR from the other efforts and pads the ranges", () => {
    const m = chartModel(efforts);
    expect(m?.pr).toMatchObject({ y: 341, x: T2024 * 1000 });
    expect(m?.efforts.map((p) => p.y)).toEqual([456, 355]);
    expect(m?.years).toEqual([2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026, 2027]);
    expect(m?.xMin).toBe(Date.UTC(2019, 0, 1));
    expect(m?.xMax).toBe(Date.UTC(2027, 0, 1));
    expect(m && m.yMin <= 341 && m.yMax >= 456).toBe(true);
    expect(m && m.yMin % m.yStep === 0 && m.yMax % m.yStep === 0).toBe(true);
  });
  it("handles a single effort", () => {
    const m = chartModel([effort("a", T2026, 300)]);
    expect(m?.efforts).toEqual([]);
    expect(m && m.yMax > m.yMin).toBe(true);
    expect(m?.years).toEqual([2026, 2027]);
  });
  it("is null without efforts", () => {
    expect(chartModel([])).toBeNull();
  });
});
