# Coastal Erosion — Deltares ShorelineMonitor bar polygons
# Reads transect CSV, builds directional bar polygons from changerate,
# crops to AOI, saves as gpkg + fgb.
# Source: Delft University of Technology, Long-term Shoreline Changes (1984-2016)
#
# Produces TWO outputs:
#   shoreline_snap     — transect points snapped to nearest AOI boundary
#   shoreline_baseline — raw transect points (define their own coastline)
#
# Requires: setup.R already sourced (aoi, city_string, country, spatial_dir, tabular_dir)
USE_GCS <<- TRUE
if (!exists("aoi")) source(here::here("core/R/setup.R"))

# Download from GCS private bucket
shoreline_csv <- tempfile(fileext = ".csv")
tryCatch(
  googleCloudStorageR::gcs_get_object("Long-term Shoreline Changes/ShorelineMonitor_1984_2016_v1.1_set3_filtered.csv",
    bucket = "city-scan-global-data", saveToDisk = shoreline_csv),
  error = function(e) { message("Could not download shoreline data: ", e$message); shoreline_csv <<- NULL }
)

if (is.null(shoreline_csv) || length(shoreline_csv) == 0 || !file.exists(shoreline_csv)) {
  message("ShorelineMonitor CSV not found — skipping coastal erosion")
} else {

  message("\n=== Processing coastal erosion data ===")

  shoreline <- readr::read_csv(shoreline_csv, show_col_types = FALSE) %>%
    filter(tolower(country_name) == tolower(country)) %>%
    arrange(transect_id)

  if (nrow(shoreline) == 0) {
    message("No transects found for country: ", country, " — skipping")
  } else {

    # Raw transect coordinates
    coords_raw <- cbind(shoreline$Intersect_lon, shoreline$Intersect_lat)

    # Snapped coordinates (snap to nearest AOI boundary point)
    message("Snapping transect points to AOI boundary")
    aoi_boundary <- st_boundary(st_as_sf(aoi))
    pts_sf <- st_as_sf(data.frame(x = coords_raw[,1], y = coords_raw[,2]),
                        coords = c("x", "y"), crs = 4326)
    nearest <- st_nearest_points(pts_sf, aoi_boundary)
    snapped <- st_cast(nearest, "POINT")
    snapped_coords <- st_coordinates(snapped[seq(2, length(snapped), 2)])[, 1:2]

    # Group by BOX to avoid jumps between disjoint segments
    shoreline$box_group <- sub("_[0-9]+$", "", shoreline$transect_id)
    groups <- unique(shoreline$box_group)

    aoi_sf <- st_as_sf(aoi)

    # Pre-compute AOI boundary rings + winding order for deterministic outward normals
    bdy_all <- st_coordinates(aoi_boundary)
    bdy_ring_id <- apply(bdy_all[, 3:ncol(bdy_all), drop = FALSE], 1, paste, collapse = "_")
    bdy_rings <- split(seq_len(nrow(bdy_all)), bdy_ring_id)

    # Determine winding order per ring via shoelace formula
    # CCW (positive area) = exterior ring in OGC/sf → outward normal is (dy, -dx)
    # CW (negative area) = interior ring → outward normal is (-dy, dx)
    ring_ccw <- sapply(bdy_rings, function(indices) {
      pts <- bdy_all[indices, 1:2]
      nr <- nrow(pts)
      if (nr < 3) return(TRUE)
      signed_area <- sum(pts[-nr, 1] * pts[-1, 2] - pts[-1, 1] * pts[-nr, 2])
      signed_area > 0
    })

    # Helper: get AOI edge tangent + outward normal at nearest boundary point
    get_aoi_outward <- function(x, y) {
      dists <- sqrt((bdy_all[,1] - x)^2 + (bdy_all[,2] - y)^2)
      k_global <- which.min(dists)
      this_ring <- bdy_ring_id[k_global]
      ring_indices <- bdy_rings[[this_ring]]
      ring_pts <- bdy_all[ring_indices, 1:2]
      nr <- nrow(ring_pts)
      local_k <- which(ring_indices == k_global)
      k_prev <- ifelse(local_k == 1, nr - 1, local_k - 1)
      k_next <- ifelse(local_k == nr, 2, local_k + 1)
      edge_tang <- ring_pts[k_next, ] - ring_pts[k_prev, ]
      dx <- edge_tang[1]; dy <- edge_tang[2]
      # Outward normal based on winding: CCW → (dy, -dx), CW → (-dy, dx)
      if (ring_ccw[this_ring]) {
        outward <- c(dy, -dx)
      } else {
        outward <- c(-dy, dx)
      }
      list(tang = edge_tang, outward = outward)
    }

    # --- Function: build bar polygons for a given set of coordinates ---
    # tangent_source: "aoi_edge" = tangent from nearest AOI boundary edge
    #                 "transect" = tangent from transect point neighbors
    # Seaward direction is ALWAYS determined from AOI polygon winding (no probing)
    build_bars <- function(coords, tangent_source = "transect") {
      n <- nrow(coords)
      tang <- matrix(0, n, 2)
      seaward <- matrix(0, n, 2)

      if (tangent_source == "aoi_edge") {
        # Snap mode: tangent AND outward normal both from AOI boundary edge
        message("  Computing tangent + seaward from AOI boundary edge winding")
        for (i in 1:n) {
          aoi_info <- get_aoi_outward(coords[i, 1], coords[i, 2])
          tang[i, ] <- aoi_info$tang
          seaward[i, ] <- aoi_info$outward
        }
        # Normalize
        tang_len <- sqrt(rowSums(tang^2))
        tang_len[tang_len == 0] <- 1
        tang <- tang / tang_len
        sea_len <- sqrt(rowSums(seaward^2))
        sea_len[sea_len == 0] <- 1
        seaward <- seaward / sea_len

      } else {
        # Baseline mode: tangent from transect neighbors (with gap splitting)
        message("  Computing tangent from transect point neighbors (gap-aware)")
        for (grp in groups) {
          idx <- which(shoreline$box_group == grp)
          ng <- length(idx)
          if (ng == 1) { tang[idx, ] <- c(0, 1); next }

          # Split box at gaps > 500m to avoid cross-harbor tangents
          pts_grp <- coords[idx, ]
          dists <- sqrt(rowSums(diff(pts_grp)^2))
          seg_ids <- cumsum(c(1, dists > 0.005))

          for (sid in unique(seg_ids)) {
            seg_idx <- idx[seg_ids == sid]
            ns <- length(seg_idx)
            if (ns == 1) { tang[seg_idx, ] <- c(0, 1); next }
            tang[seg_idx[1], ] <- coords[seg_idx[2], ] - coords[seg_idx[1], ]
            tang[seg_idx[ns], ] <- coords[seg_idx[ns], ] - coords[seg_idx[ns - 1], ]
            if (ns > 2) {
              for (j in 2:(ns - 1)) {
                tang[seg_idx[j], ] <- coords[seg_idx[j + 1], ] - coords[seg_idx[j - 1], ]
              }
            }
          }
        }
        tang_len <- sqrt(rowSums(tang^2))
        tang_len[tang_len == 0] <- 1
        tang <- tang / tang_len

        # Two candidate normals perpendicular to transect tangent
        normal_a <- cbind(-tang[, 2], tang[, 1])   # rotate 90° CCW
        normal_b <- cbind(tang[, 2], -tang[, 1])   # rotate 90° CW

        # Seaward = outside AOI, using small probe (100m) to avoid overshooting harbors
        message("  Probing AOI at 100m to determine seaward direction")
        probe_sm <- 0.001  # ~100m
        pts_a <- st_as_sf(data.frame(x = coords[,1] + normal_a[,1] * probe_sm,
                                      y = coords[,2] + normal_a[,2] * probe_sm),
                           coords = c("x", "y"), crs = 4326)
        pts_b <- st_as_sf(data.frame(x = coords[,1] + normal_b[,1] * probe_sm,
                                      y = coords[,2] + normal_b[,2] * probe_sm),
                           coords = c("x", "y"), crs = 4326)
        in_aoi_a <- st_intersects(pts_a, aoi_sf, sparse = FALSE)[, 1]
        in_aoi_b <- st_intersects(pts_b, aoi_sf, sparse = FALSE)[, 1]
        use_a <- !in_aoi_a  # outside AOI = seaward
        ambiguous <- in_aoi_a == in_aoi_b

        # Resolve ambiguous points by inheriting from non-ambiguous neighbors in same box
        if (any(ambiguous)) {
          message("  ", sum(ambiguous), " ambiguous points — inheriting from box neighbors")
          for (grp in groups) {
            idx <- which(shoreline$box_group == grp)
            grp_amb <- idx[ambiguous[idx]]
            grp_ok  <- idx[!ambiguous[idx]]
            if (length(grp_amb) > 0 && length(grp_ok) > 0) {
              majority <- sum(use_a[grp_ok]) > length(grp_ok) / 2
              use_a[grp_amb] <- majority
            } else if (length(grp_amb) > 0) {
              # Entire box ambiguous: fall back to AOI winding
              for (i in grp_amb) {
                ref <- get_aoi_outward(coords[i, 1], coords[i, 2])$outward
                use_a[i] <- sum(normal_a[i, ] * ref) > 0
              }
            }
          }
        }

        seaward <- normal_a
        seaward[!use_a, ] <- normal_b[!use_a, ]
      }

      # Create bar endpoints (scale changerate to bar length)
      bar_rate <- shoreline$changerate  # no clamping
      bar_scale <- 0.0005  # ~300m per m/yr
      end_pts <- coords + seaward * bar_rate * bar_scale

      # Build rectangular POLYGON bars
      bar_width <- 0.0009  # half-width ~33m
      polys <- lapply(1:n, function(i) {
        w <- tang[i, ] * bar_width
        st_polygon(list(rbind(
          coords[i, ] - w,
          coords[i, ] + w,
          end_pts[i, ] + w,
          end_pts[i, ] - w,
          coords[i, ] - w
        )))
      })

      bar_sf <- st_sf(
        transect_id = shoreline$transect_id,
        changerate = round(shoreline$changerate, 3),
        geometry = st_sfc(polys, crs = 4326)
      )

      # Crop to AOI (with 10km buffer — ShorelineMonitor transect points sit
      # offshore of the AOI polygon; 1km was too tight for coastal AOIs whose
      # western edge stops at the shore rather than extending over water).
      bar_sf <- bar_sf[st_intersects(bar_sf, aoi %>% buffer(10000) %>% st_as_sf(), sparse = FALSE)[, 1], ]
      bar_sf
    }

    # --- Helper: save bar_sf to gpkg + fgb ---
    save_bars <- function(bar_sf, suffix) {
      if (nrow(bar_sf) == 0) {
        message("No shoreline transects found within AOI for ", suffix, " — skipping.")
        return(invisible(NULL))
      }
      gpkg_path <- file.path(spatial_dir, paste0(city_string, "_", suffix, ".gpkg"))
      fgb_path  <- file.path(spatial_dir, paste0(city_string, "_", suffix, ".fgb"))
      st_write(bar_sf, gpkg_path, delete_dsn = TRUE, quiet = TRUE)
      if (file.exists(fgb_path)) file.remove(fgb_path)
      st_write(bar_sf, fgb_path, quiet = TRUE)
      message("Saved ", nrow(bar_sf), " transect bars to: ", basename(fgb_path))
    }

    # === 1. Snap mode: snapped to AOI boundary ===
    message("\n--- Building shoreline_snap (snapped to AOI) ---")
    bars_snap <- build_bars(snapped_coords, tangent_source = "aoi_edge")
    save_bars(bars_snap, "shoreline_snap")

    # === 2. Baseline mode: raw transect points ===
    message("\n--- Building shoreline_baseline (raw transect points) ---")
    bars_baseline <- build_bars(coords_raw, tangent_source = "transect")
    save_bars(bars_baseline, "shoreline_baseline")

    # Build transect coastline as a buffered polygon (grey band along coast)
    # Split lines when consecutive points jump > max_gap to avoid cross-island lines
    max_gap <- 0.005  # ~500m
    all_segments <- list()
    for (grp in groups) {
      idx <- which(shoreline$box_group == grp)
      if (length(idx) < 2) next
      pts <- coords_raw[idx, ]
      dists <- sqrt(rowSums(diff(pts)^2))
      seg_ids <- cumsum(c(TRUE, dists > max_gap))
      for (sid in unique(seg_ids)) {
        seg_idx <- which(seg_ids == sid)
        if (length(seg_idx) >= 2) all_segments <- c(all_segments, list(st_linestring(pts[seg_idx, ])))
      }
    }

    if (length(all_segments) > 0) {
      coast_lines <- st_sf(geometry = st_sfc(all_segments, crs = 4326))
      st_write(coast_lines, file.path(spatial_dir, paste0(city_string, "_transect_coastline.gpkg")),
               delete_dsn = TRUE, quiet = TRUE)
      fgb_coast <- file.path(spatial_dir, paste0(city_string, "_transect_coastline.fgb"))
      if (file.exists(fgb_coast)) file.remove(fgb_coast)
      st_write(coast_lines, fgb_coast, quiet = TRUE)
      message("Saved transect coastline lines")
    }
  }
}
