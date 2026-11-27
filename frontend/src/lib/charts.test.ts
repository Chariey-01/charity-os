import { expect, it } from "vitest";

import { foldSlices } from "./charts";

const slice = (label: string, value: number) => ({ key: label, label, color: "#000000", value });

it("keeps at most six segments, largest first, folding the rest into Other", () => {
  const rows = ["a", "b", "c", "d", "e", "f", "g"].map((label, index) => slice(label, 10 - index));
  const folded = foldSlices(rows);
  expect(folded.map((row) => row.label)).toEqual(["a", "b", "c", "d", "e", "Other (2)"]);
  expect(folded.at(-1)!.value).toBe(4 + 5);
  expect(folded.reduce((sum, row) => sum + row.value, 0)).toBe(rows.reduce((sum, row) => sum + row.value, 0));
});

it("drops empty parts and keeps small sets whole", () => {
  expect(foldSlices([slice("a", 0), slice("b", 2)]).map((row) => row.label)).toEqual(["b"]);
});
