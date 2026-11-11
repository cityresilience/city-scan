// PLOT HELPER FUNCTIONS - plot-helpers.js
// reusable calculations for all d3 plots



// =====================================================
// 1. CONSTANTS
// =====================================================

// PLOT_BASE =================================
export const PLOT_BASE = {
    HEIGHT: 600,
    WIDTH: 800,
    BAR_WIDTH: 100
  };
  
// BASE_FONT_SIZES ===========================
export const BASE_FONT_SIZES = {
  TITLE: 18,
  SUBTITLE: 16,
  AXIS_LABEL: 11,
  Y_AXIS_TICK: 10,
  BAR_LABEL: 10,
  CAPTION: 9,
  X_AXIS_TICK: 9,
  ANNOTATION: 9
};
  

// =====================================================
// 2. CORE TEXT UTILITIES
// =====================================================
// (pure text measurement/wrapping used everywhere)

// wrapText ==================================
/**
  * wrap text into multiple lines based on max width
  * @param {string} text - text to wrap
  * @param {number} maxWidth - maximum width in pixels
  * @param {string} font - font specification (e.g., "12px system-ui")
  * @returns {Array} array of text lines
  */
export function wrapText(text, maxWidth, font) {
  const canvas = document.createElement("canvas");
  const context = canvas.getContext("2d");
  context.font = font;
  
  const words = text.split(" ");
  const lines = [];
  let currentLine = "";
    
  words.forEach(word => {
    const testLine = currentLine + (currentLine ? " " : "") + word;
    const metrics = context.measureText(testLine);
      
    if (metrics.width > maxWidth && currentLine) {
      lines.push(currentLine);
      currentLine = word;
    } else {
      currentLine = testLine;
    }
  });
  
  if (currentLine) {
    lines.push(currentLine);
  }
  
  return lines;
}

// wrapBarLabel ===============================
/**
 * wrap bar chart x-axis labels intelligently
 * - splits ranges at "-" if they don't fit
 * - keeps short labels on one line
 * - handles negative numbers correctly
 * - handles word wrapping with spaces correctly
 * @param {string} text - the label text (e.g., "0.015-0.14")
 * @param {number} barWidth - available width for the label
 * @param {string} font - font specification (e.g., "10px system-ui")
 * @returns {array} array of lines to display
 */
export function wrapBarLabel(text, barWidth, font) {
  const canvas = document.createElement('canvas');
  const context = canvas.getContext('2d');
  context.font = font;
  
  const fullWidth = context.measureText(text).width;
  
  // (if it fits, return as-is)
  if (fullWidth <= barWidth) {
    return [text];
  }
 
  // handle ranges (contains "-")
  if (text.includes('-') && !text.includes(' ')) {
    const parts = text.split('-');
    
    // handle negative numbers: "-1-0.015" -> ["-1", "0.015"]
    if (parts[0] === '') {
      const line1 = '-' + parts[1];
      const line2 = parts.slice(2).join('-');
      return [line1, line2];
    }
    
    // normal range: "0.015-0.14" -> ["0.015", "0.14"]
    const midPoint = Math.floor(parts.length / 2);
    const line1 = parts.slice(0, midPoint).join('-');
    const line2 = parts.slice(midPoint).join('-');
    
    return [line1, line2];
  }
  
  // handle word wrapping (contains spaces)
  if (text.includes(' ')) {
    const words = text.split(' ');
    const lines = [];
    let currentLine = words[0];
    
    for (let i = 1; i < words.length; i++) {
      const testLine = currentLine + ' ' + words[i];
      const testWidth = context.measureText(testLine).width;
      
      if (testWidth <= barWidth) {
        currentLine = testLine;
      } else {
        lines.push(currentLine);
        currentLine = words[i];
      }
    }
    lines.push(currentLine);
    
    return lines;
  }
  
  // fallback: single long word (no spaces or dashes)
  return [text];
}

// wrapLineChartLabel =========================
/**
   * wrap line chart x-axis labels (e.g., "Jul 2016" -> two lines)
   * returns array of lines, just like wrapBarLabel
   * @param {string} text - the label text (e.g., "Jul 2016")
   * @param {number} maxWidth - available width for the label
   * @param {string} font - font specification (e.g., "10px system-ui")
   * @returns {array} array of lines to display
   */
export function wrapLineChartLabel(text, maxWidth, font) {
  const canvas = document.createElement('canvas');
  const context = canvas.getContext('2d');
  context.font = font;
  
  const fullWidth = context.measureText(text).width;
  
  // (if it fits, return as-is)
  if (fullWidth <= maxWidth) {
    return [text];
  }
  
  // (split on spaces (e.g., "Jul 2016" -> ["Jul", "2016"]))
  if (text.includes(' ')) {
    return text.split(' ');
  }
  
  // (fallback: return as single line)
  return [text];
}

// wrapShortLabel =============================
/**
 * wrap a single word or short phrase to fit within a width
 * (intelligently breaks long words if needed)
 * @param {string} text - text to wrap
 * @param {number} maxWidth - maximum width in pixels
 * @param {string} font - font specification (e.g., "10px system-ui")
 * @returns {Array} array of lines to display
 */
export function wrapShortLabel(text, maxWidth, font) {
  const canvas = document.createElement('canvas');
  const context = canvas.getContext('2d');
  context.font = font;
  
  const fullWidth = context.measureText(text).width;
  
  // (if it fits, return as-is)
  if (fullWidth <= maxWidth) {
    return [text];
  }
  
  // (if it doesn't fit, try to break at syllables or reasonable points)
  // (for "Deforested", for example, try common break points)
  const breakPoints = [
    [text], // (try full word first)
    [text.slice(0, Math.ceil(text.length / 2)), text.slice(Math.ceil(text.length / 2))], // (break in middle of word)
    [text.slice(0, 5), text.slice(5)], // (break at character 5 of word)
    [text.slice(0, 4), text.slice(4)], // (break at character 4 of word)
    [text.slice(0, 3), text.slice(3)]  // (break at character 3 of word)
  ];
  
  // (find the first break point where both parts fit)
  for (const parts of breakPoints) {
    const allFit = parts.every(part => context.measureText(part).width <= maxWidth);
    if (allFit) {
      return parts;
    }
  }
  
  // (fallback: just return the original text)
  return [text];
}


// =====================================================
// 3. FONT SIZE CALCULATIONS
// =====================================================

// calculateFontSizes =========================
/**
  * calculate all font sizes proportionally based on plot dimensions
  * @param {number} width - plot width in pixels
  * @param {number} height - plot height in pixels
  * @returns {Object} font sizes for all text elements
  */
export function calculateFontSizes(width, height) {
  const heightScale = height / PLOT_BASE.HEIGHT;
  const widthScale = width / PLOT_BASE.WIDTH;
    
  return {
    title: Math.max(10, Math.min(24, BASE_FONT_SIZES.TITLE * heightScale)),
    subtitle: Math.max(9, Math.min(20, BASE_FONT_SIZES.SUBTITLE * heightScale)),
    axisLabel: Math.max(8, Math.min(14, BASE_FONT_SIZES.AXIS_LABEL * heightScale)),
    yAxisTick: Math.max(5, Math.min(12, BASE_FONT_SIZES.Y_AXIS_TICK * heightScale)),
    xAxisTick: Math.max(5, Math.min(11, BASE_FONT_SIZES.X_AXIS_TICK * heightScale)),
    barLabel: Math.max(5, Math.min(13, BASE_FONT_SIZES.BAR_LABEL * Math.min(heightScale, widthScale))),
    caption: Math.max(6, Math.min(11, BASE_FONT_SIZES.CAPTION * heightScale)),
    annotation: Math.max(6, Math.min(11, BASE_FONT_SIZES.ANNOTATION * heightScale))
  };
}

// calculateLineHeights =======================
/**
  * calculate line heights for multi-line text
  * @param {Object} fontSizes - font sizes object from calculateFontSizes
  * @returns {Object} line heights for all text elements
  */
export function calculateLineHeights(fontSizes) {
  return {
    title: Math.max(12, fontSizes.title * 1.2),
    subtitle: Math.max(10, fontSizes.subtitle * 1.2),
    axisLabel: Math.max(10, fontSizes.axisLabel * 1.2),
    caption: Math.max(6, fontSizes.caption * 1.2)
  };
}

// calculateXAxisTickSize =====================
/**
  * calculate x-axis tick label size based on available bar width
  * @param {number} barWidth - width of bars in pixels
  * @returns {number} font size in pixels
  */
export function calculateXAxisTickSize(barWidth) {
  const barWidthScale = barWidth / PLOT_BASE.BAR_WIDTH;
  return Math.max(5, Math.min(11, BASE_FONT_SIZES.X_AXIS_TICK * barWidthScale));
}


// =====================================================
// 4. MARGIN & LAYOUT CALCULATIONS
// =====================================================

// calculateMargins ===========================
/**
  * calculate margins dynamically based on plot size and text dimensions
  * @param {number} width - plot width
  * @param {number} height - plot height
  * @param {Object} textDimensions - object with titleHeight, subtitleHeight, etc.
  * @returns {Object} margin object with top, right, bottom, left
  */
export function calculateMargins(width, height, textDimensions = {}) {
  const heightScale = height / PLOT_BASE.HEIGHT;
  const widthScale = width / PLOT_BASE.WIDTH;
    
  const {
    titleHeight = 0,
    subtitleHeight = 0,
    xAxisLabelHeight = 0,
    captionHeight = 0,
    yAxisLabelWidth = 0
  } = textDimensions;
    
  const topMargin = Math.max(
    50, 
    15 * heightScale + titleHeight + subtitleHeight + 10 * heightScale
  );
    
  const bottomMargin = Math.max(
    60,
    20 * heightScale + xAxisLabelHeight + captionHeight + 25 * heightScale
  );
    
  const leftMargin = Math.max(
    60,
    30 * widthScale + yAxisLabelWidth + 20 * widthScale
  );
    
  const rightMargin = Math.max(20, width * 0.02);
    
  return {
    top: topMargin,
    right: rightMargin,
    bottom: bottomMargin,
    left: leftMargin
  };
}

// calculatePyramidMargins ====================
/**
  * calculate population pyramid margins
  * @param {number} width - plot width
  * @param {number} height - plot height
  * @param {Object} textDimensions - text dimension object from calculateMargins
  * @returns {Object} margin object optimized for pyramids
  */
export function calculatePyramidMargins(width, height, textDimensions) {
  const baseMargins = calculateMargins(width, height, textDimensions);
  
  // (pyramids need more space on left/right for percentage labels)
  return {
    ...baseMargins,
    left: Math.max(60, width * 0.06, baseMargins.left),
    right: Math.max(60, width * 0.06, baseMargins.right)
  };
}


// =====================================================
// 5. TEXT POSITIONING
// =====================================================

// getTitleY ==================================
/**
  * calculate y-position for title
  * @param {number} height - plot height
  * @param {number} heightScale - height scale factor
  * @returns {number} y position in pixels
  */
export function getTitleY(height, heightScale) {
  return Math.max(15, 20 * heightScale);
}

// getSubtitleY ===============================
/**
  * calculate y-position for subtitle (below title)
  * @param {number} titleY - title y position
  * @param {number} titleLines - number of title lines
  * @param {number} titleLineHeight - title line height
  * @param {number} heightScale - height scale factor
  * @returns {number} y position in pixels
  */
export function getSubtitleY(titleY, titleLines, titleLineHeight, heightScale) {
  return titleY + (titleLines * titleLineHeight) + (5 * heightScale);
}

// getXAxisLabelY =============================
/**
  * calculate y-position for x-axis label
  * @param {number} height - plot height
  * @param {number} captionHeight - total caption height
  * @param {number} heightScale - height scale factor
  * @returns {number} y position in pixels
  */
export function getXAxisLabelY(height, captionHeight, heightScale) {
  return height - captionHeight - (15 * heightScale);
}

// getCaptionY ================================
/**
  * calculate y-position for caption
  * @param {number} height - plot height
  * @param {number} heightScale - height scale factor
  * @returns {number} y position in pixels
  */
export function getCaptionY(height, heightScale) {
  return height - (10 * heightScale);
}

// getYAxisLabelY =============================
/**
  * calculate y-position for y-axis label
  * @param {number} widthScale - width scale factor
  * @returns {number} y position in pixels
  */
export function getYAxisLabelY(widthScale) {
  return Math.max(10, 15 * widthScale);
}


// =====================================================
// 6. SCALE HELPERS
// =====================================================

// calculateYTicks ============================
/**
  * calculate number of y-axis ticks based on height
  * @param {number} innerHeight - inner plot height
  * @returns {number} number of ticks
  */
export function calculateYTicks(innerHeight) {
  return Math.max(4, Math.min(10, Math.floor(innerHeight / 80)));
}

// addDomainPadding ===========================
/**
  * add padding to a domain for better visualization
  * @param {Array} domain - [min, max] domain array
  * @param {number} topPadding - padding percentage at top (default: 0.02 = 2%)
  * @param {number} bottomPadding - padding percentage at bottom (default: 0.005 = 0.5%)
  * @returns {Array} padded domain [min, max]
  */
export function addDomainPadding(domain, topPadding = 0.02, bottomPadding = 0.005) {
  const [min, max] = domain;
  return [
    min * (1 - bottomPadding),
    max * (1 + topPadding)
  ];
}


// =====================================================
// 7. ANNOTATION HELPERS
// =====================================================

// calculateAnnotationStrokeWidth =============
/**
  * calculate annotation font size based on plot width
  * @param {number} width - plot width in pixels
  * @returns {number} font size in pixels
  */
export function calculateAnnotationStrokeWidth(width) {
  return Math.max(1, Math.min(2, width / 500));
}

// addHorizontalAnnotation ====================
/**
  * add a horizontal threshold line with label annotation
  * @param {d3.selection} g - svg group to add annotation to
  * @param {number} yValue - y-axis value for the line
  * @param {d3.scale} yScale - y-scale function
  * @param {number} innerWidth - width of plot area
  * @param {string} label - text label for the annotation
  * @param {number} fontSize - font size for label
  * @param {number} strokeWidth - stroke width for line
  * @param {string} color - color for line and text (default: "gray")
  */
export function addHorizontalAnnotation(g, yValue, yScale, innerWidth, label, fontSize, strokeWidth, color = "gray") {
  g.append("line")
    .attr("class", "plot-annotation-line")
    .attr("x1", 0)
    .attr("x2", innerWidth)
    .attr("y1", yScale(yValue))
    .attr("y2", yScale(yValue))
    .attr("stroke", color)
    .attr("stroke-width", strokeWidth)
    .attr("stroke-dasharray", "5,5");
   
  g.append("text")
    .attr("class", "plot-annotation-text")
    .attr("x", innerWidth / 2)
    .attr("y", yScale(yValue) + fontSize - 10)
    .attr("text-anchor", "middle")
    .attr("fill", color)
    .style("font-size", `${fontSize}px`)
    .style("font-weight", "bold")
    .text(label);
}


// =====================================================
// 8. LEGEND HELPERS
// =====================================================

// shouldShowLegend ===========================
/**
  * calculate if legend should be visible based on plot size
  * @param {number} width - plot width
  * @param {number} height - plot height
  * @returns {boolean} whether legend should be shown
  */
export function shouldShowLegend(width, height) {
  // hide legend if width is too small (< 400px) or height is too small (< 300px)
  return width >= 400 && height >= 300;
}

// calculateLegendSizing ======================
/**
  * calculate legend font size and spacing based on plot dimensions
  * @param {number} width - plot width
  * @param {number} height - plot height
  * @returns {Object} legend styling parameters
  */
export function calculateLegendSizing(width, height) {
  const widthScale = width / PLOT_BASE.WIDTH;
  const heightScale = height / PLOT_BASE.HEIGHT;
  const avgScale = (widthScale + heightScale) / 2;
    
  return {
    fontSize: Math.max(10, Math.min(14, 12 * avgScale)),
    lineWidth: Math.max(15, Math.min(25, 20 * avgScale)),
    spacing: Math.max(18, Math.min(26, 22 * avgScale)),
    strokeWidth: Math.max(1.5, Math.min(3, 2 * avgScale))
  };
}

// addLegend ==================================
/**
  * add a legend to the svg
  * @param {d3.selection} svg - svg element to add legend to
  * @param {Array} legendData - array of legend items: [{label, color, dashed?, shape?}]
  *   - shape: 'line' (default), 'circle', 'square'
  *   - dashed: true/false (only for lines)
  * @param {number} width - plot width
  * @param {number} height - plot height
  * @param {string} position - position: 'top-right' (default), 'top-left', 'bottom-right', 'bottom-left'
  */
export function addLegend(svg, legendData, width, height, position = 'top-right') {
  // check if legend should be shown
  if (!shouldShowLegend(width, height)) {
    return; // don't render legend
  }
  
  const sizing = calculateLegendSizing(width, height);
  
  // calculate position based on parameter
  let legendX, legendY;
  const margin = 20;
  
  switch(position) {
    case 'top-left':
      legendX = margin;
      legendY = 25;
      break;
    case 'bottom-right':
      legendX = width - 160;
      legendY = height - (legendData.length * sizing.spacing) - margin;
      break;
    case 'bottom-left':
      legendX = margin;
      legendY = height - (legendData.length * sizing.spacing) - margin;
      break;
    case 'top-right':
    default:
      legendX = width - 160;
      legendY = 25;
      break;
  }
  
  const legendGroup = svg.append("g")
    .attr("class", "plot-legend");
  
  legendData.forEach((item, i) => {
    const legendItem = legendGroup.append("g")
      .attr("transform", `translate(${legendX}, ${legendY + i * sizing.spacing})`);
    
    // determine shape type (default to 'line' for backward compatibility)
    const shape = item.shape || 'line';
    
    if (shape === 'line') {
      // line sample (for line charts)
      legendItem.append("line")
        .attr("x1", 0)
        .attr("x2", sizing.lineWidth)
        .attr("y1", 0)
        .attr("y2", 0)
        .attr("stroke", item.color)
        .attr("stroke-width", sizing.strokeWidth)
        .attr("stroke-dasharray", item.dashed ? "4,4" : "0");
    } else if (shape === 'circle') {
      // circle sample (for bubble/scatter plots)
      legendItem.append("circle")
        .attr("cx", sizing.lineWidth / 2)
        .attr("cy", 0)
        .attr("r", 6)
        .attr("fill", item.color)
        .attr("fill-opacity", 0.7)
        .attr("stroke", "black")
        .attr("stroke-width", 1);
    } else if (shape === 'square') {
      // square sample (for other chart types)
      legendItem.append("rect")
        .attr("x", 0)
        .attr("y", -6)
        .attr("width", 12)
        .attr("height", 12)
        .attr("fill", item.color)
        .attr("fill-opacity", 0.7)
        .attr("stroke", "black")
        .attr("stroke-width", 1);
    }
    
    // label text
    legendItem.append("text")
      .attr("x", sizing.lineWidth + 5)
      .attr("y", 0)
      .attr("dy", "0.32em")
      .attr("font-size", `${sizing.fontSize}px`)
      .attr("font-family", "system-ui")
      .attr("fill", "currentColor")
      .text(item.label);
  });
}


// =====================================================
// 10. BAR CHART HELPERS (vertical bar charts)
// =====================================================

// calculateBarChartDomain ====================
/**
  * calculate nice domain maximum for horizontal bar charts with variable data
  * @param {number} maxValue - maximum data value
  * @returns {number} nice rounded domain max
  */
export function calculateBarChartDomain(maxValue) {
  const tickStep = Math.ceil(maxValue / 10) || 1;
  const lastTick = Math.ceil(maxValue / tickStep) * tickStep;
  return lastTick;
}

// calculateDynamicScale ======================
/**
  * calculate dynamic scale factor based on plot width
  * @param {number} width - plot width
  * @param {number} baseWidth - base width for scaling (default: 800)
  * @param {number} minScale - minimum scale factor (default: 0.6)
  * @param {number} maxScale - maximum scale factor (default: 1.5)
  * @returns {number} dynamic scale factor
  */
export function calculateDynamicScale(width, baseWidth = 800, minScale = 0.6, maxScale = 1.5) {
  const scaleFactor = width / baseWidth;
  return Math.max(minScale, Math.min(maxScale, scaleFactor));
}

// shouldShowBarLabels ========================
/**
  * determine if horizontal bar chart should show value labels
  * @param {number} width - plot width
  * @param {number} minWidth - minimum width to show labels (default: 500)
  * @returns {boolean} whether to show value labels
  */
export function shouldShowBarLabels(width, minWidth = 500) {
  return width >= minWidth;
}

// calculateBarChartMargins ===================
/**
  * calculate adjusted margins for horizontal bar charts
  * @param {Object} baseMargin - base margin object from calculateMargins
  * @param {number} dynamicScale - dynamic scale factor
  * @param {boolean} showValueLabels - whether value labels are shown
  * @returns {Object} adjusted margin object
  */
export function calculateBarChartMargins(baseMargin, dynamicScale, showValueLabels) {
  return {
    top: baseMargin.top,
    right: showValueLabels ? Math.max(baseMargin.right, 180 * dynamicScale) : Math.max(baseMargin.right, 20),
    bottom: baseMargin.bottom,
    left: Math.max(baseMargin.left, 120 * dynamicScale)
  };
}

// calculateYAxisLabelBox =====================
/**
  * calculate y-axis label foreignObject dimensions for horizontal bar charts
  * @param {number} marginLeft - left margin size
  * @param {number} bandwidth - y-scale bandwidth (bar height)
  * @param {number} padding - space to leave from bars (default: 30)
  * @returns {Object} object with width, height, x, y for foreignObject
  */
export function calculateYAxisLabelBox(marginLeft, bandwidth, padding = 30) {
  return {
    width: marginLeft - padding,
    height: bandwidth * 1.5, // allow space for wrapping
    x: -(marginLeft - padding),
    y: -bandwidth * 0.75 // center the taller box
  };
}

// calculateBarChartLabelFontSize =============
/**
  * calculate font size for horizontal bar chart axis labels
  * @param {number} dynamicScale - dynamic scale factor
  * @returns {number} Font size in pixels
  */
export function calculateBarChartLabelFontSize(dynamicScale) {
  return Math.max(5, Math.min(14, 8.5 * dynamicScale));
}

// calculateTimePeriodDomain ==================
/**
  * calculate domain maximum for time-period horizontal bar charts
  * @param {Array} data - data array
  * @param {string} timeField - field name for time period (e.g., 'week', 'month')
  * @returns {number} maximum value for the domain
  */
export function calculateTimePeriodDomain(data, timeField) {
  return Math.max(...data.map(d => d[timeField]));
}


// =====================================================
// 11. GROUPED BAR CHART HELPERS
// =====================================================

// calculateGroupedBarXTicks ==================
/**
  * calculate intelligent X-axis tick filtering for grouped bar charts with many categories
  * @param {Array} categories - array of all category labels (e.g., age brackets)
  * @param {number} innerWidth - available width for the plot
  * @param {number} bandwidth - width of each category band
  * @returns {Array} filtered array of categories to show as ticks
  */
export function calculateGroupedBarXTicks(categories, innerWidth, bandwidth) {
  const availableSpacePerCategory = bandwidth;
  let tickInterval;

  // (less aggressive filtering - keep more labels visible)
  if (availableSpacePerCategory < 20) {
    tickInterval = 2; // (show every 3rd category)
  } else {
    tickInterval = 1; // (show all categories)
  }

  return categories.filter((cat, index) => index % tickInterval === 0);
}

// calculateXAxisLabelRotation ================
/**
  * calculate rotation angle for x-axis labels based on available space
  * @param {number} bandwidth - width of each category band
  * @returns {number} rotation angle in degrees (0, -45, or -90)
  */
export function calculateXAxisLabelRotation(bandwidth) {
  if (bandwidth < 20) {
    return -45; // (vertical)
  } else {
    return 0; // (horizontal)
  }
}

// calculateRotatedLabelProperties ============
/**
  * calculate text anchor and offsets for rotated x-axis labels
  * @param {number} rotation - rotation angle in degrees
  * @returns {Object} {textAnchor, dx, dy}
  */
export function calculateRotatedLabelProperties(rotation) {
  if (rotation === -90) {
    return {
      textAnchor: "end",
      dx: "0em",
      dy: "0.3em"
    };
  } else if (rotation === -45) {
    return {
      textAnchor: "end",
      dx: "-0.5em",
      dy: "0.3em"
    };
  } else {
    return {
      textAnchor: "middle",
      dx: "0em",
      dy: "1em"
    };
  }
}

// createGroupedBarLegend =====================
/**
  * create simple legend data for grouped bar chart
  * @param {Array} groups - array of group names (e.g., ["female", "male"])
  * @param {d3.scaleOrdinal} colorScale - d3 color scale
  * @returns {Array} legend data array
  */
export function createGroupedBarLegend(groups, colorScale) {
  return groups.map(group => ({
    label: group,
    color: colorScale(group),
    shape: "square"
  }));
}


// =====================================================
// 11. LINE CHART HELPERS
// =====================================================

// calculateXAxisTickCount ====================
/**
  * calculate optimal number of x-axis ticks for line charts
  * prevents label overlap by limiting tick count based on available width
  * @param {number} innerWidth - available width for the plot
  * @param {number} minTicks - minimum number of ticks (default: 5)
  * @param {number} maxTicks - maximum number of ticks (default: 15)
  * @returns {number} optimal tick count
  */
export function calculateXAxisTickCount(innerWidth, minTicks = 4, maxTicks = 15) {
  // (assume each tick label needs ~50px of space to avoid overlap)
  const tickSpacing = 60;
  const maxPossibleTicks = Math.floor(innerWidth / tickSpacing);
  return Math.max(minTicks, Math.min(maxPossibleTicks, maxTicks));
}

// calculateLineChartXTicks ===================
/**
  * calculate intelligent x-axis tick count for line charts
  * @param {number} innerWidth - available width for the plot
  * @param {number} minTicks - minimum number of ticks (default: 5)
  * @param {number} maxTicks - maximum number of ticks (default: 15)
  * @returns {number} number of ticks to show
  */
export function calculateLineChartXTicks(innerWidth, minTicks = 5, maxTicks = 15) {
  const tickCount = Math.floor(innerWidth / 80);
  return Math.max(minTicks, Math.min(maxTicks, tickCount));
}

// calculateLineStrokeWidth ===================
/**
  * calculate dynamic line stroke width based on plot width
  * @param {number} width - plot width
  * @param {number} minWidth - minimum stroke width (default: 1.5)
  * @param {number} maxWidth - maximum stroke width (default: 3)
  * @returns {number} stroke width in pixels
  */
export function calculateLineStrokeWidth(width, minWidth = 1.5, maxWidth = 3) {
  return Math.max(minWidth, Math.min(maxWidth, width / 400));
}

// calculateLineDotRadius =====================
/**
  * calculate dynamic dot radius for line chart points
  * @param {number} width - plot width
  * @param {number} minRadius - minimum radius (default: 2)
  * @param {number} maxRadius - maximum radius (default: 4)
  * @returns {number} dot radius in pixels
  */
export function calculateLineDotRadius(width, minRadius = 2, maxRadius = 4) {
  return Math.max(minRadius, Math.min(maxRadius, width / 200));
}


// =====================================================
// 12. BUBBLE/SCATTER PLOT HELPERS
// =====================================================

// calculateBubbleRadiusRange =================
/**
  * calculate bubble radius range for scatter/bubble plots
  * @param {number} width - plot width
  * @returns {Array} [minRadius, maxRadius]
  */
export function calculateBubbleRadiusRange(width) {
  return [
    Math.max(3, Math.min(8, width / 150)),
    Math.max(15, Math.min(40, width / 25))
  ];
}

// calculateYearTicks =========================
/**
  * calculate year tick interval and values for time series plots
  * @param {number} startYear - starting year
  * @param {number} endYear - ending year
  * @param {number} width - plot width
  * @returns {Object} {interval, values}
  */
export function calculateYearTicks(startYear, endYear, width) {
  const tickInterval = Math.max(5, Math.min(10, Math.floor((width * 0.6) / 40)));
    
  // generate array of year values
  const values = [];
  for (let year = startYear; year <= endYear; year += tickInterval) {
    values.push(year);
  }
    
  return {
    interval: tickInterval,
    values: values
  };
}


// =====================================================
// 13. TREEMAP HELPERS
// =====================================================

// calculateTreemapLabelSize ==================
/**
  * calculate dynamic font size for treemap labels based on cell size and viewport
  * @param {number} rectWidth - width of the treemap cell
  * @param {number} plotWidth - total plot width
  * @param {number} minSize - minimum font size (default: 10)
  * @param {number} maxSize - maximum font size (default: 18)
  * @returns {number} calculated font size in pixels
  */
 export function calculateTreemapLabelSize(rectWidth, plotWidth, minSize = 10, maxSize = 18) {
  const baseFontSize = Math.max(minSize, Math.min(maxSize, rectWidth / 12));
  const viewportScale = Math.max(0.8, Math.min(1.4, plotWidth / 600));
  return baseFontSize * viewportScale;
}

// calculateTreemapPercentageSize =============
/**
  * calculate dynamic font size for treemap percentage labels
  * @param {number} rectWidth - width of the treemap cell
  * @param {number} plotWidth - total plot width
  * @returns {number} calculated font size in pixels
  */
export function calculateTreemapPercentageSize(rectWidth, plotWidth) {
  const baseFontSize = Math.max(7, Math.min(12, rectWidth / 12));
  const viewportScale = Math.max(0.8, Math.min(1.4, plotWidth / 600));
  return baseFontSize * viewportScale;
}

// shouldShowTreemapLabel =====================
/**
  * check if treemap cell is large enough for labels
  * @param {number} width - cell width
  * @param {number} height - cell height
  * @param {number} minWidth - minimum width threshold (default: 60)
  * @param {number} minHeight - minimum height threshold (default: 35)
  * @returns {boolean} whether cell is large enough
  */
export function shouldShowTreemapLabel(width, height, minWidth = 60, minHeight = 35) {
  return width > minWidth && height > minHeight;
}

// shouldShowTreemapPercentage ================
/**
  * check if treemap cell is large enough for percentage labels
  * @param {number} width - cell width
  * @param {number} height - cell height
  * @returns {boolean} whether cell is large enough for percentage
  */
export function shouldShowTreemapPercentage(width, height) {
  return width > 50 && height > 50;
}

// wrapTreemapLabel ===========================
/**
  * split text into multiple lines for treemap labels
  * @param {string} text - text to split
  * @param {number} rectWidth - width of the rectangle
  * @param {number} fontSize - font size being used
  * @returns {Array<string>} array of text lines
  */
export function wrapTreemapLabel(text, rectWidth, fontSize) {
  const words = text.split(/\s+/);
  const maxCharsPerLine = Math.floor(rectWidth / (fontSize * 0.6));
  const lines = [];
  let currentLine = "";
    
  words.forEach(word => {
    if ((currentLine + word).length <= maxCharsPerLine) {
      currentLine += (currentLine ? " " : "") + word;
    } else {
      if (currentLine) lines.push(currentLine);
      currentLine = word;
    }
  });
  if (currentLine) lines.push(currentLine);
    
  return lines;
}


// =====================================================
// 14. BUBBLE GRID HELPERS
// =====================================================

// calculateBubbleGridDimensions ==============
/**
  * calculate bubble grid dimensions
  * @param {number} width - plot width
  * @param {number} numCols - number of columns (default: 10)
  * @param {number} maxBubbleSize - maximum bubble size (default: 40)
  * @returns {Object} {bubbleSize, bubbleSpacing, gridWidth, gridHeight}
  */
export function calculateBubbleGridDimensions(width, numCols = 10, maxBubbleSize = 40) {
  const bubbleSize = Math.min(width / 12, maxBubbleSize);
  const bubbleSpacing = bubbleSize * 1.2;
  const gridWidth = bubbleSpacing * numCols;
  const gridHeight = bubbleSpacing * numCols; // (assuming square grid)
  
  return {
    bubbleSize,
    bubbleSpacing,
    gridWidth,
    gridHeight
  };
}

// calculateBubbleGridOffset ==================
/**
  * calculate centered offset for bubble grid
  * @param {number} width - total width
  * @param {number} gridWidth - grid width
  * @param {number} topMargin - top margin for title/subtitle
  * @returns {Object} {offsetX, offsetY}
  */
export function calculateBubbleGridOffset(width, gridWidth, topMargin = 80) {
  return {
    offsetX: (width - gridWidth) / 2,
    offsetY: topMargin
  };
}

// generateBubbleGridData =====================
/**
  * generate bubble grid data
  * @param {number} totalBubbles - total number of bubbles (e.g., 100)
  * @param {number} numCols - number of columns
  * @returns {Array} array of bubble objects with row, col, id
  */
export function generateBubbleGridData(totalBubbles = 100, numCols = 10) {
  const bubbles = [];
  for (let i = 0; i < totalBubbles; i++) {
    bubbles.push({
      id: i,
      row: Math.floor(i / numCols),
      col: i % numCols
    });
  }
  return bubbles;
}

// calculateBubblePosition ====================
/**
  * calculate bubble position
  * @param {number} row - bubble row
  * @param {number} col - bubble column
  * @param {number} bubbleSpacing - spacing between bubbles
  * @param {number} offsetX - x offset
  * @param {number} offsetY - y offset
  * @returns {Object} {cx, cy}
  */
export function calculateBubblePosition(row, col, bubbleSpacing, offsetX, offsetY) {
  return {
    cx: offsetX + (col * bubbleSpacing) + bubbleSpacing / 2,
    cy: offsetY + (row * bubbleSpacing) + bubbleSpacing / 2
  };
}

// calculateBubbleGridOverHang ================
/**
  * calculate adjusted dimensions accounting for bubble overhang
  * @param {number} gridWidth - width of the bubble grid
  * @param {number} bubbleSize - size of individual bubbles
  * @returns {Object} {effectiveGridWidth, bubbleRadius, paddingOffset}
  */
export function calculateBubbleGridOverhang(gridWidth, bubbleSize) {
  const bubbleRadius = bubbleSize / 2;
  const effectiveGridWidth = gridWidth + bubbleRadius; // (account for right overhang)
  const paddingOffset = bubbleRadius; // (account for left overhang)
    
  return {
    effectiveGridWidth,
    bubbleRadius,
    paddingOffset
  };
}

// addBubbleGridLegend ========================
/**
  * add legend for bubble grid plots
  * @param {d3.selection} svg - svg element to add legend to
  * @param {Array} legendItems - array of legend items: [{label, color, shape, value?}]
  *   - shape: 'circle' or 'rect'
  *   - value: optional value to display (e.g., dependency ratio)
  * @param {number} width - plot width
  * @param {number} legendY - y position for legend
  * @param {number} fontSize - font size for legend text
  * @returns {number} total height of legend (for calculating plot height)
  */
export function addBubbleGridLegend(svg, legendItems, width, legendY, fontSize = 7) {
  const legendItemHeight = 20;
  const circleRadius = 5;
  const legendCenterX = width / 2;
  const legendStartX = Math.max(20, legendCenterX - 200);
  const maxTextWidth = Math.min(width - legendStartX - 40, 400); // (available width for text)
  
  let currentY = legendY;
  
  legendItems.forEach((item, i) => {
    const legendGroup = svg.append("g")
      .attr("class", `legend-item-${i}`)
      .attr("transform", `translate(${legendStartX}, ${currentY})`);
    
    // add shape (circle or rectangle)
    if (item.shape === 'circle') {
      legendGroup.append("circle")
        .attr("cx", 6)
        .attr("cy", 6)
        .attr("r", circleRadius)
        .attr("fill", item.color)
        .attr("stroke", item.stroke || (item.opacity < 0.2 ? item.color : "white"))
        .attr("stroke-width", 1)
        .attr("opacity", item.opacity || 0.8);
    } else if (item.shape === 'rect') {
      legendGroup.append("rect")
        .attr("x", 2)
        .attr("y", 2)
        .attr("width", 8)
        .attr("height", 8)
        .attr("fill", item.fill || "none")
        .attr("stroke", item.color)
        .attr("stroke-width", 1.5);
    }
    
    // add text with wrapping using foreignObject
    const textX = 18;
    const foreignObject = legendGroup.append("foreignObject")
      .attr("x", textX)
      .attr("y", -4)
      .attr("width", maxTextWidth)
      .attr("height", legendItemHeight * 2); // (allow for 2 lines)
    
    foreignObject.append("xhtml:div")
      .style("font-size", `${fontSize}px`)
      .style("font-family", "system-ui")
      .style("font-weight", "normal")
      .style("color", "currentColor")
      .style("line-height", "1.3")
      .text(item.label);
    
    currentY += legendItemHeight;
  });
  
  return legendItems.length * legendItemHeight;
}


// =====================================================
// 15. POPULATION PYRAMID HELPERS
// =====================================================

// calculatePyramidLabelSize ==================
/**
  * calculate dynamic label font size for pyramid percentage labels
  * @param {number} width - plot width
  * @param {number} bandWidth - height of each bar band
  * @returns {number} font size in pixels
  */
export function calculatePyramidLabelSize(width, bandWidth) {
  const widthScale = Math.max(0.7, Math.min(1.2, width / 800));
  const bandScale = Math.max(0.8, Math.min(1.2, bandWidth / 20));
  const baseFontSize = 9;
    
  return Math.max(7, Math.min(11, baseFontSize * widthScale * bandScale));
}

// shouldShowPyramidLabel =====================
/**
  * determine if pyramid labels should be shown based on bar size
  * @param {number} barWidth - width of the bar in pixels
  * @param {number} bandHeight - height of the bar band
  * @param {number} minWidth - minimum width threshold (default: 30)
  * @param {number} minHeight - minimum height threshold (default: 15)
  * @returns {boolean} whether labels should be shown
  */
export function shouldShowPyramidLabel(barWidth, bandHeight, minWidth = 30, minHeight = 15) {
  return barWidth > minWidth && bandHeight > minHeight;
}

// calculatePyramidYTicks =====================
/**
  * calculate intelligent Y-axis tick filtering for pyramid age brackets
  * @param {Array} ageBrackets - array of all age bracket labels
  * @param {number} innerHeight - available height for the plot
  * @returns {Array} filtered array of age brackets to show
  */
export function calculatePyramidYTicks(ageBrackets, innerHeight) {
  const availableSpacePerBracket = innerHeight / ageBrackets.length;
  let tickInterval;
  
  if (availableSpacePerBracket < 15) {
    tickInterval = 4; // (show every 4th bracket)
  } else if (availableSpacePerBracket < 20) {
    tickInterval = 3; // (show every 3rd bracket)
  } else if (availableSpacePerBracket < 25) {
    tickInterval = 2; // (show every 2nd bracket)
  } else {
    tickInterval = 1; // (show all brackets)
  }
  
  return ageBrackets.filter((bracket, index) => index % tickInterval === 0);
}

// calculatePyramidXTickCount =================
/**
  * calculate number of x-axis ticks for pyramid based on available space
  * @param {number} innerWidth - available width for the plot
  * @returns {number} number of ticks to show
  */
export function calculatePyramidXTickCount(innerWidth) {
  const availableSpacePerTick = (innerWidth / 2) / 5; // space for ticks on each side
    
  if (availableSpacePerTick < 40) {
    return 2; // (show fewer ticks)
  } else if (availableSpacePerTick < 60) {
    return 3; // (show every 3rd tick)
  } else {
    return 4; // (show every 4th tick)
  }
}


// =====================================================
// 16. SMALL MULTIPLES / PANEL HELPERS
// =====================================================

// calculateSmallMultiplesDimensions ==========
/**
  * calculate dimensions for small multiples layout
  * @param {number} totalWidth - total plot width
  * @param {number} numPanels - number of panels/multiples
  * @param {number} gridWidth - width of the content grid within each panel
  * @param {number} minPanelSpacing - minimum spacing between panels (default: 40)
  * @returns {Object} {panelSpacing, totalPanelsWidth, startX}
  */
export function calculateSmallMultiplesDimensions(totalWidth, numPanels, gridWidth, minPanelSpacing = 40) {
  // (calculate spacing needed between panels)
  const availableWidth = totalWidth - 80; // 40px padding on each side
  const totalGridWidth = gridWidth * numPanels;
  const totalSpacingNeeded = availableWidth - totalGridWidth;
  const panelSpacing = Math.max(minPanelSpacing, totalSpacingNeeded / (numPanels + 1));
  
  // (calculate actual total width including spacing)
  const totalPanelsWidth = (gridWidth * numPanels) + (panelSpacing * (numPanels - 1));
  const startX = (totalWidth - totalPanelsWidth) / 2;
  
  return {
    panelSpacing,
    gridWidth,
    totalPanelsWidth,
    startX
  };
}

// calculatePanelXOffset ======================
/**
  * calculate panel x offset for a given panel index
  * @param {number} panelIndex - index of the panel (0-based)
  * @param {number} gridWidth - width of each panel's content
  * @param {number} panelSpacing - spacing between panels
  * @param {number} startX - starting x position for first panel
  * @returns {number} x offset for this panel
  */
export function calculatePanelXOffset(panelIndex, gridWidth, panelSpacing, startX) {
  return startX + (panelIndex * (gridWidth + panelSpacing));
}

// calculatePanelLabelPosition ================
/**
  * calculate panel label positioning
  * @param {number} xOffset - x offset of the panel
  * @param {number} gridWidth - width of the grid/content within panel
  * @returns {Object} {centerX, labelX}
  */
export function calculatePanelLabelPosition(xOffset, gridWidth) {
  const centerX = xOffset + gridWidth / 2;
    
  return {
    centerX,
    labelX: centerX
  };
}

// calculateSmallMultiplesFontSizes ===========
/**
  * calculate font sizes for small multiples labels
  * @param {number} width - total plot width
  * @param {number} numPanels - number of panels
  * @returns {Object} font sizes for panel elements
  */
export function calculateSmallMultiplesFontSizes(width, numPanels) {
  const widthScale = width / PLOT_BASE.WIDTH;
  const densityScale = Math.max(0.7, Math.min(1.2, 6 / numPanels)); // (adjust for panel density)
    
  return {
    panelLabel: Math.max(10, Math.min(16, 14 * widthScale * densityScale)),
    panelValue: Math.max(8, Math.min(12, 10 * widthScale * densityScale)),
    panelDescription: Math.max(7, Math.min(11, 9 * widthScale * densityScale))
  };
}

// calculatePanelStatsPosition ================
/**
  * calculate statistics positioning below a panel
  * @param {number} gridHeight - height of the grid/content
  * @param {number} yOffset - y offset of the panel
  * @param {number} lineSpacing - spacing between stat lines (default: 13)
  * @returns {Object} y positions for stat lines
  */
export function calculatePanelStatsPositions(gridHeight, yOffset, lineSpacing = 13) {
  const baseY = yOffset + gridHeight;
    
  return {
    stat1Value: baseY + 20,
    stat1Label: baseY + 33,
    stat2Value: baseY + 53,
    stat2Label: baseY + 66
  };
}

// createTimePeriodBins =======================
/**
  * create time period bins for temporal small multiples
  * @param {Array} data - data array with year field
  * @param {number} binSize - size of each bin in years (default: 5)
  * @param {Function} aggregateFn - function to aggregate data within each bin
  * @returns {Array} array of bin objects
  */
export function createTimePeriodBins(data, binSize = 5, aggregateFn) {
  const sortedData = data.slice().sort((a, b) => a.year - b.year);
  const minYear = Math.min(...sortedData.map(d => d.year));
  const maxYear = Math.max(...sortedData.map(d => d.year));
    
  const bins = [];
    
  for (let startYear = minYear; startYear <= maxYear; startYear += binSize) {
    const endYear = Math.min(startYear + binSize - 1, maxYear);
    const binData = sortedData.filter(d => d.year >= startYear && d.year <= endYear);
      
    const aggregatedData = aggregateFn ? aggregateFn(binData, sortedData, startYear, minYear) : binData;
      
    bins.push({
      label: `${startYear}`,
      startYear,
      endYear,
      data: binData,
      ...aggregatedData
    });
  }
    
  return bins;
}


// =====================================================
// 17. TIMELNE / EVENT PLOT HELPERS
// =====================================================

// calculateTimelineDotRadius =================
/**
  * calculate dot radius for timeline/event plots
  * @param {number} width - plot width
  * @param {Object} options - optional min, max, divisor overrides
  * @returns {number} dot radius in px
  */
export function calculateTimelineDotRadius(width, { min = 2, max = 4, divisor = 220 } = {}) {
  return Math.max(min, Math.min(max, width / divisor));
}

// calculateTimelineStemLength ================
/**
  * calculate stem length for timeline/event plots
  * @param {number} innerHeight - inner plot height
  * @param {Object} options - optional min, ratio overrides
  * @returns {number} stem length in px
  */
export function calculateTimelineStemLength(innerHeight, { min = 20, ratio = 0.25 } = {}) {
  return Math.max(min, innerHeight * ratio);
}

// calculateTimelineYearTicks =================
/**
  * calculate intelligent year tick interval for timelines
  * @param {number} innerWidth - inner plot width
  * @param {number} minYear - minimum year in data
  * @param {number} maxYear - maximum year in data
  * @returns {Object} {interval, ticks} - tick interval and array of Date objects
  */
export function calculateTimelineYearTicks(innerWidth, minYear, maxYear) {
  const yearRange = maxYear - minYear;
  const yearSpacing = innerWidth / yearRange;
  
  let interval;
  if (yearSpacing < 40) {
    interval = 5;
  } else if (yearSpacing < 60) {
    interval = 3;
  } else if (yearSpacing < 80) {
    interval = 2;
  } else {
    interval = 1;
  }

  const ticks = [];
  for (let year = minYear; year <= maxYear; year += interval) {
    ticks.push(new Date(year, 0, 1));
  }

  return { interval, ticks };
}


// =====================================================
// 18. MULTI-CHART GRID LAYOUT HELPERS
// =====================================================

// calculateMultiChartDimensions ==============
/**
  * calculate dimensions for a multi-chart grid layout
  * @param {number} totalWidth - total plot width
  * @param {number} numColumns - number of columns (default: 2)
  * @param {number} gridGap - gap between charts (default: 30)
  * @param {number} aspectRatio - height/width ratio per chart (default: 0.65)
  * @returns {Object} {chartWidth, chartHeight, gridGap}
  */
export function calculateMultiChartDimensions(totalWidth, numColumns = 2, gridGap = 30, aspectRatio = 0.65) {
  const totalGapWidth = gridGap * (numColumns - 1);
  const chartWidth = (totalWidth - totalGapWidth - 80) / numColumns; // 80px for side padding
  const chartHeight = chartWidth * aspectRatio;
  
  return {
    chartWidth,
    chartHeight,
    gridGap
  };
}

// calculateChartMargins ======================
/**
  * calculate margins for individual charts in a multi-chart layout
  * @param {number} chartWidth - width of individual chart
  * @param {number} chartHeight - height of individual chart
  * @returns {Object} {top, right, bottom, left}
  */
export function calculateChartMargins(chartWidth, chartHeight) {
  return {
    top: 60,
    right: Math.max(20, chartWidth * 0.04),
    bottom: Math.max(55, chartWidth * 0.11),
    left: Math.max(70, chartWidth * 0.14)
  };
}

// calculateMultiChartFontSizes ===============
/**
  * calculate font sizes for multi-chart layouts
  * @param {number} chartWidth - width of individual chart
  * @returns {Object} font sizes for chart elements
  */
export function calculateMultiChartFontSizes(chartWidth) {
  return {
    title: Math.max(11, Math.min(14, chartWidth / 40)),
    axisLabel: Math.max(9, Math.min(11, chartWidth / 45)),
    tickLabel: Math.max(8, Math.min(10, chartWidth / 50)),
    annotation: Math.max(9, Math.min(11, chartWidth / 45))
  };
}

// calculateMultiChartStrokeSizes =============
/**
  * calculate stroke and dot sizes for multi-chart layouts
  * @param {number} chartWidth - width of individual chart
  * @returns {Object} {strokeWidth, dotRadius}
  */
export function calculateMultiChartStrokeSizes(chartWidth) {
  return {
    strokeWidth: Math.max(1.2, Math.min(2, chartWidth / 350)),
    dotRadius: Math.max(1.2, Math.min(2.2, chartWidth / 220))
  };
}

// formatPopulation ===========================
/**
  * format population numbers for axis labels
  * @param {number} value - number to format
  * @returns {string} formatted string
  */
export function formatPopulation(value) {
  if (value === 0) return "0";
  if (value >= 1000000) return `${(value/1000000).toFixed(value % 1000000 === 0 ? 0 : 1)}M`;
  if (value >= 1000) return `${(value/1000).toFixed(0)}K`;
  return value.toString();
}

// getMultiChartLineConfig ====================
/**
  * get configuration for a standard line chart in multi-chart layout
  * returns parameters that can be used to create the chart
  * @param {Object} config - configuration object
  * @returns {Object} configuration to use with chart creation
  */
export function getMultiChartLineConfig(config) {
  return {
    ...config,
    innerWidth: config.chartWidth - config.margin.left - config.margin.right,
    innerHeight: config.chartHeight - config.margin.top - config.margin.bottom
  };
  }


  // ===================================================
  // 19. DATA PARSING HELPERS
  // ===================================================
  
  // parseRwiCategory =========================
  /**
    * parse RWI category into numeric order for sorting
    * @param {string} bin - RWI category label
    * @returns {number} numeric order value for sorting
    */
  export function parseRwiCategory(bin) {
    const categoryOrder = {
      "Least wealthy": 1,
      "Less wealthy": 2,
      "Average wealth": 3,
      "More wealthy": 4,
      "Most wealthy": 5
    };
    return categoryOrder[bin] || 0;
  }

  // parseUbaAreaRange ========================
  /**
    * parse urban built-up area range for sorting
    * @param {string|number} bin - urban built-up area range bin label
    * @returns {number} numeric start value for sorting
    */
  export function parseUbaAreaRange(bin) {
    const binStr = String(bin);
    
    if (binStr.includes('Before')) {
      const [start] = binStr.split('-').map(x => parseFloat(x));
      return start;
    }
    
    return parseFloat(binStr);
  }

  // parsePvAreaRange =========================
  /**
    * parse photovoltaic power potential range for sorting
    * @param {string|number} bin - photovoltaic power potential range bin label
    * @returns {number} numeric start value for sorting
    */
  export function parsePvAreaRange(bin) {
    const binStr = String(bin);
    if (binStr.includes('-')) {
      const [start] = binStr.split('-').map(x => parseFloat(x));
      return start;
    }
    return parseFloat(binStr);
  }

  // parseAirQualityRange ======================
   /**
    * parse air quality range for sorting
    * @param {string|number} bin - air quality range bin label
    * @returns {number} numeric start value for sorting
    */
  export function parseAirQualityRange(bin) {
    const binStr = String(bin);
    if (binStr.includes('-')) {
      const [start] = binStr.split('-').map(x => parseFloat(x));

      return start;
    }
    return parseFloat(binStr);
  }
  
  // parseSummerRange ==========================
  /**
    * parse summer range for sorting
    * @param {string|number} bin - summer range bin label
    * @returns {number} numeric start value for sorting
    */
  export function parseSummerRange(bin) {
    const binStr = String(bin);
    if (binStr.includes('-')) {
      const [start] = binStr.split('-').map(x => parseFloat(x));
      return start;
    }
    return parseFloat(binStr);
  }

  // parseNdviRange ============================
  /**
    * parse NDVI range for sorting
    * @param {string|number} bin - NDVI range bin label
    * @returns {number} numeric start value for sorting
    */
  export function parseNdviRange(bin) {
    const binStr = String(bin);
    if (binStr.includes('-')) {
      const [start] = binStr.split('-').map(x => parseFloat(x));  
      return start;
    }
    return parseFloat(binStr);
  }
  
  // parseElevationRange =======================
  /**
    * parse elevation range for sorting
    * @param {string|number} bin - elevation range bin label
    * @returns {number} numeric start value for sorting
    */
  export function parseElevationRange(bin) {
    const binStr = String(bin);
    
    if (binStr.startsWith('-')) {
      return parseFloat(binStr);
    }
    
    if (binStr.includes('-')) {
      const [start] = binStr.split('-').map(x => parseFloat(x));
      return start;
    }
    
    if (binStr.includes('+')) {
      return parseFloat(binStr.replace('+', ''));
    }
    
    return parseFloat(binStr);
  }

  // parseSlopeRange ===========================
  /**
    * parse slope range for sorting
    * @param {string|number} bin - slope range bin label
    * @returns {number} numeric start value for sorting
    */
  export function parseSlopeRange(bin) {
    const binStr = String(bin);
    if (binStr.includes('-')) {
      const [start] = binStr.split('-').map(x => parseFloat(x));
      return start;
    }
    return parseFloat(binStr);
  }

  // parseLsAreaRange ==========================
  /**
    * parse landslide area range for sorting
    * @param {string|number} bin - landslide area range bin label
    * @returns {number} numeric start value for sorting
    */
  export function parseLsAreaRange(bin) {
    const binStr = String(bin);
    if (binStr.includes('-')) {
      const [start] = binStr.split('-').map(x => parseFloat(x));
      return start;
    }
    return parseFloat(binStr);
  }

  // parseLAreaRange ===========================
  /**
    * parse liquefaction area range for sorting
    * @param {string|number} bin - liquefaction area range bin label
    * @returns {number} numeric start value for sorting
    */
  export function parseLAreaRange(bin) {
    const binStr = String(bin);
    if (binStr.includes('-')) {
      const [start] = binStr.split('-').map(x => parseFloat(x));
      return start;
    }
    return parseFloat(binStr);
  }