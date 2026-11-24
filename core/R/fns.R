# =========================================================
# fns.R — sourcing manifest
# =========================================================

# Module map:
#   fns-util.R         core utilities: fuzzy_read, type_data, exists_and_true,
#                      resolve_render_targets, tryCatch_named, Mode, normalize
#   fns-text.R         string/number formatting: paste_bold, print_text,
#                      tolatin, label_maker, format_title, break_lines
#   fns-geometry.R     raster/vector geometry transforms: rast_as_vect,
#                      density_rast, center_max_circle, create_geom
#   fns-aggregation.R  hex/cell aggregation primitives + orchestration:
#                      run_aggregate, hexbin_aggregate, points_hex_count,
#                      build_aggregate_lookups, apply_smoothing, aggregate_hex
#   fns-maps-aes.R     ggplot scales / themes / output: fill_scale, color_scale,
#                      break_pretty2, theme_custom, save_plot, set_domain
#   fns-maps-static.R  static map composer: plot_static_layer, add_roads_underlay,
#                      add_wards_labels, add_builtup_hatch, autozoom_bounds,
#                      aspect_buffer, coord_3857_bounds
#   fns-maps-web.R     leaflet API: prepare_parameters, create_layer_function
#   fns-charts.R       chart helpers: ggdonut, filled_histo
#   fns-web.R          HTML/slide rendering: print_md, fill_slide_content,
#                      prepare_html, include_html_chart

source(here("core/R/fns-util.R"),         local = T)
source(here("core/R/fns-text.R"),         local = T)
source(here("core/R/fns-geometry.R"),     local = T)
source(here("core/R/fns-aggregation.R"),  local = T)
source(here("core/R/fns-maps-aes.R"),     local = T)
source(here("core/R/fns-maps-static.R"),  local = T)
source(here("core/R/fns-maps-web.R"),     local = T)
source(here("core/R/fns-cog-web.R"),      local = T)
source(here("core/R/fns-charts.R"),       local = T)
source(here("core/R/fns-web.R"),          local = T)
