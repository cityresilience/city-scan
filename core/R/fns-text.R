# =========================================================
# TEXT FUNCTIONS & HELPERS
# =========================================================

# ---------- Helpers ----------
duplicated2way <- duplicated_all <- function(x) {
  duplicated(x) | duplicated(x, fromLast = T)
}

tolatin <- function(x) stringi::stri_trans_general(x, id = "Latin-ASCII")

double_space <- function(x) {
  str_replace(x, "\\n", "\n\n")
}

break_lines <- function(x, width = 20, newline = "<br>") {
  if (is.null(x)) return(NULL)
  # Consider using stringr::str_wrap() instead
  str_split_1(x, paste0(newline, "|\\\n|<br>")) %>%
    str_replace_all(paste0("(.{", width, "}[^\\s]*)\\s"), paste0("\\1", newline)) %>%
    paste(collapse = newline)
}

format_title <- function(title, subtitle, width = 20) { # transparencies.R is maybe better suited for 24
  if ((is.null(title) || title == "") & (is.null(subtitle) || subtitle == "")) return(NULL)
  title_broken <- paste0(break_lines(title, width = width, newline = "<br>"), "<br>")
  if (is.null(subtitle) || subtitle == "") return(title_broken)
  subtitle_broken <- break_lines(subtitle, width = width, newline = "<br>")
  formatted_title <- paste0(title_broken, "<br><em>", subtitle_broken, "</em><br>")
  return(formatted_title)
}


# ---------- Paste ----------
paste_and <- function(v) {
    if (length(v) == 1) {
    string <- paste(v)
  } else {
    # l[1:(length(l)-1)] %>% paste(collapse = ", ")
    paste(head(v, -1), collapse = ", ") %>%
    paste("and", tail(v, 1))
  }
}

paste_bold <- function(x) {
  # Handle NA/NULL input
  if (is.null(x) || length(x) == 0 || all(is.na(x))) return("<b>NA</b>")

  # Handle vector input - collapse to comma-separated string
  if (length(x) > 1) x <- paste(x, collapse = ", ")

  # Convert to character if needed
  x <- as.character(x)
  if (is.na(x) || x == "") return("<b>NA</b>")

  # Check if it looks like a list of items (commas/and between words, not number formatting)
  # This pattern detects number formatting like "3,603,026"
  has_number_format <- grepl("\\d{1,3}(,\\d{3})+", x)
  has_list_pattern <- grepl(",| and ", x) && grepl("[a-zA-Z]", x)

  if (has_list_pattern && !has_number_format) {
    # Split by comma and " and " only if it's a word list, not a formatted number
    parts <- strsplit(x, ",| and ")[[1]]
    parts_bold <- paste0("<b>", trimws(parts), "</b>")
    n_commas <- length(gregexpr(",", x)[[1]])

    if (n_commas > 0 && grepl(" and ", x)) {
      # Has both commas and "and"
      paste(paste(head(parts_bold, -1), collapse = ", "), "and", tail(parts_bold, 1))
    } else if (n_commas > 0) {
      # Only commas
      paste(parts_bold, collapse = ", ")
    } else {
      # Only "and"
      paste(parts_bold, collapse = " and ")
    }
  } else {
    # Simple case: no list pattern or has number formatting, just bold everything
    paste0("<b>", x, "</b>")
  }
}


# ---------- Print ----------

print_paged_df <- function(...) {
  cat(rmarkdown:::print.paged_df(rmarkdown::paged_table(...)))
}

print_text <- function(x, linebreaks = 2) {
  cat(paste0(x, "\n", paste(rep("<br>", linebreaks), collapse = ""), "\n"))
}


label_maker <- function(x, levels = NULL, labels = NULL, suffix = NULL) {
  # if (!is.null(labels)) {
  #   index <- sapply(x, \(.x) which(levels == .x)) # Using R's new lambda functions!
  #   x <- labels[index]
  # }
  if (is.numeric(x)) {
    x <- signif(x, 6)
  }
  if (!is.null(suffix)) {
    x <- paste0(x, suffix)
  }
  return(x)
  }
