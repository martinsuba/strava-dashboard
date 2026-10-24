// Display formats from docs/DESIGN.md. All dates are shown in Europe/Bratislava (D-007).

export const DISPLAY_TIME_ZONE = "Europe/Bratislava";

/** Elapsed seconds as m:ss, or h:mm:ss from one hour. */
export function formatDuration(totalSeconds: number): string {
  const s = Math.round(totalSeconds);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = String(s % 60).padStart(2, "0");
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${sec}` : `${m}:${sec}`;
}

const DATE_PARTS = new Intl.DateTimeFormat("en-GB", {
  timeZone: DISPLAY_TIME_ZONE,
  day: "numeric",
  month: "short",
  year: "numeric",
});

/** UTC ISO 8601 timestamp (or epoch seconds) as "12 Jun 2024" in Europe/Bratislava. */
export function formatDate(when: string | number): string {
  const date = typeof when === "number" ? new Date(when * 1000) : new Date(when);
  const parts = Object.fromEntries(DATE_PARTS.formatToParts(date).map((p) => [p.type, p.value]));
  const month = parts["month"] === "Sept" ? "Sep" : parts["month"];
  return `${parts["day"]} ${month} ${parts["year"]}`;
}

/** Distance in km with one decimal ("42.6"). */
export function formatKm(km: number): string {
  return km.toFixed(1);
}
