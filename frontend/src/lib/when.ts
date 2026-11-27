import { formatDate as formatWith } from "./time";

/** "27 Nov 2026" for an ISO date (YYYY-MM-DD); the year is dropped when it is this year. */
export function formatDate(date: string, thisYear = new Date().getFullYear()) {
  if (!date) return "";
  const year = Number(date.slice(0, 4));
  return formatWith(date, { day: "numeric", month: "short", ...(year === thisYear ? {} : { year: "numeric" }) });
}

export function monthLabel(month: string) {
  return formatWith(`${month}-01`, { month: "long", year: "numeric" });
}
