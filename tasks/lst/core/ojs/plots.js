import * as Plot from "https://cdn.jsdelivr.net/npm/@observablehq/plot/+esm";

let _city = "";
let _width = 640;

export function setCity(city) { _city = city; }
export function setWidth(w) { _width = w; }

export function plot_summer_area(data, { height = 300 } = {}) {
  const rows = data
    .map(d => ({ bin: d.bin, lower: +d.bin.split("-")[0], pct: +d.percentage }))
    .sort((a, b) => a.lower - b.lower);

  return Plot.plot({
    title: `${_city} — Summer Land Surface Temperature`,
    width: _width,
    height,
    x: { domain: rows.map(d => d.bin), label: "Temperature (°C)", tickRotate: -30 },
    y: { label: "% of city area", grid: true },
    color: { type: "linear", domain: [0, 55], scheme: "RdYlBu", reverse: true },
    marks: [
      Plot.barY(rows, { x: "bin", y: "pct", fill: d => d.lower, tip: true }),
      Plot.ruleY([0])
    ]
  });
}
