import { describe, expect, it } from "vitest";
import { formatDate, formatDuration, formatKm } from "./format";

describe("formatDuration", () => {
  it("uses m:ss under an hour", () => {
    expect(formatDuration(341)).toBe("5:41");
    expect(formatDuration(59)).toBe("0:59");
    expect(formatDuration(600)).toBe("10:00");
  });

  it("uses h:mm:ss from one hour", () => {
    expect(formatDuration(3600)).toBe("1:00:00");
    expect(formatDuration(3725)).toBe("1:02:05");
  });

  it("rounds to whole seconds", () => {
    expect(formatDuration(340.6)).toBe("5:41");
  });
});

describe("formatDate", () => {
  it("formats as 12 Jun 2024", () => {
    expect(formatDate("2024-06-12T16:20:00Z")).toBe("12 Jun 2024");
    expect(formatDate("2026-10-18T15:05:00Z")).toBe("18 Oct 2026");
  });

  it("uses the Europe/Bratislava day, not UTC", () => {
    expect(formatDate("2026-06-07T22:30:00Z")).toBe("8 Jun 2026"); // 00:30 CEST
    expect(formatDate("2026-01-07T22:30:00Z")).toBe("7 Jan 2026"); // 23:30 CET
  });

  it("writes Sep as Sep", () => {
    expect(formatDate("2023-09-10T16:45:00Z")).toBe("10 Sep 2023");
  });
});

describe("formatKm", () => {
  it("shows one decimal", () => {
    expect(formatKm(42.6)).toBe("42.6");
    expect(formatKm(18)).toBe("18.0");
    expect(formatKm(88.349)).toBe("88.3");
  });
});
