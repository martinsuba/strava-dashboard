import { describe, expect, it, vi } from "vitest";
import { onLeave, runCleanups } from "./cleanup";

describe("cleanup hooks", () => {
  it("runs registered hooks once, in order, and then forgets them", () => {
    const calls: string[] = [];
    onLeave(() => calls.push("a"));
    onLeave(() => calls.push("b"));
    runCleanups();
    runCleanups();
    expect(calls).toEqual(["a", "b"]);
  });
  it("does nothing without hooks", () => {
    const fn = vi.fn();
    runCleanups();
    expect(fn).not.toHaveBeenCalled();
  });
});
