import { KeyboardEvent, useId, useState } from "react";

import { formatMinutes, niceTicks } from "../../lib/format";

export type Point = { label: string; value: number; track?: number; detail?: string; tick?: string };

/**
 * Accessible column chart.
 * - One series: no legend; the title names it.
 * - Optional ``track``: a lighter step of the same hue drawn behind the bar
 *   (planned behind completed). A legend is shown in that case.
 * - Hover, tap or arrow keys show a tooltip; a table view is always available.
 */
export function ColumnChart({
  title,
  points,
  unit,
  tone = "productivity",
  trackLabel,
  valueLabel,
  format = (value) => `${value}`,
}: {
  title: string;
  points: Point[];
  unit: string;
  tone?: "productivity" | "health";
  trackLabel?: string;
  valueLabel?: string;
  format?: (value: number) => string;
}) {
  const [active, setActive] = useState<number | null>(null);
  const [table, setTable] = useState(false);
  const titleId = useId();
  const max = Math.max(1, ...points.map((point) => Math.max(point.value, point.track ?? 0)));
  const ticks = niceTicks(max);
  const top = ticks[ticks.length - 1];
  const hasTrack = points.some((point) => point.track !== undefined);
  const total = points.reduce((sum, point) => sum + point.value, 0);
  const labelEvery = Math.ceil(points.length / 7);

  function onKey(event: KeyboardEvent<HTMLDivElement>) {
    if (!points.length) return;
    if (event.key === "ArrowRight") setActive((value) => Math.min(points.length - 1, (value ?? -1) + 1));
    else if (event.key === "ArrowLeft") setActive((value) => Math.max(0, (value ?? points.length) - 1));
    else if (event.key === "Escape") setActive(null);
    else return;
    event.preventDefault();
  }

  const current = active !== null ? points[active] : null;
  return (
    <figure className={`chart chart-${tone}`} aria-labelledby={titleId}>
      <figcaption className="chart-head">
        <span id={titleId} className="chart-title">{title}</span>
        <button type="button" className="text-button small" onClick={() => setTable(!table)} aria-pressed={table}>
          {table ? "Chart" : "Table"}
        </button>
      </figcaption>
      {hasTrack && (
        <div className="legend" aria-hidden="true">
          <span><i className="key value" /> {valueLabel}</span>
          <span><i className="key track" /> {trackLabel}</span>
        </div>
      )}
      {table ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">Period</th>
                {hasTrack && <th scope="col">{trackLabel}</th>}
                <th scope="col">{valueLabel ?? unit}</th>
              </tr>
            </thead>
            <tbody>
              {points.map((point) => (
                <tr key={point.label}>
                  <th scope="row">{point.label}</th>
                  {hasTrack && <td>{format(point.track ?? 0)}</td>}
                  <td>{format(point.value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div
          className="plot"
          tabIndex={0}
          role="img"
          aria-label={`${title}. ${points.length} periods, total ${format(total)} ${unit}. Use arrow keys to read values or switch to the table.`}
          onKeyDown={onKey}
          onMouseLeave={() => setActive(null)}
          onBlur={() => setActive(null)}
        >
          <div className="grid" aria-hidden="true">
            {ticks.map((tick) => (
              <span key={tick} style={{ bottom: `${(tick / top) * 100}%` }}>
                <small>{format(tick)}</small>
              </span>
            ))}
          </div>
          <div className="bars" style={{ gridTemplateColumns: `repeat(${points.length}, minmax(0, 1fr))` }}>
            {points.map((point, index) => (
              <div
                key={point.label}
                className={`bar-slot ${active === index ? "active" : ""}`}
                onPointerEnter={() => setActive(index)}
                onPointerDown={() => setActive(index)}
              >
                {point.track !== undefined && <i className="bar track" style={{ height: `${(point.track / top) * 100}%` }} />}
                <i className="bar value" style={{ height: `${(point.value / top) * 100}%` }} />
              </div>
            ))}
          </div>
          <div className="x-labels" aria-hidden="true" style={{ gridTemplateColumns: `repeat(${points.length}, minmax(0, 1fr))` }}>
            {points.map((point, index) => (
              <small key={point.label}>{index % labelEvery === 0 ? point.tick ?? point.label : ""}</small>
            ))}
          </div>
          {current && (
            <div className="tooltip" role="status" style={{ left: `${((active! + 0.5) / points.length) * 100}%` }}>
              <b>{format(current.value)} {unit}</b>
              {current.track !== undefined && <span>of {format(current.track)} {trackLabel?.toLowerCase()}</span>}
              <small>{current.detail ?? current.label}</small>
            </div>
          )}
        </div>
      )}
    </figure>
  );
}

/** Horizontal bars, one row per category: a single series with a text label per row. */
export function CategoryBars({ rows }: { rows: { key: string; label: string; color: string; actual: number; planned: number }[] }) {
  const max = Math.max(1, ...rows.map((row) => Math.max(row.actual, row.planned)));
  return (
    <ul className="category-bars">
      {rows.map((row) => (
        <li key={row.key}>
          <span className="cat-label">
            <span className="category-dot" style={{ background: row.color }} aria-hidden="true" />
            {row.label}
          </span>
          <span className="cat-track" aria-hidden="true">
            <i className="planned" style={{ width: `${(row.planned / max) * 100}%` }} />
            <i className="actual" style={{ width: `${(row.actual / max) * 100}%` }} />
          </span>
          <span className="cat-value">
            <b>{formatMinutes(row.actual)}</b>
            <small> of {formatMinutes(row.planned)} planned</small>
          </span>
        </li>
      ))}
    </ul>
  );
}
