// Index JSON (docs/ARCHITECTURE.md "Site JSON"): segment summaries and a flat ride list.

export interface IndexSegment {
  slug: string;
  name: string;
  efforts: number;
  pr_s: number | null;
  pr_date: string | null;
}

export interface IndexRide {
  id: string;
  date: string; // UTC ISO 8601
  name: string;
  km: number;
  n_efforts: number;
}

export interface IndexData {
  generated: string;
  segments: IndexSegment[];
  rides: IndexRide[];
}

/** Rides newest first. The input may be in any order; ties keep a stable order by id. */
export function ridesNewestFirst(rides: readonly IndexRide[]): IndexRide[] {
  return [...rides].sort(
    (a, b) => Date.parse(b.date) - Date.parse(a.date) || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0),
  );
}

export interface RideSplit {
  shown: IndexRide[];
  rest: IndexRide[];
  /** Label of the "show all" button, or null when everything is shown. */
  showAllLabel: string | null;
}

/** Newest first, split into the first `limit` rides and the rest. */
export function splitRides(rides: readonly IndexRide[], limit: number): RideSplit {
  const sorted = ridesNewestFirst(rides);
  const rest = sorted.slice(limit);
  return {
    shown: sorted.slice(0, limit),
    rest,
    showAllLabel: rest.length > 0 ? `Show all ${sorted.length} rides` : null,
  };
}
