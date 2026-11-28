/** Squarified treemap layout (Bruls, Huizing & van Wijk). Pure, so it is unit-tested in node. */

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface Placed<T> extends Rect {
  item: T;
}

function worst(row: number[], side: number): number {
  const sum = row.reduce((a, b) => a + b, 0);
  const max = Math.max(...row);
  const min = Math.min(...row);
  const s2 = side * side;
  const sum2 = sum * sum;
  return Math.max((s2 * max) / sum2, sum2 / (s2 * min));
}

/** Lay out items (by `value`) inside `rect`. Items with value <= 0 are dropped. */
export function squarify<T>(items: T[], value: (item: T) => number, rect: Rect): Placed<T>[] {
  const entries = items
    .map((item) => ({ item, v: value(item) }))
    .filter((e) => e.v > 0)
    .sort((a, b) => b.v - a.v);
  const total = entries.reduce((a, e) => a + e.v, 0);
  if (!entries.length || rect.w <= 0 || rect.h <= 0 || total <= 0) return [];
  const scale = (rect.w * rect.h) / total;
  const areas = entries.map((e) => e.v * scale);
  const out: Placed<T>[] = [];
  let { x, y, w, h } = rect;
  let i = 0;
  while (i < areas.length) {
    const side = Math.min(w, h);
    const row: number[] = [areas[i]];
    let j = i + 1;
    while (j < areas.length && worst([...row, areas[j]], side) <= worst(row, side)) {
      row.push(areas[j]);
      j += 1;
    }
    const rowSum = row.reduce((a, b) => a + b, 0);
    if (w >= h) {
      const rowW = rowSum / h;
      let cy = y;
      row.forEach((area, k) => {
        const rh = area / rowW;
        out.push({ item: entries[i + k].item, x, y: cy, w: rowW, h: rh });
        cy += rh;
      });
      x += rowW;
      w -= rowW;
    } else {
      const rowH = rowSum / w;
      let cx = x;
      row.forEach((area, k) => {
        const rw = area / rowH;
        out.push({ item: entries[i + k].item, x: cx, y, w: rw, h: rowH });
        cx += rw;
      });
      y += rowH;
      h -= rowH;
    }
    i = j;
  }
  return out;
}
