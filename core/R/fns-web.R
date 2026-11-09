# =========================================================
# WEB & PDF CONTENT FUNCTIONS
# =========================================================

include_html_chart <- \(file) cat(str_replace_all(readLines(file), "\\s+", " "), sep="\n")

# ------- fill slides -------
fill_slide_content <- function(layer, extra_layers = NULL, title = NULL, slide_text = NULL) {
  if (!is.null(plots_html[[layer]])) {
    mapping_layers <- paste(
      map(c(extra_layers, layer), \(lay) layer_params[[lay]]$group_id),
      collapse = ";")
    if (is.null(slide_text)) slide_text <- slide_texts[[layer]]
    if (is.null(title)) title <- slide_text$title
    if (is.null(title)) title <- layer
    cat(glue("### {title}"))
    cat("\n")
    cat(glue('<div class="map-list" data-layers="{mapping_layers}"></div>'))
    cat("\n")
    # tryCatch(
    #   include_html_chart(fuzzy_read(file.path(output_dir, "plots/html"), slide_text$plot, paste)),
    #   error = \(e) return(""))
    plot_file <- fuzzy_read(charts_dir, slide_text$plot %||% "NO PLOT TO SEARCH FOR", paste)
    if (!is.na(plot_file)) cat(glue('<img style="max-width:95%" src="{plot_file}">\n\n\n'))
    print_slide_text(slide_text)
  }
}

fill_slide_content_pdf <- function(layer, map_name = NULL, title = NULL, slide_text = NULL) {
  if (is.null(map_name)) map_name <- layer
  map_file <- file.path(styled_maps_dir, paste0(map_name, ".png"))
  if (file.exists(map_file)) {
    if (is.null(slide_text)) slide_text <- slide_texts[[layer]]
    if (is.null(title)) title <- slide_text$title
    if (is.null(title)) title <- layer
    cat(glue("### {title}"))
    cat("\n")
    # cat(glue('<div class="map-list" data-static-map="{layer}"></div>'))
    cat(glue('<p class="map"><img src="{map_file}"></p>'))
    cat("\n")
    # tryCatch(
    #   include_html_chart(fuzzy_read(file.path(output_dir, "plots/html"), slide_text$plot, paste)),
    #   error = \(e) return(""))
    # print_slide_text(slide_text)

    cat('<div class="takeaways-method">\n')
    plot_file <- fuzzy_read(charts_dir, slide_text$plot %||% "NO PLOT TO SEARCH FOR", paste)
    if (!is.na(plot_file)) cat(glue('<p class="side-chart"><img src="{plot_file}"></p>'))
    cat("\n")
    if (!is.null(slide_text$takeaways)) {
    print_md(slide_text$takeaways, div_class = "takeaways")
    cat("\n")
  }
  if (!is.null(slide_text$method)) {
    print_md(slide_text$method, div_class = "method")
    cat("\n")
  }
    cat('</div>\n')
    print_md(slide_text$footnote %||% "", div_class = "footnote")
  # if (!is.null(slide$footnote)) print_md(slide$footnote %||% "", div_class = "footnote")
  }
}

# ---------- Read MD ----------
read_md <- function(file) {
  md <- readLines(file)
  instruction_lines <- 1:grep("CITY CONTENT BEGINS HERE", md)
  mddf <- tibble(text = md[-instruction_lines]) %>%
    mutate(
      section = case_when(str_detect(text, "^//// ") ~ str_extract(text, "^/+ (.*)$", group = T), T ~ NA_character_),
      slide = case_when(str_detect(text, "^// ") ~ str_extract(text, "^/+ (.*)$", group = T), T ~ NA_character_),
      .before = 1) %>%
    tidyr::fill(section) %>% 
    { lapply(na.omit(unique(.$section)), \(sect, df) {
        df <- filter(df, section == sect) %>%
          tidyr::fill(slide, .direction = "down") %>%
          filter(!(slide != lead(slide) & text == "")) %>%
          filter(!str_detect(text, "^/") & !str_detect(text, "^----"))
        while (df$text[1] == "" & nrow(df) > 1) df <- df[-1,]
        while (tail(df$text, 1) == "" & nrow(df) > 1) df <- head(df, -1)
        return(df)
    }, df = .) } %>%
    bind_rows() #%>%
    # Do I want to remove header lines? For now, no
    # filter(!str_detect(text, "^#"))

  # Remove empty lines
  no_slide <- filter(mddf, is.na(slide))
  if (nrow(no_slide) > 0) {
    warning(paste0(
      "There are", nrow(no_slide), "lines with no slide name:\n\n",
      paste(knitr::kable(mutate(no_slide, .keep = "none", section, text = substr(text, 1, 25))), collapse = "\n")))
    mddf <- filter(mddf, !is.na(slide))
  }
  text_list <- sapply(unique(mddf$section), function(sect) {
    section_df <- filter(mddf, section == sect)
    section_list <- sapply(c(unique(section_df$slide)), function(s) {
      if (s == "empty") return (NULL)
      slide_text <- filter(section_df, slide == s)$text

      # Parse :::footnote blocks
      footnote_start <- which(str_detect(slide_text, "^:::footnote"))
      footnote_end <- which(str_detect(slide_text, "^:::$"))

      if (length(footnote_start) > 0 && length(footnote_end) > 0) {
        footnote_lines <- c()
        takeaway_lines <- slide_text

        # Process each footnote block (in reverse to maintain indices)
        for (i in rev(seq_along(footnote_start))) {
          start_idx <- footnote_start[i]
          end_idx <- footnote_end[footnote_end > start_idx][1]
          if (!is.na(end_idx)) {
            if (end_idx > start_idx + 1) {
              footnote_lines <- c(slide_text[(start_idx + 1):(end_idx - 1)], footnote_lines)
            }
            takeaway_lines <- takeaway_lines[-c(start_idx:end_idx)]
          }
        }

        # Clean up empty lines
        while (length(takeaway_lines) > 0 && takeaway_lines[1] == "") takeaway_lines <- takeaway_lines[-1]
        while (length(takeaway_lines) > 0 && tail(takeaway_lines, 1) == "") takeaway_lines <- head(takeaway_lines, -1)

        return(list(
          takeaways = if (length(takeaway_lines) > 0) takeaway_lines else NULL,
          footnote = if (length(footnote_lines) > 0) paste(footnote_lines, collapse = " ") else NULL
        ))
      } else {
        return(list(takeaways = slide_text))
      }
    }, simplify = F)
    return(section_list)
  }, simplify = F)
  return(text_list)
}


prepare_html <- \(in_file, out_file, css_file) {
  library(rvest)
  library(xml2)
  pdf <- read_html(in_file)
  # browser()
  stylesheet_nodes <- html_elements(pdf, "link[rel=stylesheet]")
  xml_attr(stylesheet_nodes[1], "href") <- css_file
  xml2::xml_remove(stylesheet_nodes[-1])
  setup_node <- html_elements(pdf, ".setup")
  xml2::xml_remove(setup_node)
  # Do I want to remove all div.cell? NO
  # xml2::xml_remove(html_nodes(pdf, ".cell"))
  ojs_script_node <- html_element(pdf, "script[src='index_files/libs/quarto-ojs/quarto-ojs-runtime.js']")
  xml2::xml_remove(ojs_script_node)
  module_nodes <- html_elements(pdf, "script[type=module]")
  xml2::xml_remove(module_nodes)
  ojs_module_node <- html_element(pdf, "script[type=ojs-module-contents]")
  xml2::xml_remove(ojs_module_node)
  js_nodes <- html_elements(pdf, "script[type='text/javascript']")
  xml2::xml_remove(js_nodes)
  json_node <- html_elements(pdf, "script[type='application/json']")
  xml2::xml_remove(json_node)
  nav_node <- html_element(pdf, ".navigation")
  xml2::xml_remove(nav_node)
  xml2::xml_remove(html_nodes(pdf, "script#quarto-html-after-body"))
  write_html(pdf, out_file)
}

# ---------- Print ----------
print_md <- function(x, div_class = NULL) {
  if (!is.null(div_class)) cat(":::", div_class, "\n")
  cat(x, sep = "\n")
  if (!is.null(div_class)) cat(":::\n")
}

print_slide_text <- function(slide) {
  if (!is.null(slide$takeaways)) {
    print_md(slide$takeaways, div_class = "takeaways")
    cat("\n")
  }
  if (!is.null(slide$method)) {
    print_md(slide$method, div_class = "method")
    cat("\n")
  }
  print_md(slide$footnote %||% "", div_class = "footnote")
}



# Ported from roundtrippt gather-content.R (shared web+print content backbone).
# Attaches map_path/plot_path to each slide in the content list.
add_image_paths <- function(slide_texts, image_dir) {
  slide_texts %>%
    modify(\(section) {
      imodify(section, \(slide, name) {
        # Declare path to static map file
        # Probably better for generic-text.yml to have a map boolean
        map_path <- file.path(image_dir, "maps", paste0(name, ".png"))
        if (file.exists(map_path)) slide$map_path <- map_path
        # Declare path to plot file
        if ("plot" %in% names(slide)) {
          plot_path <- fuzzy_read(file.path(image_dir, "plots"), slide$plot, paste)
          if (!is.na(plot_path)) slide$plot_path <- plot_path
        }
        return(slide)
      })
    })
}
