export function niceTicks(max: number) {
  const rough = max / 3;
  const power = 10 ** Math.floor(Math.log10(rough || 1));
  const step = [1, 2, 2.5, 5, 10].map((factor) => factor * power).find((candidate) => candidate >= rough) ?? power * 10;
  const ticks = [0];
  while (ticks[ticks.length - 1] < max) ticks.push(Number((ticks[ticks.length - 1] + step).toFixed(4)));
  return ticks;
}

export function formatMinutes(minutes: number) {
  if (minutes < 60) return `${Math.round(minutes)}m`;
  const hours = Math.floor(minutes / 60);
  const rest = Math.round(minutes % 60);
  return rest ? `${hours}h ${rest}m` : `${hours}h`;
}
