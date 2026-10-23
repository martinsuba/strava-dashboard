import { describe, expect, it } from "vitest";
import { parseRoute, rideHref, segmentHref } from "./router";

describe("parseRoute", () => {
  it("maps empty and root hashes to the index", () => {
    expect(parseRoute("")).toEqual({ page: "index" });
    expect(parseRoute("#/")).toEqual({ page: "index" });
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
