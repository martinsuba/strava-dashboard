import { describe, expect, it } from "vitest";
import { ridesNewestFirst, splitRides, type IndexRide } from "./index-data";

const ride = (id: string, date: string): IndexRide => ({
  id,
  date,
  name: `Ride ${id}`,
  km: 10,
  n_efforts: 0,
});

describe("ridesNewestFirst", () => {
  it("sorts by date descending without mutating the input", () => {
    const input = [
      ride("1", "2023-09-10T16:45:00Z"),
      ride("2", "2026-10-18T15:05:00Z"),
      ride("3", "2024-06-12T16:20:00Z"),
    ];
    expect(ridesNewestFirst(input).map((r) => r.id)).toEqual(["2", "3", "1"]);
    expect(input.map((r) => r.id)).toEqual(["1", "2", "3"]);
  });

  it("orders same-instant rides by id", () => {
    const same = "2024-06-12T16:20:00Z";
    expect(ridesNewestFirst([ride("b", same), ride("a", same)]).map((r) => r.id)).toEqual([
      "a",
      "b",
    ]);
  });

  it("handles an empty list", () => {
    expect(ridesNewestFirst([])).toEqual([]);
  });
});

describe("splitRides", () => {
  const many = Array.from({ length: 53 }, (_, i) =>
    ride(String(i), new Date(Date.UTC(2020, 0, 1 + i)).toISOString()),
  );

  it("shows the newest 50 and offers all 53", () => {
    const split = splitRides(many, 50);
    expect(split.shown).toHaveLength(50);
    expect(split.rest).toHaveLength(3);
    expect(split.shown[0]?.id).toBe("52");
    expect(split.rest[2]?.id).toBe("0");
    expect(split.showAllLabel).toBe("Show all 53 rides");
  });

  it("has no button at or under the limit", () => {
    expect(splitRides(many.slice(0, 50), 50).showAllLabel).toBeNull();
    expect(splitRides([], 50)).toEqual({ shown: [], rest: [], showAllLabel: null });
  });
});
