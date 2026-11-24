#### Gather City Scan content into a nested content_list ########################
# Shared content backbone, sourced by BOTH:
#   - web   : publish/index.qmd  (flattens content_list for OJS + writes content.json)
#   - print : roundtrippt        (reads content.json, or sources this)
#
# Functions live in core/R (loaded via core/R/setup.R, sourced before this):
#   read_md, add_image_paths             -> core/R/fns-web.R
#   merge_lists, fuzzy_read              -> core/R/fns-util.R
#   double_space                         -> core/R/fns-text.R
#   collapse_with_line_breaks, add_markdown_formatting -> core/R/fns-text.R  (markdown dump only)

# Paths — point at the real city's files (override before sourcing if needed)
paths <- list()
paths$generic_text      <- here::here("source/generic-text.yml")
paths$manual_text       <- list.files(file.path(user_input_dir, "text-files"), pattern = "manual-text\\.md$", full.names = TRUE)[1]
paths$render_output_dir <- output_dir

# Combine generic text and city-specific text -> nested content_list
generic_text <- yaml::read_yaml(paths$generic_text) %>% rapply(double_space, how = "replace")
city_text    <- if (!is.na(paths$manual_text) && file.exists(paths$manual_text)) read_md(paths$manual_text) else NULL
content_list <- if (!is.null(city_text)) merge_lists(city_text, generic_text) else generic_text

# Attach map_path / plot_path to each slide (shared with print)
content_list <- add_image_paths(content_list, image_dir = paths$render_output_dir)
