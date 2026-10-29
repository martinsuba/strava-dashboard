import { describe, expect, it } from "vitest";
import {
  aboveCapCount,
  capNote,
  chartLabel,
  chartModel,
  formatGap,
  metaLine,
  prOf,
  visibleYears,
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

describe("summarize", () => {
  it("computes PR, latest and this-year figures", () => {
    const s = summarize(efforts, 2026, 355);
    expect(s?.pr.activity_id).toBe("b");
    expect(s?.latest.activity_id).toBe("c");
    expect(s?.medianS).toBe(355);
    expect(summarize(efforts, 2026, 999)?.medianS).toBe(999); // taken from the data file, not computed
    expect(s?.yearCount).toBe(1);
    expect(s?.yearBestS).toBe(355);
  });
  it("has no best for a year without efforts, and null without efforts", () => {
    expect(summarize(efforts, 2030, 355)).toMatchObject({ yearCount: 0, yearBestS: null });
    expect(summarize([], 2026, null)).toBeNull();
  });
});

describe("metaLine and chartLabel", () => {
  const data: SegmentData = { name: "S", ref_length_m: 2400, efforts, per_year: [], median_s: 355 };
  it("meta", () => {
    expect(metaLine(data)).toBe("2.40 km · 3 efforts · first ridden 4 May 2019");
    expect(metaLine({ ...data, efforts: [efforts[0] as Effort] })).toContain("1 effort ·");
  });
  it("label contains PR m:ss and the range", () => {
    expect(chartLabel(efforts, 355)).toBe(
      "Elapsed time for 3 efforts from 2019 to 2026; PR 5:41 on 12 Jun 2024",
    );
  });
});

describe("chartModel", () => {
  it("splits the PR from the other efforts and pads the ranges", () => {
    const m = chartModel(efforts, 355);
    expect(m?.pr).toMatchObject({ y: 341, x: T2024 * 1000 });
    expect(m?.efforts.map((p) => p.y)).toEqual([456, 355]);
    expect(m?.years).toEqual([2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026, 2027]);
    expect(m?.xMin).toBe(Date.UTC(2019, 0, 1));
    expect(m?.xMax).toBe(Date.UTC(2027, 0, 1));
    expect(m && m.yMin <= 341 && m.yMax >= 456).toBe(true);
    expect(m && m.yMin % m.yStep === 0 && m.yMax % m.yStep === 0).toBe(true);
  });
  it("handles a single effort", () => {
    const m = chartModel([effort("a", T2026, 300)], 300);
    expect(m?.efforts).toEqual([]);
    expect(m && m.yMax > m.yMin).toBe(true);
    expect(m?.years).toEqual([2026, 2027]);
  });
  it("is null without efforts", () => {
    expect(chartModel([], null)).toBeNull();
  });
});

describe("prOf", () => {
  it("is the fastest effort, undefined when empty", () => {
    expect(prOf(efforts)?.activity_id).toBe("b");
    expect(prOf([])).toBeUndefined();
  });
});

describe("visibleYears", () => {
  const years = [2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026, 2027];
  it("keeps all years when they fit", () => {
    expect(visibleYears(years, 600)).toEqual(years);
  });
  it("thins out years on a narrow plot", () => {
    expect(visibleYears(years, 280)).toEqual([2019, 2021, 2023, 2025, 2027]);
    expect(visibleYears(years, 100)).toEqual([2019, 2024]);
  });
});

describe("y axis cap (T-016)", () => {
  const T = (m: number): number => Date.UTC(2020, m, 1) / 1000;
  const set = [
    effort("a", T(0), 300),
    effort("b", T(1), 310),
    effort("c", T(2), 320),
    effort("d", T(3), 290),
    effort("slow", T(4), 900),
  ];
  it("counts efforts above 2x the median (median 310 -> cap 620)", () => {
    expect(aboveCapCount(set, 310)).toBe(1);
    expect(
      aboveCapCount([effort("a", T(0), 620), effort("b", T(1), 100), effort("c", T(2), 620)], 310),
    ).toBe(0);
  });
  it("caps at CAP_FACTOR x the median_s it is given, it computes none itself", () => {
    expect(aboveCapCount(set, 100)).toBe(5); // cap 200
    expect(aboveCapCount(set, 1000)).toBe(0); // cap 2000
    expect(chartModel(set, 1000)?.capped).toHaveLength(0);
  });
  it("words the note in singular and plural, empty for none", () => {
    expect(capNote(set, 310)).toBe("1 slower effort above the cap");
    expect(capNote([...set, effort("s2", T(5), 1000)], 310)).toBe("2 slower efforts above the cap");
    expect(capNote(set.slice(0, 4), 310)).toBe("");
  });
  it("puts capped efforts on the slow edge at their date and sizes the axis without them", () => {
    const m = chartModel(set, 310);
    expect(m?.capped).toHaveLength(1);
    expect(m?.capped[0]).toMatchObject({ x: T(4) * 1000, y: m?.yMax, actual: 900 });
    expect(m?.efforts.map((p) => p.y)).toEqual([300, 310, 320]);
    expect(m && m.yMax < 900).toBe(true);
  });
  it("mentions the cap in the chart label only when needed", () => {
    expect(chartLabel(set, 310)).toContain("1 slower effort above the cap");
    expect(chartLabel(set.slice(0, 4), 310)).not.toContain("cap");
  });
  it("spans the whole ~3 years Oct 2019 - May 2021 on the x axis", () => {
    const long = [
      effort("a", Date.UTC(2019, 9, 12) / 1000, 310),
      effort("b", Date.UTC(2020, 5, 20) / 1000, 290),
      effort("c", Date.UTC(2021, 4, 9) / 1000, 301),
    ];
    const m = chartModel(long, 301);
    expect(m?.years).toEqual([2019, 2020, 2021, 2022]);
    expect(m?.xMin).toBe(Date.UTC(2019, 0, 1));
    expect(m?.xMax).toBe(Date.UTC(2022, 0, 1));
    expect(m?.efforts.map((p) => p.x)).toEqual([Date.UTC(2019, 9, 12), Date.UTC(2021, 4, 9)]);
    expect(m?.pr.x).toBe(Date.UTC(2020, 5, 20));
  });
});
