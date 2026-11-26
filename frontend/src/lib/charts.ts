export type Slice = { key: string; label: string; color: string; value: number };

const OTHER_COLOR = "#94A3B8";

/** Keep the five largest parts and fold the rest into "Other" (at most six segments). */
export function foldSlices(rows: Slice[], max = 6): Slice[] {
  const sorted = [...rows].filter((row) => row.value > 0).sort((a, b) => b.value - a.value || a.label.localeCompare(b.label));
  if (sorted.length <= max) return sorted;
  const kept = sorted.slice(0, max - 1);
  const rest = sorted.slice(max - 1);
  return [...kept, { key: "other", label: `Other (${rest.length})`, color: OTHER_COLOR, value: rest.reduce((sum, row) => sum + row.value, 0) }];
}
