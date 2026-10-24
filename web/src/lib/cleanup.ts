// Per-route cleanup: a page registers what must be torn down when the user leaves it (e.g. a
// Chart.js instance); main.ts runs them all before rendering the next route.
const cleanups: (() => void)[] = [];

export function onLeave(fn: () => void): void {
  cleanups.push(fn);
}

export function runCleanups(): void {
  for (const fn of cleanups.splice(0)) fn();
}
