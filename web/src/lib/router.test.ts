import { describe, expect, it } from "vitest";
import { isCurrentRoute, parseRoute, rideHref, segmentHref } from "./router";

describe("parseRoute", () => {
  it("maps empty and root hashes to the index", () => {
    expect(parseRoute("")).toEqual({ page: "index" });
    expect(parseRoute("#/")).toEqual({ page: "index" });
  });

  it("maps the rides shortcut", () => {
    expect(parseRoute("#/rides")).toEqual({ page: "rides" });
  });

  it("maps segment and ride routes", () => {
    expect(parseRoute("#/segment/hill-road-climb")).toEqual({
      page: "segment",
      slug: "hill-road-climb",
    });
    expect(parseRoute("#/ride/3000000108")).toEqual({ page: "ride", id: "3000000108" });
  });

  it("sends anything else to not-found", () => {
    expect(parseRoute("#/nope").page).toBe("not-found");
    expect(parseRoute("#/ride/abc").page).toBe("not-found");
    expect(parseRoute("#/segment/Bad Slug").page).toBe("not-found");
    expect(parseRoute("#/segment/%E0%A4%A").page).toBe("not-found");
  });

  it("builds hrefs that parse back", () => {
    expect(parseRoute(segmentHref("lakeside-flat"))).toEqual({
      page: "segment",
      slug: "lakeside-flat",
    });
    expect(parseRoute(rideHref("42"))).toEqual({ page: "ride", id: "42" });
  });
});

describe("isCurrentRoute", () => {
  it("accepts the same ride with trailing slash or percent-encoding", () => {
    const ride = { page: "ride", id: "3000000106" } as const;
    expect(isCurrentRoute("#/ride/3000000106", ride)).toBe(true);
    expect(isCurrentRoute("#/ride/3000000106/", ride)).toBe(true);
    expect(isCurrentRoute("#/ride/%33000000106", ride)).toBe(true);
  });

  it("accepts the same segment with a trailing slash", () => {
    expect(isCurrentRoute("#/segment/hill-road/", { page: "segment", slug: "hill-road" })).toBe(
      true,
    );
  });

  it("rejects another page or another id", () => {
    const ride = { page: "ride", id: "1" } as const;
    expect(isCurrentRoute("#/ride/2", ride)).toBe(false);
    expect(isCurrentRoute("#/segment/s", ride)).toBe(false);
    expect(isCurrentRoute("#/", ride)).toBe(false);
    expect(isCurrentRoute("#/ride/1", { page: "segment", slug: "s" })).toBe(false);
  });
});
