// core/ojs/dataloader.js - Loads plot-ready CSVs straight from each task's
// tabular output (no clean-tabular, no processed/ folder).
// Usage: import {loadData} from "./core/ojs/dataloader.js"
//        d = await loadData(city)
//        Then: d.pg, d.pas, d.pv, etc.

export async function loadData(city, tdir = `./02-process-output/tabular/`) {
  const d3 = await import("https://cdn.jsdelivr.net/npm/d3@7/+esm");
  // tdir defaults to the local scan output; index_cog.qmd passes the delivery
  // bucket's tabular/ URL so the web report reads the delivered CSVs instead.
  // Most files are city-prefixed ({city}_name.csv). Fathom prob files are not
  // (multianalysis.R writes fu_prob.csv / pu_prob.csv / cu_prob.csv) — pass prefixed=false.
  async function load(name, prefixed = true) {
    const file = prefixed ? `${tdir}${city.toLowerCase()}_${name}.csv` : `${tdir}${name}.csv`;
    try {
      const r = await fetch(file);
      return r.ok ? d3.csvParse(await r.text(), d3.autoType) : null;
    } catch (e) { return null; }
  }

  var [pg, pas, rwi_area, uba, uba_area, lc, pug, pv, pv_area,
         aq_area, summer_area, ndvi_area, fu, pu, cu, comb,
         e, s, ls_area, l_area, fwi, uba_tracker, fe, fu_prob, pu_prob, cu_prob ] = await Promise.all([
    load("pg"),
    load("pas"),
    load("rwi_area"),
    load("wsf_harmonized"),  // uba (plot_ubaa) — harmonized, not evolution
    load("uba_area"),
    load("lc"),
    load("pug"),
    load("solar_monthly_stats"), // pv (plot_pv_alt)
    load("pv_area"),
    load("aq_area"),
    load("summer_area"),
    load("ndvi_area"),       // ndxi task writes {city}_ndvi_area.csv
    load("fu"),
    load("pu"),
    load("cu"),
    load("comb"),
    load("elevation"),       // e
    load("slope"),           // s
    load("ls_area"),
    load("l_area"),
    load("fwi_weekly_95"),   // fwi
    load("wsf_tracker"),     // uba_tracker
    load("flood_events"),    // fe
    load("fu_prob", false),
    load("pu_prob", false),
    load("cu_prob", false),  // fathom multianalysis.R writes cu_prob.csv (no city prefix)
  ]);

  return {pg, pas, rwi_area, uba, uba_area, lc, pug, pv, pv_area, aq_area, summer_area, ndvi_area, fu, pu, cu, comb, e, s, ls_area, l_area, fwi, fe, uba_tracker, fu_prob, pu_prob, cu_prob};
}
