// plots.js - Plotting functions from Caroline's Observable notebook
// Source: https://observablehq.com/@carolinecullinan/nouakchott-scanned

// import plot helpers (Caroline's refactor)
import * as PlotHelpers from './plot-helpers.js';

let d3;
let globalCity = "City";
let globalCountry = "Country";

// Call this first with d3 from OJS: setD3(require("d3@7"))
export function setD3(d3Instance) {
  d3 = d3Instance;
}


// Set city and country names
export function setCity(name) {
  globalCity = name;
}

export function setCountry(name) {
  globalCountry = name;
}


// ------------------------------------------------------------
// calculateAgeDependencyRatios
// ------------------------------------------------------------
function calculateAgeDependencyRatios(pas) {
    // aggregate data into age groups: young (under 15 years); working age (15-64 years); and elderly (65 + years)
    const ageGroups = {
      youth: ["0-4", "5-9", "10-14"],
      workingAge: ["15-19", "20-24", "25-29", "30-34", "35-39", "40-44", "45-49", "50-54", "55-59", "60-64"],
      elderly: ["65-69", "70-74", "75-79", "80+"]
    };
    
    // calculate totals for each age group
    const youthTotal = d3.sum(pas.filter(d => ageGroups.youth.includes(d.ageBracket)), d => d.count);
    const workingAgeTotal = d3.sum(pas.filter(d => ageGroups.workingAge.includes(d.ageBracket)), d => d.count);
    const elderlyTotal = d3.sum(pas.filter(d => ageGroups.elderly.includes(d.ageBracket)), d => d.count);
    
    // calculate dependency ratios
    const youthDependencyRatio = (youthTotal / workingAgeTotal) * 100;
    const elderlyDependencyRatio = (elderlyTotal / workingAgeTotal) * 100;
    const totalDependencyRatio = youthDependencyRatio + elderlyDependencyRatio;
    
    return {
      youthDependencyRatio: Math.round(youthDependencyRatio),
      elderlyDependencyRatio: Math.round(elderlyDependencyRatio), 
      totalDependencyRatio: Math.round(totalDependencyRatio),
      youthTotal,
      workingAgeTotal,
      elderlyTotal
    };
  }


// ------------------------------------------------------------
// plot_pga
// ------------------------------------------------------------
function plot_pga(pg, {
  cityName = globalCity,
  countryName = globalCountry,
  width,
  height
} = {}) {
  
  // ========================================
  // DATA PREPARATION
  // ========================================
  // get year range for title
  const minYear = d3.min(pg, d => d.yearName);
  const maxYear = d3.max(pg, d => d.yearName);

  // ========================================
  // STYLING CALCULATIONS
  // ========================================
  // (use helper functions from plot-helpers.js for all styling calculatiosn)
  const fontSizes = PlotHelpers.calculateFontSizes(width, height);
  const lineHeights = PlotHelpers.calculateLineHeights(fontSizes);
  
  // text content
  const titleText = `Population Growth, ${minYear}-${maxYear}`;
  const titleLocation = cityName;
  const xAxisLabelText = "Year";
  const yAxisLabelText = "Population";
  const captionText = ""; // (empty for this plot)
  
  // text wrapping
  const titleLines = PlotHelpers.wrapText(titleText, width - 40, `${fontSizes.title}px system-ui`);
  const subtitleLines = PlotHelpers.wrapText(titleLocation, width - 40, `${fontSizes.subtitle}px system-ui`);
  const xAxisLabelLines = PlotHelpers.wrapText(xAxisLabelText, width * 0.8, `${fontSizes.axisLabel}px system-ui`);
  const yAxisLabelLines = PlotHelpers.wrapText(yAxisLabelText, height * 0.6, `${fontSizes.axisLabel}px system-ui`);
  const captionLines = PlotHelpers.wrapText(captionText, width - 40, `${fontSizes.caption}px system-ui`);

  // calculate text dimensions for margins
  const titleHeight = titleLines.length * lineHeights.title;
  const subtitleHeight = subtitleLines.length * lineHeights.subtitle;
  const xAxisLabelHeight = xAxisLabelLines.length * lineHeights.axisLabel;
  const captionHeight = captionLines.length * lineHeights.caption;
  const yAxisLabelWidth = yAxisLabelLines.length * lineHeights.axisLabel;

  // calculate margins using helper
  const margin = PlotHelpers.calculateMargins(width, height, {
    titleHeight,
    subtitleHeight,
    xAxisLabelHeight,
    captionHeight,
    yAxisLabelWidth
  });
  
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  
  // ========================================
  // SCALES
  // ========================================
  // (linear for line charts)
  const xScale = d3.scaleLinear()
    .domain(d3.extent(pg, d => d.yearName))
    .range([0, innerWidth]);
    
  const yScale = d3.scaleLinear()
    .domain([0, Math.max(...pg.map(d => d.population)) * 1.1])
    .range([innerHeight, 0]);

  // ========================================
  // SVG CREATION
  // ========================================
  const svg = d3.create("svg")
    .attr("viewBox", `0 0 ${width} ${height}`)
    .attr("preserveAspectRatio", "xMidYMid meet")
    .style("width", "100%")
    .style("height", "auto")
    .style("max-width", `${width}px`);

  const g = svg.append("g")
    .attr("transform", `translate(${margin.left},${margin.top})`);
  
  // ========================================
  // Y-AXIS 
  // ========================================
  const yTicks = PlotHelpers.calculateYTicks(innerHeight);
  const yAxisGroup = g.append("g").attr("class", "y-axis");
  const yAxisCall = d3.axisLeft(yScale)
    .ticks(yTicks)
    .tickSizeOuter(0)
    .tickSizeInner(-innerWidth)
    .tickFormat(d => { // (with custom population formatter)
      if (d === 0) return "0";
      if (d >= 1000000) return `${(d/1000000).toFixed(d % 1000000 === 0 ? 0 : 1)}M`;
      if (d >= 1000) return `${(d/1000).toFixed(0)}K`;
      return d;
    });

  yAxisGroup.call(yAxisCall);
  yAxisGroup.selectAll(".tick text")
    .style("font-size", `${fontSizes.yAxisTick}px`);
  
  // ========================================
  // X-AXIS
  // ========================================
  const tickCount = PlotHelpers.calculateXAxisTickCount(innerWidth);
  
  const xAxisGroup = g.append("g")
    .attr("class", "x-axis")
    .attr("transform", `translate(0,${innerHeight})`);
    
  xAxisGroup.call(d3.axisBottom(xScale)
    .ticks(tickCount)  // smart tick count based on width
    .tickFormat(d3.format("d"))  // simple integer format for years
    .tickSizeOuter(0)
    .tickSizeInner(-innerHeight));

  // x-axis tick labels with wrapping
  const tickSpacing = innerWidth / tickCount;
  xAxisGroup.selectAll(".tick text")
    .each(function() {
      const text = d3.select(this);
      const labelText = text.text();
      
      text.style("font-size", `${fontSizes.xAxisTick}px`);

      const lines = PlotHelpers.wrapLineChartLabel(labelText, tickSpacing, `${fontSizes.xAxisTick}px system-ui`);
      text.text(null);
      
      lines.forEach((line, i) => {
        text.append("tspan")
          .attr("x", 0)
          .attr("dy", i === 0 ? "1.2em" : "1.1em")
          .text(line);
      });
    });

  // ========================================
  // LINE
  // ========================================
  const line = d3.line()
    .defined(d => d.population > 0)   // skip missing years (0): leave a gap, don't connect (team fix)
    .x(d => xScale(d.yearName))
    .y(d => yScale(d.population));
    
  g.append("path")
    .datum(pg)
    .attr("fill", "none")
    .attr("stroke", "black")
    .attr("stroke-width", Math.max(1.5, Math.min(3, width / 400)))
    .attr("d", line);
  
  // ========================================
  // DOTS
  // ========================================
  g.selectAll(".dot")
    .data(pg)
    .enter().append("circle")
    .attr("class", "dot")
    .attr("cx", d => xScale(d.yearName))
    .attr("cy", d => yScale(d.population))
    .attr("r", Math.max(2, Math.min(3, width / 200)))
    .attr("fill", "black")
    .style("cursor", "default")
    .on("mouseover", function(event, d) {
      d3.selectAll(".d3-tooltip").remove();

      const tooltip = d3.select("body").append("div")
        .attr("class", "d3-tooltip")
        .style("opacity", 0);
        
      const html = `<div>Year: ${d.yearName}</div><div>Population: ${d.population.toLocaleString()}</div>`;
      
      // calculate position to avoid bleeding off screen
      const tooltipWidth = 220;
      const windowWidth = window.innerWidth;
      const mouseX = event.pageX;
      
      let leftPos = mouseX + 10;
      if (leftPos + tooltipWidth > windowWidth) {
        leftPos = mouseX - tooltipWidth - 10;
      }
      
      tooltip
        .html(html)
        .style("left", leftPos + "px")
        .style("top", (event.pageY - 35) + "px")
        .transition()
        .duration(200)
        .style("opacity", 1);
    })
    .on("mousemove", function(event) {
      const tooltip = d3.select(".d3-tooltip");
      if (!tooltip.empty()) {
        const tooltipWidth = 220;
        const windowWidth = window.innerWidth;
        const mouseX = event.pageX;
        
        let leftPos = mouseX + 10;
        if (leftPos + tooltipWidth > windowWidth) {
          leftPos = mouseX - tooltipWidth - 10;
        }
        
        tooltip
          .style("left", leftPos + "px")
          .style("top", (event.pageY - 35) + "px");
      }
    })
    .on("mouseout", function() {
      d3.select(".d3-tooltip")
        .transition()
        .duration(200)
        .style("opacity", 0)
        .remove();
    });
  
  // ========================================
  // TITLE
  // ========================================
  const heightScale = height / PlotHelpers.PLOT_BASE.HEIGHT;
  const titleY = PlotHelpers.getTitleY(height, heightScale);
  
  titleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-title")
      .attr("x", 20)
      .attr("y", titleY + (i * lineHeights.title))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.title}px`)
      .text(line);
  });
    
  // ========================================
  // SUBTITLE
  // ========================================
  const subtitleY = PlotHelpers.getSubtitleY(titleY, titleLines.length, lineHeights.title, heightScale);
  
  subtitleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-subtitle")
      .attr("x", 20)
      .attr("y", subtitleY + (i * lineHeights.subtitle))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.subtitle}px`)
      .text(line);
  });
    
  // ========================================
  // Y-AXIS LABEL
  // ========================================
  const widthScale = width / PlotHelpers.PLOT_BASE.WIDTH;
  const yAxisLabelX = -(margin.top + innerHeight/2);
  const yAxisLabelY = PlotHelpers.getYAxisLabelY(widthScale);
  
  yAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("transform", "rotate(-90)")
      .attr("y", yAxisLabelY + (i * lineHeights.axisLabel))
      .attr("x", yAxisLabelX)
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // X-AXIS LABEL
  // ========================================
  const xAxisLabelX = margin.left + innerWidth/2;
  const xAxisLabelY = PlotHelpers.getXAxisLabelY(height, captionHeight, heightScale);
  
  xAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("x", xAxisLabelX)
      .attr("y", xAxisLabelY - ((xAxisLabelLines.length - 1 - i) * lineHeights.axisLabel))
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // CAPTION
  // ========================================
  // (empty for this plot)
  if (captionText) {
    const captionY = PlotHelpers.getCaptionY(height, heightScale);
    
    captionLines.forEach((line, i) => {
      svg.append("text")
        .attr("class", "plot-caption")
        .attr("x", 20)
        .attr("y", captionY - ((captionLines.length - 1 - i) * lineHeights.caption))
        .attr("text-anchor", "start")
        .style("font-size", `${fontSizes.caption}px`)
        .text(line);
    });
  }
  
  return svg.node();
}


// ------------------------------------------------------------
// plot_pgp
// ------------------------------------------------------------
function plot_pgp(pg, {
  cityName = globalCity,
  countryName = globalCountry,
  width,
  height
} = {}) {
  
  // ========================================
  // DATA PREPARATION
  // ========================================
  // get year range for title
  const minYear = d3.min(pg, d => d.yearName);
  const maxYear = d3.max(pg, d => d.yearName);

  // ========================================
  // STYLING CALCULATIONS
  // ========================================
  // (use helper functions from plot-helpers.js for all styling calculatiosn)
  const fontSizes = PlotHelpers.calculateFontSizes(width, height);
  const lineHeights = PlotHelpers.calculateLineHeights(fontSizes);
  
  // text content
  const titleText = `Population Growth Percentage, ${minYear}-${maxYear}`;
  const titleLocation = cityName;
  const xAxisLabelText = "Year";
  const yAxisLabelText = "Population Growth Percentage (%)";
  const captionText = ""; // (empty for this plot)
  
  // text wrapping
  const titleLines = PlotHelpers.wrapText(titleText, width - 40, `${fontSizes.title}px system-ui`);
  const subtitleLines = PlotHelpers.wrapText(titleLocation, width - 40, `${fontSizes.subtitle}px system-ui`);
  const xAxisLabelLines = PlotHelpers.wrapText(xAxisLabelText, width * 0.8, `${fontSizes.axisLabel}px system-ui`);
  const yAxisLabelLines = PlotHelpers.wrapText(yAxisLabelText, height * 0.6, `${fontSizes.axisLabel}px system-ui`);
  const captionLines = PlotHelpers.wrapText(captionText, width - 40, `${fontSizes.caption}px system-ui`);

  // calculate text dimensions for margins
  const titleHeight = titleLines.length * lineHeights.title;
  const subtitleHeight = subtitleLines.length * lineHeights.subtitle;
  const xAxisLabelHeight = xAxisLabelLines.length * lineHeights.axisLabel;
  const captionHeight = captionLines.length * lineHeights.caption;
  const yAxisLabelWidth = yAxisLabelLines.length * lineHeights.axisLabel;

  // calculate margins using helper
  const margin = PlotHelpers.calculateMargins(width, height, {
    titleHeight,
    subtitleHeight,
    xAxisLabelHeight,
    captionHeight,
    yAxisLabelWidth
  });
  
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  
  // ========================================
  // SCALES
  // ========================================
  // (linear for line charts)
  const xScale = d3.scaleLinear()
    .domain(d3.extent(pg, d => d.yearName))
    .range([0, innerWidth]);
    
  const yScale = d3.scaleLinear()
    .domain([0, Math.max(...pg.map(d => d.populationGrowthPercentage)) * 1.1])
    .range([innerHeight, 0]);

  // ========================================
  // SVG CREATION
  // ========================================
  const svg = d3.create("svg")
    .attr("viewBox", `0 0 ${width} ${height}`)
    .attr("preserveAspectRatio", "xMidYMid meet")
    .style("width", "100%")
    .style("height", "auto")
    .style("max-width", `${width}px`);

  const g = svg.append("g")
    .attr("transform", `translate(${margin.left},${margin.top})`);
  
  // ========================================
  // Y-AXIS
  // ========================================
  const yTicks = PlotHelpers.calculateYTicks(innerHeight);
  const yAxisGroup = g.append("g").attr("class", "y-axis");
  const yAxisCall = d3.axisLeft(yScale)
    .ticks(yTicks)
    .tickSizeOuter(0)
    .tickSizeInner(-innerWidth)
    .tickFormat(d => d);

  yAxisGroup.call(yAxisCall);
  yAxisGroup.selectAll(".tick text")
    .style("font-size", `${fontSizes.yAxisTick}px`);
  
  // ========================================
  // X-AXIS
  // ========================================
  const tickCount = PlotHelpers.calculateXAxisTickCount(innerWidth);
  
  const xAxisGroup = g.append("g")
    .attr("class", "x-axis")
    .attr("transform", `translate(0,${innerHeight})`);
    
  xAxisGroup.call(d3.axisBottom(xScale)
    .ticks(tickCount) // smart tick count based on width
    .tickFormat(d3.format("d"))  // simple integer format for years
    .tickSizeOuter(0)
    .tickSizeInner(-innerHeight));

  // x-axis tick labels with wrapping
  const tickSpacing = innerWidth / tickCount;
  xAxisGroup.selectAll(".tick text")
    .each(function() {
      const text = d3.select(this);
      const labelText = text.text();
      
      text.style("font-size", `${fontSizes.xAxisTick}px`);

      const lines = PlotHelpers.wrapLineChartLabel(labelText, tickSpacing, `${fontSizes.xAxisTick}px system-ui`);
      text.text(null);
      
      lines.forEach((line, i) => {
        text.append("tspan")
          .attr("x", 0)
          .attr("dy", i === 0 ? "1.2em" : "1.1em")
          .text(line);
      });
    });

  // ========================================
  // LINE
  // ========================================
  const line = d3.line()
    .defined(d => d.populationGrowthPercentage !== null) // skip null values
    .x(d => xScale(d.yearName))
    .y(d => yScale(d.populationGrowthPercentage));
    
  g.append("path")
    .datum(pg)
    .attr("fill", "none")
    .attr("stroke", "black")
    .attr("stroke-width", Math.max(1.5, Math.min(3, width / 400)))
    .attr("d", line);
  
  // ========================================
  // DOTS
  // ========================================
  g.selectAll(".dot")
    .data(pg.filter(d => d.populationGrowthPercentage !== null)) // skip null values
    .enter().append("circle")
    .attr("class", "dot")
    .attr("cx", d => xScale(d.yearName))
    .attr("cy", d => yScale(d.populationGrowthPercentage))
    .attr("r", Math.max(2, Math.min(3, width / 200)))
    .attr("fill", "black")
    .style("cursor", "default")
    .on("mouseover", function(event, d) {
      d3.selectAll(".d3-tooltip").remove();

      const tooltip = d3.select("body").append("div")
        .attr("class", "d3-tooltip")
        .style("opacity", 0);
        
      const html = `<div>Year: ${d.yearName}</div><div>Growth Percentage: ${d.populationGrowthPercentage !== null ? d.populationGrowthPercentage.toFixed(2) + '%' : 'N/A'}</div>`;
      
      // calculate position to avoid bleeding off screen
      const tooltipWidth = 220;
      const windowWidth = window.innerWidth;
      const mouseX = event.pageX;
      
      let leftPos = mouseX + 10;
      if (leftPos + tooltipWidth > windowWidth) {
        leftPos = mouseX - tooltipWidth - 10;
      }
      
      tooltip
        .html(html)
        .style("left", leftPos + "px")
        .style("top", (event.pageY - 35) + "px")
        .transition()
        .duration(200)
        .style("opacity", 1);
    })
    .on("mousemove", function(event) {
      const tooltip = d3.select(".d3-tooltip");
      if (!tooltip.empty()) {
        const tooltipWidth = 220;
        const windowWidth = window.innerWidth;
        const mouseX = event.pageX;
        
        let leftPos = mouseX + 10;
        if (leftPos + tooltipWidth > windowWidth) {
          leftPos = mouseX - tooltipWidth - 10;
        }
        
        tooltip
          .style("left", leftPos + "px")
          .style("top", (event.pageY - 35) + "px");
      }
    })
    .on("mouseout", function() {
      d3.select(".d3-tooltip")
        .transition()
        .duration(200)
        .style("opacity", 0)
        .remove();
    });
  
  // ========================================
  // TITLE
  // ========================================
  const heightScale = height / PlotHelpers.PLOT_BASE.HEIGHT;
  const titleY = PlotHelpers.getTitleY(height, heightScale);
  
  titleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-title")
      .attr("x", 20)
      .attr("y", titleY + (i * lineHeights.title))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.title}px`)
      .text(line);
  });
    
  // ========================================
  // SUBTITLE
  // ========================================
  const subtitleY = PlotHelpers.getSubtitleY(titleY, titleLines.length, lineHeights.title, heightScale);
  
  subtitleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-subtitle")
      .attr("x", 20)
      .attr("y", subtitleY + (i * lineHeights.subtitle))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.subtitle}px`)
      .text(line);
  });
    
  // ========================================
  // Y-AXIS LABEL
  // ========================================
  const widthScale = width / PlotHelpers.PLOT_BASE.WIDTH;
  const yAxisLabelX = -(margin.top + innerHeight/2);
  const yAxisLabelY = PlotHelpers.getYAxisLabelY(widthScale);
  
  yAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("transform", "rotate(-90)")
      .attr("y", yAxisLabelY + (i * lineHeights.axisLabel))
      .attr("x", yAxisLabelX)
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // X-AXIS LABEL
  // ========================================
  const xAxisLabelX = margin.left + innerWidth/2;
  const xAxisLabelY = PlotHelpers.getXAxisLabelY(height, captionHeight, heightScale);
  
  xAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("x", xAxisLabelX)
      .attr("y", xAxisLabelY - ((xAxisLabelLines.length - 1 - i) * lineHeights.axisLabel))
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // CAPTION
  // ========================================
  // (empty for this plot)
  if (captionText) {
    const captionY = PlotHelpers.getCaptionY(height, heightScale);
    
    captionLines.forEach((line, i) => {
      svg.append("text")
        .attr("class", "plot-caption")
        .attr("x", 20)
        .attr("y", captionY - ((captionLines.length - 1 - i) * lineHeights.caption))
        .attr("text-anchor", "start")
        .style("font-size", `${fontSizes.caption}px`)
        .text(line);
    });
  }
  
  return svg.node();
}


// ------------------------------------------------------------
// plot_pas
// ------------------------------------------------------------
function plot_pas(pas, {
  cityName = globalCity, 
  countryName = globalCountry, 
  width, 
  height 
} = {}) { 
  // ========================================
  // DATA PREPARATION
  // ========================================
  // get year for title
  const year = d3.max(pas, d => d.yearName);
  
  // define age bracket order
  const ageBrackets = [
    "0-4", "5-9", "10-14", "15-19", "20-24", "25-29", "30-34", 
    "35-39", "40-44", "45-49", "50-54", "55-59", "60-64", 
    "65-69", "70-74", "75-79", "80+"
  ];
  
  // color scale
  const colorScale = d3.scaleOrdinal()
    .domain(["female", "male"])
    .range(["#f05f5c", "#00b4b7"]);
  
  // ========================================
  // STYLING CALCULATIONS
  // ========================================
  // (use helper functions from plot-helpers.js for all styling calculatiosn)
  const fontSizes = PlotHelpers.calculateFontSizes(width, height);
  const lineHeights = PlotHelpers.calculateLineHeights(fontSizes);
  
  // text content
  const titleText = (year ? `Population Distribution by Age and Sex, ${year}` : `Population Distribution by Age and Sex`);
  const titleLocation = countryName ? `${cityName}, ${countryName}` : cityName;
  const xAxisLabelText = "Age Bracket";
  const yAxisLabelText = "Percentage of Age Distribution (%)";
  const captionText = ""; // (empty for this plot)
  
  // text wrapping
  const titleLines = PlotHelpers.wrapText(titleText, width - 40, `${fontSizes.title}px system-ui`);
  const subtitleLines = PlotHelpers.wrapText(titleLocation, width - 40, `${fontSizes.subtitle}px system-ui`);
  const xAxisLabelLines = PlotHelpers.wrapText(xAxisLabelText, width * 0.8, `${fontSizes.axisLabel}px system-ui`);
  const yAxisLabelLines = PlotHelpers.wrapText(yAxisLabelText, height * 0.6, `${fontSizes.axisLabel}px system-ui`);
  const captionLines = PlotHelpers.wrapText(captionText, width - 40, `${fontSizes.caption}px system-ui`);

  // calculate text dimensions for margins
  const titleHeight = titleLines.length * lineHeights.title;
  const subtitleHeight = subtitleLines.length * lineHeights.subtitle;
  const xAxisLabelHeight = xAxisLabelLines.length * lineHeights.axisLabel;
  const captionHeight = captionLines.length * lineHeights.caption;
  const yAxisLabelWidth = yAxisLabelLines.length * lineHeights.axisLabel;

  // calculate margins using helper
  const margin = PlotHelpers.calculateMargins(width, height, {
    titleHeight,
    subtitleHeight,
    xAxisLabelHeight,
    captionHeight,
    yAxisLabelWidth
  });
  
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  
  // ========================================
  // SCALES
  // ========================================
  const xScale = d3.scaleBand()
    .domain(ageBrackets)
    .range([0, innerWidth])
    .paddingInner(0.3)
    .paddingOuter(0.1);
    
  // sub-scales for grouping female/male bars
  const xSubScale = d3.scaleBand()
    .domain(["female", "male"])
    .range([0, xScale.bandwidth()])
    .padding(0.1);
  
  const yScale = d3.scaleLinear()
    .domain([0, Math.max(...pas.map(d => d.percentage)) * 1.1])
    .range([innerHeight, 0]);
  
  // ========================================
  // SVG CREATION
  // ========================================
  const svg = d3.create("svg")
    .attr("viewBox", `0 0 ${width} ${height}`)
    .attr("preserveAspectRatio", "xMidYMid meet")
    .style("width", "100%")
    .style("height", "auto")
    .style("max-width", `${width}px`);
    
  const g = svg.append("g")
    .attr("transform", `translate(${margin.left},${margin.top})`);
  
  // ========================================
  // Y-AXIS
  // ========================================
  const yTicks = PlotHelpers.calculateYTicks(innerHeight);
  const yAxisGroup = g.append("g").attr("class", "y-axis");
  const yAxisCall = d3.axisLeft(yScale)
    .ticks(yTicks)
    .tickSizeOuter(0)
    .tickSizeInner(-innerWidth)
    .tickFormat(d3.format("~s"));

  yAxisGroup.call(yAxisCall);
  yAxisGroup.select(".domain").remove();
  yAxisGroup.selectAll(".tick line")
    .attr("stroke", "#f0f0f0")
    .attr("stroke-width", 1);
  yAxisGroup.selectAll(".tick text")
    .style("font-size", `${fontSizes.yAxisTick}px`);
  
  // ========================================
  // X-AXIS
  // ========================================
  // (with intelligent tick filtering and rotation)
  const filteredBrackets = PlotHelpers.calculateGroupedBarXTicks(ageBrackets, innerWidth, xScale.bandwidth());
  const rotation = PlotHelpers.calculateXAxisLabelRotation(xScale.bandwidth());
  const labelProps = PlotHelpers.calculateRotatedLabelProperties(rotation);

  // calculate tick padding based on rotation
  const tickPadding = rotation === -90 ? 8 : rotation === -45 ? 5 : 10;

  // calculate center between female and male bars
  // (note: midpoint = halfway between the start of female bar and start of male bar, plus half a bar width
  const barCenterOffset = (xSubScale("female") + xSubScale("male")) / 2 + xSubScale.bandwidth() / 2;

  const xAxisGroup = g.append("g")
    .attr("class", "x-axis")
    .attr("transform", `translate(0,${innerHeight})`);
    
  xAxisGroup.call(d3.axisBottom(xScale)
    .tickValues(filteredBrackets)
    .tickSizeOuter(0)
    .tickSizeInner(0)
    .tickPadding(tickPadding));
    
  xAxisGroup.select(".domain")
    .attr("stroke", "currentColor")
    .attr("stroke-width", 1);

  // apply rotation and styling to tick labels
  // center ticks exactly between the female and male bars
  xAxisGroup.selectAll(".tick")
    .attr("transform", function() {
      const currentTransform = d3.select(this).attr("transform");
      const match = currentTransform.match(/translate\(([^,]+),([^)]+)\)/);
      if (match) {
        const x = parseFloat(match[1]);
        const y = parseFloat(match[2]);
        return `translate(${x},${y})`;
      }
      return currentTransform;
    });

  xAxisGroup.selectAll(".tick text")
    .style("font-size", `${fontSizes.xAxisTick}px`)
    .style("text-anchor", labelProps.textAnchor)
    .attr("dx", labelProps.dx)
    .attr("dy", labelProps.dy)
    .each(function() {
      if (rotation !== 0) {
        d3.select(this).attr("transform", `rotate(${rotation})`);
      }
    });
  
  // ========================================
  // BASELINE RULE
  // ========================================
  g.append("line")
    .attr("x1", 0)
    .attr("x2", innerWidth)
    .attr("y1", yScale(0))
    .attr("y2", yScale(0))
    .attr("stroke", "currentColor")
    .attr("stroke-width", 1);
  
  // ========================================
  // BARS
  // ========================================
  g.selectAll(".bar")
    .data(pas)
    .enter().append("rect")
    .attr("class", "bar")
    .attr("x", d => xScale(d.ageBracket) + xSubScale(d.sex))
    .attr("width", xSubScale.bandwidth())
    .attr("y", d => yScale(d.percentage))
    .attr("height", d => innerHeight - yScale(d.percentage))
    .attr("fill", d => colorScale(d.sex))
    .style("cursor", "default");
  
  // ========================================
  // HOVER AREAS WITH TOOLTIPS
  // ========================================
  ageBrackets.forEach(bracket => {
    const femaleData = pas.find(d => d.ageBracket === bracket && d.sex === "female");
    const maleData = pas.find(d => d.ageBracket === bracket && d.sex === "male");
    
    g.append("rect")
      .attr("class", "hover-area")
      .attr("x", xScale(bracket))
      .attr("width", xScale.bandwidth())
      .attr("y", 0)
      .attr("height", innerHeight)
      .attr("fill", "transparent")
      .style("cursor", "default")
      .on("mouseover", function(event) {
        d3.selectAll(".d3-tooltip").remove();
        
        const tooltip = d3.select("body").append("div")
          .attr("class", "d3-tooltip")
          .style("opacity", 0);
        
        const tooltipContent = `
          <div style="font-weight: bold; margin-bottom: 8px;">Age Bracket: ${bracket}</div>
          <div style="border-bottom: 1px solid #ddd; margin-bottom: 6px;"></div>
          <div style="margin-bottom: 4px;">Female: ${femaleData?.percentage.toFixed(2) || '0.00'}% (${femaleData?.count.toFixed(0) || '0'} people)</div>
          <div style="">Male: ${maleData?.percentage.toFixed(2) || '0.00'}% (${maleData?.count.toFixed(0) || '0'} people)</div>
        `;
        
        const tooltipWidth = 280;
        const windowWidth = window.innerWidth;
        const mouseX = event.pageX;
        
        let leftPos = mouseX + 10;
        if (leftPos + tooltipWidth > windowWidth) {
          leftPos = mouseX - tooltipWidth - 10;
        }
        
        tooltip
          .html(tooltipContent)
          .style("left", leftPos + "px")
          .style("top", (event.pageY - 10) + "px")
          .transition()
          .duration(200)
          .style("opacity", 1);
      })
      .on("mousemove", function(event) {
        const tooltip = d3.select(".d3-tooltip");
        if (!tooltip.empty()) {
          const tooltipWidth = 280;
          const windowWidth = window.innerWidth;
          const mouseX = event.pageX;
          
          let leftPos = mouseX + 10;
          if (leftPos + tooltipWidth > windowWidth) {
            leftPos = mouseX - tooltipWidth - 10;
          }
          
          tooltip
            .style("left", leftPos + "px")
            .style("top", (event.pageY - 10) + "px");
        }
      })
      .on("mouseout", function() {
        d3.select(".d3-tooltip")
          .transition()
          .duration(200)
          .style("opacity", 0)
          .remove();
      });
      
  });
  
  // ========================================
  // LEGEND
  // ========================================
  // (top-right to avoid subtitle overlap)
  const legendData = PlotHelpers.createGroupedBarLegend(["female", "male"], colorScale);
  PlotHelpers.addLegend(svg, legendData, width, height, 'top-right');
  
  // ========================================
  // TITLE
  // ========================================
  const heightScale = height / PlotHelpers.PLOT_BASE.HEIGHT;
  const titleY = PlotHelpers.getTitleY(height, heightScale);
  
  titleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-title")
      .attr("x", 20)
      .attr("y", titleY + (i * lineHeights.title))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.title}px`)
      .text(line);
  });
    
  // ========================================
  // SUBTITLE
  // ========================================
  const subtitleY = PlotHelpers.getSubtitleY(titleY, titleLines.length, lineHeights.title, heightScale);
  
  subtitleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-subtitle")
      .attr("x", 20)
      .attr("y", subtitleY + (i * lineHeights.subtitle))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.subtitle}px`)
      .text(line);
  });
    
  // ========================================
  // Y-AXIS LABEL
  // ========================================
  const widthScale = width / PlotHelpers.PLOT_BASE.WIDTH;
  const yAxisLabelX = -(margin.top + innerHeight/2);
  const yAxisLabelY = PlotHelpers.getYAxisLabelY(widthScale);
  
  yAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("transform", "rotate(-90)")
      .attr("y", yAxisLabelY + (i * lineHeights.axisLabel))
      .attr("x", yAxisLabelX)
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // X-AXIS LABEL
  // ========================================
  const xAxisLabelX = margin.left + innerWidth/2;
  const xAxisLabelY = PlotHelpers.getXAxisLabelY(height, captionHeight, heightScale);
  
  xAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("x", xAxisLabelX)
      .attr("y", xAxisLabelY - ((xAxisLabelLines.length - 1 - i) * lineHeights.axisLabel))
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });

  // ========================================
  // CAPTION
  // ========================================
  // (empty for this plot)
  if (captionText) {
    const captionY = PlotHelpers.getCaptionY(height, heightScale);
    
    captionLines.forEach((line, i) => {
      svg.append("text")
        .attr("class", "plot-caption")
        .attr("x", 20)
        .attr("y", captionY - ((captionLines.length - 1 - i) * lineHeights.caption))
        .attr("text-anchor", "start")
        .style("font-size", `${fontSizes.caption}px`)
        .text(line);
    });
  }

  return svg.node();
}


// ------------------------------------------------------------
// plot_pas_pyramid
// ------------------------------------------------------------
function plot_pas_pyramid(pas, {
  cityName = globalCity,
  countryName = globalCountry,
  width,
  height
} = {}) {
  
  // ========================================
  // DATA PREPARATION
  // ========================================
  // get year for title
  const year = d3.max(pas, d => d.yearName);
  
  // age bracket order (bottom to top, reversed for pyramid)
  const ageBrackets = [
    "0-4", "5-9", "10-14", "15-19", "20-24", "25-29", "30-34", 
    "35-39", "40-44", "45-49", "50-54", "55-59", "60-64", 
    "65-69", "70-74", "75-79", "80+"
  ].reverse();
  
  // max percentage for symmetric scale
  const maxPercentage = d3.max(pas, d => d.percentage);
  
  // color scale
  const colorScale = d3.scaleOrdinal()
    .domain(["female", "male"])
    .range(["#f05f5c", "#00b4b7"]);
  
  // ========================================
  // STYLING CALCULATIONS
  // ========================================
  // (use helper functions from plot-helpers.js for all styling calculatiosn)
  const fontSizes = PlotHelpers.calculateFontSizes(width, height);
  const lineHeights = PlotHelpers.calculateLineHeights(fontSizes);
  
  // text content
  const titleText = (year ? `Population Distribution by Age and Sex, ${year}` : `Population Distribution by Age and Sex`);
  const titleLocation = countryName ? `${cityName}, ${countryName}` : cityName;
  const xAxisLabelText = "Percentage of Age Distribution (%)";
  const yAxisLabelText = "Age Bracket";
  const captionText = ""; // (empty for this plot)

  // text wrapping
  const titleLines = PlotHelpers.wrapText(titleText, width - 40, `${fontSizes.title}px system-ui`);
  const subtitleLines = PlotHelpers.wrapText(titleLocation, width - 40, `${fontSizes.subtitle}px system-ui`);
  const xAxisLabelLines = PlotHelpers.wrapText(xAxisLabelText, width * 0.8, `${fontSizes.axisLabel}px system-ui`);
  const yAxisLabelLines = PlotHelpers.wrapText(yAxisLabelText, height * 0.6, `${fontSizes.axisLabel}px system-ui`);
  const captionLines = PlotHelpers.wrapText(captionText, width - 40, `${fontSizes.caption}px system-ui`);

  // calculate text dimensions for margins
  const titleHeight = titleLines.length * lineHeights.title;
  const subtitleHeight = subtitleLines.length * lineHeights.subtitle;
  const xAxisLabelHeight = xAxisLabelLines.length * lineHeights.axisLabel;
  const captionHeight = captionLines.length * lineHeights.caption;
  const yAxisLabelWidth = yAxisLabelLines.length * lineHeights.axisLabel;

  // calculate margins using pyramid-specific helper
  const margin = PlotHelpers.calculatePyramidMargins(width, height, {
    titleHeight,
    subtitleHeight,
    xAxisLabelHeight,
    captionHeight,
    yAxisLabelWidth
  });
  
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  
  // ========================================
  // SCALES
  // ========================================
  const yScale = d3.scaleBand()
    .domain(ageBrackets)
    .range([0, innerHeight])
    .paddingInner(0.1)
    .paddingOuter(0.1);
    
  const xScale = d3.scaleLinear()
    .domain([0, maxPercentage * 1.1])
    .range([0, innerWidth / 2]);
  
  // ========================================
  // SVG CREATION
  // ========================================
  const svg = d3.create("svg")
    .attr("viewBox", `0 0 ${width} ${height}`)
    .attr("preserveAspectRatio", "xMidYMid meet")
    .style("width", "100%")
    .style("height", "auto")
    .style("max-width", `${width}px`);
    
  const g = svg.append("g")
    .attr("transform", `translate(${margin.left},${margin.top})`);
  
  // ========================================
  // CENTER LINE
  // ========================================
  g.append("line")
    .attr("x1", innerWidth / 2)
    .attr("x2", innerWidth / 2)
    .attr("y1", 0)
    .attr("y2", innerHeight)
    .attr("stroke", "#f0f0f0")
    .attr("stroke-width", 1);
  
  // ========================================
  // Y-AXIS
  // ========================================
  // (with intelligent tick filtering)
  const filteredBrackets = PlotHelpers.calculatePyramidYTicks(ageBrackets, innerHeight);
  
  const yAxis = g.append("g")
    .attr("class", "y-axis")
    .attr("transform", `translate(0, 0)`);
    
  yAxis.call(d3.axisLeft(yScale)
    .tickValues(filteredBrackets)
    .tickSize(0)
    .tickPadding(10))
    .select(".domain")
    .attr("stroke", "currentColor")
    .attr("stroke-width", 1);
    
  yAxis.selectAll(".tick text")
    .style("font-size", `${fontSizes.yAxisTick}px`);
  
  // ========================================
  // BARS
  // ========================================
  // (male on left side)
  const maleData = pas.filter(d => d.sex === "male");
  g.selectAll(".male-bar")
    .data(maleData)
    .enter().append("rect")
    .attr("class", "male-bar")
    .attr("x", d => innerWidth / 2 - xScale(d.percentage))
    .attr("y", d => yScale(d.ageBracket))
    .attr("width", d => xScale(d.percentage))
    .attr("height", yScale.bandwidth())
    .attr("fill", colorScale("male"))
    .style("cursor", "default");
  
  // (female on right side)
  const femaleData = pas.filter(d => d.sex === "female");
  g.selectAll(".female-bar")
    .data(femaleData)
    .enter().append("rect")
    .attr("class", "female-bar")
    .attr("x", innerWidth / 2)
    .attr("y", d => yScale(d.ageBracket))
    .attr("width", d => xScale(d.percentage))
    .attr("height", yScale.bandwidth())
    .attr("fill", colorScale("female"))
    .style("cursor", "default");
  
  // ========================================
  // PERCENTAGE LABELS
  // ========================================
  const labelFontSize = PlotHelpers.calculatePyramidLabelSize(width, yScale.bandwidth());
  
  // male labels (left side)
  g.selectAll(".male-label")
    .data(maleData)
    .enter()
    .filter(d => PlotHelpers.shouldShowPyramidLabel(xScale(d.percentage), yScale.bandwidth()))
    .append("text")
    .attr("class", "male-label")
    .attr("x", d => innerWidth / 2 - xScale(d.percentage) - 5)
    .attr("y", d => yScale(d.ageBracket) + yScale.bandwidth() / 2)
    .attr("dy", "0.35em")
    .attr("text-anchor", "end")
    .attr("fill", "currentColor")
    .style("font-size", `${labelFontSize}px`)
    .style("font-family", "system-ui")
    .text(d => d.percentage.toFixed(1) + "%");
  
  // female labels (right side)
  g.selectAll(".female-label")
    .data(femaleData)
    .enter()
    .filter(d => PlotHelpers.shouldShowPyramidLabel(xScale(d.percentage), yScale.bandwidth()))
    .append("text")
    .attr("class", "female-label")
    .attr("x", d => innerWidth / 2 + xScale(d.percentage) + 5)
    .attr("y", d => yScale(d.ageBracket) + yScale.bandwidth() / 2)
    .attr("dy", "0.35em")
    .attr("text-anchor", "start")
    .attr("fill", "currentColor")
    .style("font-size", `${labelFontSize}px`)
    .style("font-family", "system-ui")
    .text(d => d.percentage.toFixed(1) + "%");
  
  // ========================================
  // X-AXIS
  // ========================================
  // (with intelligent filtering)
  const numTicks = PlotHelpers.calculatePyramidXTickCount(innerWidth);
  const xAxisTicks = xScale.ticks(numTicks);
  
  // left side x-axis (males)
  g.selectAll(".x-axis-left")
    .data(xAxisTicks.slice(1))
    .enter().append("text")
    .attr("class", "x-axis-left")
    .attr("x", d => innerWidth / 2 - xScale(d))
    .attr("y", innerHeight + 20)
    .attr("text-anchor", "middle")
    .attr("fill", "currentColor")
    .style("font-size", `${fontSizes.xAxisTick}px`)
    .style("font-family", "system-ui")
    .text(d => d.toFixed(1) + "%");
  
  // right side x-axis (females)
  g.selectAll(".x-axis-right")
    .data(xAxisTicks.slice(1))
    .enter().append("text")
    .attr("class", "x-axis-right")
    .attr("x", d => innerWidth / 2 + xScale(d))
    .attr("y", innerHeight + 20)
    .attr("text-anchor", "middle")
    .attr("fill", "currentColor")
    .style("font-size", `${fontSizes.xAxisTick}px`)
    .style("font-family", "system-ui")
    .text(d => d.toFixed(1) + "%");
  
  // bottom x-axis baseline
  g.append("line")
    .attr("x1", 0)
    .attr("x2", innerWidth)
    .attr("y1", innerHeight)
    .attr("y2", innerHeight)
    .attr("stroke", "currentColor")
    .attr("stroke-width", 1);
  
  // ========================================
  // GENDER LABELS
  // ========================================
  const genderLabelFontSize = Math.max(10, Math.min(12, fontSizes.axisLabel));
  
  g.append("text")
    .attr("x", innerWidth / 4)
    .attr("y", innerHeight + 40)
    .attr("text-anchor", "middle")
    .attr("fill", "currentColor")
    .style("font-size", `${genderLabelFontSize}px`)
    .style("font-family", "system-ui")
    .style("font-weight", "normal")
    .text("Male");
  
  g.append("text")
    .attr("x", innerWidth * 3 / 4)
    .attr("y", innerHeight + 40)
    .attr("text-anchor", "middle")
    .attr("fill", "currentColor")
    .style("font-size", `${genderLabelFontSize}px`)
    .style("font-family", "system-ui")
    .style("font-weight", "normal")
    .text("Female");
  
  // ========================================
  // HOVER AREAS WITH TOOLTIPS
  // ========================================
  ageBrackets.forEach(bracket => {
    const femaleRecord = pas.find(d => d.ageBracket === bracket && d.sex === "female");
    const maleRecord = pas.find(d => d.ageBracket === bracket && d.sex === "male");
    
    g.append("rect")
      .attr("class", "hover-area")
      .attr("x", 0)
      .attr("y", yScale(bracket))
      .attr("width", innerWidth)
      .attr("height", yScale.bandwidth())
      .attr("fill", "transparent")
      .style("cursor", "default")
      .on("mouseover", function(event) {
        d3.selectAll(".d3-tooltip").remove();
        
        const tooltip = d3.select("body").append("div")
          .attr("class", "d3-tooltip")
          .style("opacity", 0);
        
        const tooltipContent = `
          <div style="font-weight: bold; margin-bottom: 8px;">Age Bracket: ${bracket}</div>
          <div style="border-bottom: 1px solid #ddd; margin-bottom: 6px;"></div>
          <div style="">Female: ${femaleRecord?.percentage.toFixed(2) || '0.00'}% (${femaleRecord?.count.toFixed(0) || '0'} people)</div>
          <div style="margin-bottom: 4px;">Male: ${maleRecord?.percentage.toFixed(2) || '0.00'}% (${maleRecord?.count.toFixed(0) || '0'} people)</div>
        `;
        
        const tooltipWidth = 280;
        const windowWidth = window.innerWidth;
        const mouseX = event.pageX;
        
        let leftPos = mouseX + 10;
        if (leftPos + tooltipWidth > windowWidth) {
          leftPos = mouseX - tooltipWidth - 10;
        }
        
        tooltip
          .html(tooltipContent)
          .style("left", leftPos + "px")
          .style("top", (event.pageY - 10) + "px")
          .transition()
          .duration(200)
          .style("opacity", 1);
      })
      .on("mousemove", function(event) {
        const tooltip = d3.select(".d3-tooltip");
        if (!tooltip.empty()) {
          const tooltipWidth = 280;
          const windowWidth = window.innerWidth;
          const mouseX = event.pageX;
          
          let leftPos = mouseX + 10;
          if (leftPos + tooltipWidth > windowWidth) {
            leftPos = mouseX - tooltipWidth - 10;
          }
          
          tooltip
            .style("left", leftPos + "px")
            .style("top", (event.pageY - 10) + "px");
        }
      })
      .on("mouseout", function() {
        d3.select(".d3-tooltip")
          .transition()
          .duration(200)
          .style("opacity", 0)
          .remove();
      });
  });
  
  // ========================================
  // TITLE
  // ========================================
  const heightScale = height / PlotHelpers.PLOT_BASE.HEIGHT;
  const titleY = PlotHelpers.getTitleY(height, heightScale);
  
  titleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-title")
      .attr("x", 20)
      .attr("y", titleY + (i * lineHeights.title))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.title}px`)
      .text(line);
  });
    
  // ========================================
  // SUBTITLE
  // ========================================
  const subtitleY = PlotHelpers.getSubtitleY(titleY, titleLines.length, lineHeights.title, heightScale);
  
  subtitleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-subtitle")
      .attr("x", 20)
      .attr("y", subtitleY + (i * lineHeights.subtitle))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.subtitle}px`)
      .text(line);
  });
    
  // ========================================
  // Y-AXIS LABEL
  // ========================================
  const widthScale = width / PlotHelpers.PLOT_BASE.WIDTH;
  const yAxisLabelX = -(margin.top + innerHeight/2);
  const yAxisLabelY = PlotHelpers.getYAxisLabelY(widthScale);
  
  yAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("transform", "rotate(-90)")
      .attr("y", yAxisLabelY + (i * lineHeights.axisLabel))
      .attr("x", yAxisLabelX)
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // X-AXIS LABEL
  // ========================================
  const xAxisLabelX = margin.left + innerWidth/2;
  const xAxisLabelY = PlotHelpers.getXAxisLabelY(height, captionHeight, heightScale);
  
  xAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("x", xAxisLabelX)
      .attr("y", xAxisLabelY - ((xAxisLabelLines.length - 1 - i) * lineHeights.axisLabel))
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
  
  // ========================================
  // CAPTION
  // ========================================
  // (empty for this plot)
  if (captionText) {
    const captionY = PlotHelpers.getCaptionY(height, heightScale);
    
    captionLines.forEach((line, i) => {
      svg.append("text")
        .attr("class", "plot-caption")
        .attr("x", 20)
        .attr("y", captionY - ((captionLines.length - 1 - i) * lineHeights.caption))
        .attr("text-anchor", "start")
        .style("font-size", `${fontSizes.caption}px`)
        .text(line);
    });
  }
  
  return svg.node();
}


// ------------------------------------------------------------
// plot_age
// ------------------------------------------------------------
function plot_age(pas, {
  cityName = globalCity,
  countryName = globalCountry,
  width,
  height
} = {}) {
  
  // ========================================
  // DATA PREPARATION
  // ========================================
  // get year for title
  const year = d3.max(pas, d => d.yearName);
  
  // aggregate data into three age groups
  const ageGroups = [
    {
      name: "Working Age",
      ageRange: "(15-64 years)",
      brackets: ["15-19", "20-24", "25-29", "30-34", "35-39", "40-44", "45-49", "50-54", "55-59", "60-64"],
      color: "#009E73" // color-blind inclusive
    },
    {
      name: "Youth", 
      ageRange: "(under 15 years)",
      brackets: ["0-4", "5-9", "10-14"],
      color: "#F0E442" // color-blind inclusive
    },
    {
      name: "Elderly",
      ageRange: "(65+ years)", 
      brackets: ["65-69", "70-74", "75-79", "80+"],
      color: "#D55E00" // color-blind inclusive
    }
  ];
  
  // calculate totals for each age group
  const processedData = ageGroups.map(group => {
    const groupData = pas.filter(d => group.brackets.includes(d.ageBracket));
    const totalCount = d3.sum(groupData, d => d.count);
    const totalPercentage = d3.sum(groupData, d => d.percentage);
    
    return {
      name: group.name,
      ageRange: group.ageRange,
      value: totalPercentage,
      count: totalCount,
      color: group.color
    };
  }).filter(d => d.value > 0); // (only include age groups with data)
  
  // create hierarchy data
  const hierarchyData = {
    name: `Population Distribution by Age Groups in ${cityName}`,
    children: processedData
  };
  
  // color scale based on the three age groups
  const colorScale = d3.scaleOrdinal()
    .domain(processedData.map(d => d.name))
    .range(processedData.map(d => d.color));
  
  // ========================================
  // STYLING CALCULATIONS
  // ========================================
  // (use helper functions from plot-helpers.js for all styling calculatiosn)
  const fontSizes = PlotHelpers.calculateFontSizes(width, height);
  const lineHeights = PlotHelpers.calculateLineHeights(fontSizes);
  
  // text content
  const titleText = (year ? `Population Distribution by Age Groups, ${year}` : `Population Distribution by Age Groups`);
  const titleLocation = countryName ? `${cityName}, ${countryName}` : cityName;
  const captionText = ""; // (empty for this plot)
  
  // text wrapping
  const titleLines = PlotHelpers.wrapText(titleText, width - 40, `${fontSizes.title}px system-ui`);
  const subtitleLines = PlotHelpers.wrapText(titleLocation, width - 40, `${fontSizes.subtitle}px system-ui`);
  const captionLines = PlotHelpers.wrapText(captionText, width - 40, `${fontSizes.caption}px system-ui`);

  // calculate text dimensions
  const titleHeight = titleLines.length * lineHeights.title;
  const subtitleHeight = subtitleLines.length * lineHeights.subtitle;
  const captionHeight = captionText ? captionLines.length * lineHeights.caption : 0;


  // treemap top offset for title/subtitle
  const topOffset = titleHeight + subtitleHeight + 10;
  
  // ========================================
  // HIERARCHY AND LAYOUT
  // ========================================
  const treemapHeight = height - topOffset - (captionHeight > 0 ? captionHeight + 10 : 0);
  
  const root = d3.hierarchy(hierarchyData)
    .sum(d => d.value)
    .sort((a, b) => b.value - a.value);
    
  d3.treemap()
    .size([width, treemapHeight])
    .padding(2)
    .round(true)(root);
  
  // ========================================
  // SVG CREATION
  // ========================================
  const svg = d3.create("svg")
    .attr("viewBox", `0 0 ${width} ${height}`)
    .attr("preserveAspectRatio", "xMidYMid meet")
    .style("width", "100%")
    .style("height", "auto")
    .style("max-width", `${width}px`);
  
  // ========================================
  // TITLE
  // ========================================
  const heightScale = height / PlotHelpers.PLOT_BASE.HEIGHT;
  const titleY = PlotHelpers.getTitleY(height, heightScale);
  
  titleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-title")
      .attr("x", 20)
      .attr("y", titleY + (i * lineHeights.title))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.title}px`)
      .text(line);
  });
    
  // ========================================
  // SUBTITLE
  // ========================================
  const subtitleY = PlotHelpers.getSubtitleY(titleY, titleLines.length, lineHeights.title, heightScale);
  
  subtitleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-subtitle")
      .attr("x", 20)
      .attr("y", subtitleY + (i * lineHeights.subtitle))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.subtitle}px`)
      .text(line);
  });
  
  // ========================================
  // TREEMAP CELLS
  // ========================================
  const leaf = svg.selectAll("g")
    .data(root.leaves())
    .join("g")
    .attr("transform", d => `translate(${d.x0},${d.y0 + topOffset})`);
    
  // rectangles with tooltips
  leaf.append("rect")
    .attr("fill", d => colorScale(d.data.name))
    .attr("fill-opacity", 0.8)
    .attr("stroke", "white")
    .attr("stroke-width", 2)
    .attr("width", d => d.x1 - d.x0)
    .attr("height", d => d.y1 - d.y0)
    .style("cursor", "default")
    .on("mouseover", function(event, d) {
      d3.select(this).attr("fill-opacity", 1);
      d3.selectAll(".d3-tooltip").remove();
      
      const tooltip = d3.select("body").append("div")
        .attr("class", "d3-tooltip")
        .style("opacity", 0);
        
      const html = `
        <div style="font-weight: bold; margin-bottom: 6px;">${d.data.name}: ${d.data.ageRange}</div>
        <div style="border-bottom: 1px solid #ddd; margin: 6px 0;"></div>
        <div style="margin-bottom: 3px;">${d.data.value.toFixed(1)}% (${d.data.count.toFixed(0) || '0'} people)</div>
      `;
      
      const tooltipWidth = 220;
      const windowWidth = window.innerWidth;
      const mouseX = event.pageX;
      
      let leftPos = mouseX + 10;
      if (leftPos + tooltipWidth > windowWidth) {
        leftPos = mouseX - tooltipWidth - 10;
      }
      
      tooltip
        .html(html)
        .style("left", leftPos + "px")
        .style("top", (event.pageY - 35) + "px")
        .transition()
        .duration(200)
        .style("opacity", 1);
    })
    .on("mousemove", function(event) {
      const tooltip = d3.select(".d3-tooltip");
      if (!tooltip.empty()) {
        const tooltipWidth = 220;
        const windowWidth = window.innerWidth;
        const mouseX = event.pageX;
        
        let leftPos = mouseX + 10;
        if (leftPos + tooltipWidth > windowWidth) {
          leftPos = mouseX - tooltipWidth - 10;
        }
        
        tooltip
          .style("left", leftPos + "px")
          .style("top", (event.pageY - 35) + "px");
      }
    })
    .on("mouseout", function() {
      d3.select(this).attr("fill-opacity", 0.8);
      d3.select(".d3-tooltip")
        .transition()
        .duration(200)
        .style("opacity", 0)
        .remove();
    });
    
  // ========================================
  // TREEMAP LABELS
  // ========================================
  leaf.filter(d => PlotHelpers.shouldShowTreemapLabel(d.x1 - d.x0, d.y1 - d.y0))
    .each(function(d) {
      const g = d3.select(this);
      const rectWidth = d.x1 - d.x0;
      
      // calculate dynamic font size
      const dynamicFontSize = PlotHelpers.calculateTreemapLabelSize(rectWidth, width);
      
      // split name into lines
      const nameLines = PlotHelpers.wrapTreemapLabel(d.data.name, rectWidth, dynamicFontSize);
      
      // add name text lines
      nameLines.forEach((line, i) => {
        if (i < 2) { // (only show first 2 lines)
          g.append("text")
            .attr("x", 4)
            .attr("y", 20 + (i * (dynamicFontSize + 2)))
            .style("font-family", "system-ui")
            .style("font-weight", "450")
            .style("font-size", `${dynamicFontSize}px`)
            .style("fill", "#333")
            .style("pointer-events", "none")
            .text(line);
        }
      });
      
      // split age range into lines
      const rangeLines = PlotHelpers.wrapTreemapLabel(d.data.ageRange, rectWidth, dynamicFontSize * 0.8);
      
      // add age range text lines (slightly smaller and offset)
      const nameLineCount = Math.min(nameLines.length, 2);
      rangeLines.forEach((line, i) => {
        if (i < 1) { // only show first line
          g.append("text")
            .attr("x", 4)
            .attr("y", 20 + (nameLineCount * (dynamicFontSize + 2)) + (i * (dynamicFontSize * 0.8 + 2)))
            .style("font-family", "system-ui")
            .style("font-size", `${dynamicFontSize * 0.8}px`)
            .style("fill", "#333")
            .style("pointer-events", "none")
            .text(line);
        }
      });
    });
    
  // ========================================
  // PERCENTAGE LABELS
  // ========================================
  leaf.filter(d => PlotHelpers.shouldShowTreemapPercentage(d.x1 - d.x0, d.y1 - d.y0))
    .append("text")
    .attr("x", 4)
    .attr("y", d => {
      const rectWidth = d.x1 - d.x0;
      const fontSize = PlotHelpers.calculateTreemapPercentageSize(rectWidth, width);
      const labelFontSize = PlotHelpers.calculateTreemapLabelSize(rectWidth, width);
      return 50 + labelFontSize;
    })
    .style("font-family", "system-ui")
    .style("font-size", d => {
      const rectWidth = d.x1 - d.x0;
      return `${PlotHelpers.calculateTreemapPercentageSize(rectWidth, width)}px`;
    })
    .style("fill", "#141414")
    .style("pointer-events", "none")
    .text(d => `${d.data.value.toFixed(1)}%`);

    // ========================================
    // CAPTION
    // ========================================
    // (empty for this plot)
    if (captionText) {
      const captionY = PlotHelpers.getCaptionY(height, heightScale);
      
      captionLines.forEach((line, i) => {
        svg.append("text")
          .attr("class", "plot-caption")
          .attr("x", 20)
          .attr("y", captionY - ((captionLines.length - 1 - i) * lineHeights.caption))
          .attr("text-anchor", "start")
          .style("font-size", `${fontSizes.caption}px`)
          .text(line);
      });
    }
  
  return svg.node();
}


// ------------------------------------------------------------
// plot_dependency
// ------------------------------------------------------------
function plot_dependency(pas, {
  cityName = globalCity,
  countryName = globalCountry,
  width,
  height
} = {}) {
  
  // ========================================
  // DATA PREPARATION
  // ========================================
  // get year for title
  const year = d3.max(pas, d => d.yearName);
  
  // calculate dependency ratios
  const ratios = calculateAgeDependencyRatios(pas);
  
  // age group colors (color-blind inclusive)
  const colors = {
    youth: "#F0E442",        // young (under 15 years) (yellow)
    elderly: "#D55E00",      // elderly (65+ years) (orange)
    workingAge: "#009E73",   // working age (15-64 years) (green)
    baseline: "currentColor" // baseline bubbles (gray)
  };
  
  // ========================================
  // GENERATE 100 BUBBLES DATA (10x10 GRID)
  // ========================================
  // generate 100 bubbles data (10x10 grid)
  const bubbleGridData = PlotHelpers.generateBubbleGridData(100, 10);
  
  let youthCount = 0;
  let elderlyCount = 0;
  
  const bubbleData = bubbleGridData.map(bubble => {
    let type = "baseline";
    let color = colors.baseline;
    
    // assign youth bubbles
    if (youthCount < ratios.youthDependencyRatio) {
      type = "youth";
      color = colors.youth;
      youthCount++;
    }
    // assign elderly bubbles
    else if (elderlyCount < ratios.elderlyDependencyRatio) {
      type = "elderly"; 
      color = colors.elderly;
      elderlyCount++;
    }
    
    return {
      ...bubble,
      type,
      color
    };
  });
  
  // ========================================
  // STYLING CALCULATIONS
  // ========================================
  // (use helper functions from plot-helpers.js for all styling calculations)
  const fontSizes = PlotHelpers.calculateFontSizes(width, height);
  const lineHeights = PlotHelpers.calculateLineHeights(fontSizes);
  
  // calculate bubble grid dimensions
  const gridDims = PlotHelpers.calculateBubbleGridDimensions(width, 10, 40);
  
  // text content
  const titleText = (year ? `Age Dependency Ratios, ${year}` : `Age Dependency Ratios`);
  const titleLocation = countryName ? `${cityName}, ${countryName}` : cityName;
  
  // text wrapping
  const titleLines = PlotHelpers.wrapText(titleText, width - 40, `${fontSizes.title}px system-ui`);
  const subtitleLines = PlotHelpers.wrapText(titleLocation, width - 40, `${fontSizes.subtitle}px system-ui`);

  // calculate text dimensions
  const titleHeight = titleLines.length * lineHeights.title;
  const subtitleHeight = subtitleLines.length * lineHeights.subtitle;
  
  // calculate offsets
  const topOffset = titleHeight + subtitleHeight + 20;
  const gridOffset = PlotHelpers.calculateBubbleGridOffset(width, gridDims.gridWidth, topOffset);
  
  // calculate total height
  const legendHeight = 120;
  const calculatedHeight = gridOffset.offsetY + gridDims.gridHeight + legendHeight;
  
  // ========================================
  // SVG CREATION
  // ========================================
  const svg = d3.create("svg")
    .attr("viewBox", `0 0 ${width} ${calculatedHeight}`)
    .attr("preserveAspectRatio", "xMidYMid meet")
    .style("width", "100%")
    .style("height", "auto")
    .style("max-width", `${width}px`);
  
  // ========================================
  // TITLE
  // ========================================
  const heightScale = calculatedHeight / PlotHelpers.PLOT_BASE.HEIGHT;
  const titleY = PlotHelpers.getTitleY(calculatedHeight, heightScale);
  
  titleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-title")
      .attr("x", 20)
      .attr("y", titleY + (i * lineHeights.title))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.title}px`)
      .text(line);
  });
    
  // ========================================
  // SUBTITLE
  // ========================================
  const subtitleY = PlotHelpers.getSubtitleY(titleY, titleLines.length, lineHeights.title, heightScale);
  
  subtitleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-subtitle")
      .attr("x", 20)
      .attr("y", subtitleY + (i * lineHeights.subtitle))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.subtitle}px`)
      .text(line);
  });
  
  // ========================================
  // BUBBLE GRID
  // ========================================
  const bubbles = svg.selectAll(".bubble")
    .data(bubbleData)
    .enter().append("circle")
    .attr("class", "bubble")
    .attr("cx", d => {
      const pos = PlotHelpers.calculateBubblePosition(d.row, d.col, gridDims.bubbleSpacing, gridOffset.offsetX, gridOffset.offsetY);
      return pos.cx;
    })
    .attr("cy", d => {
      const pos = PlotHelpers.calculateBubblePosition(d.row, d.col, gridDims.bubbleSpacing, gridOffset.offsetX, gridOffset.offsetY);
      return pos.cy;
    })
    .attr("r", gridDims.bubbleSize / 2)
    .attr("fill", d => d.color)
    .attr("stroke", d => d.type === "baseline" ? "#dee2e6" : "white")
    .attr("stroke-width", 1)
    .attr("opacity", d => d.type === "baseline" ? 0.07 : 0.8)
    .style("cursor", "default")
    .on("mouseover", function(event, d) {
      d3.select(this).attr("opacity", d.type === "baseline" ? 0.6 : 1);
      d3.selectAll(".d3-tooltip").remove();
      
      const tooltip = d3.select("body").append("div")
        .attr("class", "d3-tooltip")
        .style("opacity", 0);
      
      let tooltipText = "";
      if (d.type === "youth") {
        const youthPercentage = ((ratios.youthTotal / (ratios.youthTotal + ratios.workingAgeTotal + ratios.elderlyTotal)) * 100).toFixed(1);
        tooltipText = `
          <div style="font-weight: normal; margin-bottom: 6px;"><b>Youth Dependency Ratio</b>: ${ratios.youthDependencyRatio}:100</div>
          <div style="border-bottom: 1px solid #ddd; margin: 6px 0;"></div>
          <div><b>Young people</b> under the age of 15 years<br>
                make up <b>${youthPercentage}%</b> of the total population<br>
                and represent <b>${ratios.youthDependencyRatio}%</b> burden on the<br>
                working age population as dependents</div>
        `;
      } else if (d.type === "elderly") {
        const elderlyPercentage = ((ratios.elderlyTotal / (ratios.youthTotal + ratios.workingAgeTotal + ratios.elderlyTotal)) * 100).toFixed(1);
        tooltipText = `
          <div style="font-weight: normal; margin-bottom: 6px;"><b>Elderly Dependency Ratio</b>: ${ratios.elderlyDependencyRatio}:100</div>
          <div style="border-bottom: 1px solid #ddd; margin: 6px 0;"></div>
          <div><b>Elderly people</b> over the age of 65 years<br>
                make up <b>${elderlyPercentage}%</b> of the total population<br>
                and represent <b>${ratios.elderlyDependencyRatio}%</b> burden on the<br>
                working age population as dependents</div>
        `;
      } else {
        const workingAgePercentage = ((ratios.workingAgeTotal / (ratios.youthTotal + ratios.workingAgeTotal + ratios.elderlyTotal)) * 100).toFixed(1);
        tooltipText = `
          <div style="font-weight: normal; margin-bottom: 6px;"><b>Working Age Population</b>: ${workingAgePercentage}% of total</div>
          <div style="font-weight: normal; margin-bottom: 6px;"><b>Total Dependency Ratio</b>: ${ratios.totalDependencyRatio}:100</div>
          <div style="border-bottom: 1px solid #ddd; margin: 6px 0;"></div>
          <div><b>Working age people</b> between 15-64 years<br>
          make up <b>${workingAgePercentage}%</b> of the total population<br>
          and support <b>${ratios.youthDependencyRatio} youth</b> and <b>${ratios.elderlyDependencyRatio} elderly</b><br>
          dependents per 100 workers</div>
        `;
      }
      
      const tooltipWidth = 250;
      const windowWidth = window.innerWidth;
      const mouseX = event.pageX;
      
      let leftPos = mouseX + 10;
      if (leftPos + tooltipWidth > windowWidth) {
        leftPos = mouseX - tooltipWidth - 10;
      }
      
      tooltip
        .html(tooltipText)
        .style("left", leftPos + "px")
        .style("top", (event.pageY - 35) + "px")
        .transition()
        .duration(200)
        .style("opacity", 1);
    })
    .on("mousemove", function(event) {
      const tooltip = d3.select(".d3-tooltip");
      if (!tooltip.empty()) {
        const tooltipWidth = 250;
        const windowWidth = window.innerWidth;
        const mouseX = event.pageX;
        
        let leftPos = mouseX + 10;
        if (leftPos + tooltipWidth > windowWidth) {
          leftPos = mouseX - tooltipWidth - 10;
        }
        
        tooltip
          .style("left", leftPos + "px")
          .style("top", (event.pageY - 35) + "px");
      }
    })
    .on("mouseout", function(event, d) {
      d3.select(this).attr("opacity", d.type === "baseline" ? 0.07 : 0.8);
      d3.select(".d3-tooltip")
        .transition()
        .duration(200)
        .style("opacity", 0)
        .remove();
    });
  
  // ========================================
  // LEGEND
  // ========================================
  const legendY = gridOffset.offsetY + gridDims.gridHeight + 40;
  const legendFontSize = Math.max(9, Math.min(12, fontSizes.caption * 1.2));

  const legendItems = [
    {
      label: "100 bubbles = 100 workers",
      color: "currentColor",
      shape: "circle",
      opacity: 0.07,
      stroke: "currentColor"
    },
    {
      label: `= Youth dependent (${ratios.youthDependencyRatio} per 100 workers)`,
      color: colors.youth,
      shape: "circle",
      opacity: 0.8
    },
    {
      label: `= Elderly dependent (${ratios.elderlyDependencyRatio} per 100 workers)`,
      color: colors.elderly,
      shape: "circle",
      opacity: 0.8
    },
    {
      label: `= Total dependency burden (${ratios.totalDependencyRatio} per 100 workers)`,
      color: "#666",
      shape: "rect"
    }
  ];

  PlotHelpers.addBubbleGridLegend(svg, legendItems, width, legendY, legendFontSize);
  
  return svg.node();
}


// plot_rwi_area ====================================
// function with d3.js that plots rwi_area by percentage distribution to create realtive wealth index (rwi) chart (i.e., "Least wealthy"; "Less wealthy"; "Average wealth"; "More wealthy"; and "Most wealthy" areas as a percentage of total area) using styling for visual cohesion with rwi map)
function plot_rwi_area(rwi_area, {
  cityName = globalCity, 
  countryName = globalCountry,
  width,
  height
} = {}) {
  
  // ========================================
  // DATA PREPARATION
  // ========================================
  const sortedData = rwi_area.slice().sort((a, b) => 
    PlotHelpers.parseRwiCategory(a.bin) - PlotHelpers.parseRwiCategory(b.bin)
  );

  // color mapping for rwi wealth categories
  const rwiColorMap = {
    "Least wealthy": "#44b59c",
    "Less wealthy": "#94d1c0",
    "Average wealth": "#faf9c8",
    "More wealthy": "#faab90",
    "Most wealthy": "#eb765a"
  };
  const defaultColor = "#999999"; // (fallback gray if no color map match)
  // value-range bins (e.g. "-0.92 – -0.36"): colour by VALUE against the map's
  // rwi_standardized palette + SD breaks so the chart matches the map (team fix)
  const rwiMapPalette = ["#009E7A", "#70C5AD", "#FFFFBA", "#FF9169", "#ED431B"];
  const rwiMapBreaks = [-1, -0.5, 0.5, 1];
  const rwiFill = d => {
    if (rwiColorMap[d.bin]) return rwiColorMap[d.bin];
    const nums = String(d.bin).split(/\s*–\s*/).map(parseFloat).filter(n => !isNaN(n));
    if (!nums.length) return defaultColor;
    const mid = (nums[0] + nums[nums.length - 1]) / 2;
    let k = 0; while (k < rwiMapBreaks.length && mid > rwiMapBreaks[k]) k++;
    return rwiMapPalette[k];
  };
  
  const allRwiBins = sortedData.map(d => d.bin);
  
  // complete data with gray bars for visual completeness
  const completeData = allRwiBins.map(bin => {
    const existing = sortedData.find(d => d.bin === bin);
    return existing || { bin, count: 0, percentage: 0 };
  });

  // ========================================
  // STYLING CALCULATIONS
  // ========================================
  // (use helper functions from plot-helpers.js for all styling calculations)
  const fontSizes = PlotHelpers.calculateFontSizes(width, height);
  const lineHeights = PlotHelpers.calculateLineHeights(fontSizes);
  
  // text content
  const titleText = "Relative Wealth Index Distribution";
  const titleLocation = countryName ? `${cityName}, ${countryName}` : cityName;
  const xAxisLabelText = "Relative Wealth Index";
  const yAxisLabelText = "Percentage of Area (%)";
  const captionText = "Data: Meta Data for Good | Relative Wealth Index";
  
  // text wrapping
  const titleLines = PlotHelpers.wrapText(titleText, width - 40, `${fontSizes.title}px system-ui`);
  const subtitleLines = PlotHelpers.wrapText(titleLocation, width - 40, `${fontSizes.subtitle}px system-ui`);
  const xAxisLabelLines = PlotHelpers.wrapText(xAxisLabelText, width * 0.8, `${fontSizes.axisLabel}px system-ui`);
  const yAxisLabelLines = PlotHelpers.wrapText(yAxisLabelText, height * 0.6, `${fontSizes.axisLabel}px system-ui`);
  const captionLines = PlotHelpers.wrapText(captionText, width - 40, `${fontSizes.caption}px system-ui`);

  // calculate text dimensions for margins
  const titleHeight = titleLines.length * lineHeights.title;
  const subtitleHeight = subtitleLines.length * lineHeights.subtitle;
  const xAxisLabelHeight = xAxisLabelLines.length * lineHeights.axisLabel;
  const captionHeight = captionLines.length * lineHeights.caption;
  const yAxisLabelWidth = yAxisLabelLines.length * lineHeights.axisLabel;

  // calculate margins using helper
  const margin = PlotHelpers.calculateMargins(width, height, {
    titleHeight,
    subtitleHeight,
    xAxisLabelHeight,
    captionHeight,
    yAxisLabelWidth
  });
  
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  
  // ========================================
  // SCALES
  // ========================================
  const xScale = d3.scaleBand()
    .domain(completeData.map(d => d.bin))
    .range([0, innerWidth])
    .padding(0.1);
    
  const yScale = d3.scaleLinear()
    .domain([0, 100])
    .range([innerHeight, 0]);

  // ========================================
  // SVG CREATION
  // ========================================
  const svg = d3.create("svg")
    .attr("viewBox", `0 0 ${width} ${height}`)
    .attr("preserveAspectRatio", "xMidYMid meet")
    .style("width", "100%")
    .style("height", "auto")
    .style("max-width", `${width}px`);

  const g = svg.append("g")
    .attr("transform", `translate(${margin.left},${margin.top})`);
  
  // ========================================
  // Y-AXIS
  // ========================================
  const yTicks = PlotHelpers.calculateYTicks(innerHeight);
  const yAxisGroup = g.append("g").attr("class", "y-axis");
  const yAxisCall = d3.axisLeft(yScale)
    .ticks(yTicks)
    .tickSizeOuter(0)
    .tickSizeInner(-innerWidth)
    .tickFormat(d3.format("~s"));

  yAxisGroup.call(yAxisCall);
  yAxisGroup.selectAll(".tick text")
    .style("font-size", `${fontSizes.yAxisTick}px`);
    
  // ========================================
  // BARS
  // ========================================
  // gray background bars
  g.selectAll(".background-bar")
    .data(completeData)
    .enter().append("rect")
    .attr("class", "background-bar")
    .attr("x", d => xScale(d.bin))
    .attr("width", xScale.bandwidth())
    .attr("y", 0)
    .attr("height", innerHeight);
    
  // data bars with smart tooltip (to avoid bleeding off screen)
  g.selectAll(".data-bar")
    .data(completeData.filter(d => d.percentage > 0))
    .enter().append("rect")
    .attr("class", "data-bar")
    .attr("x", d => xScale(d.bin))
    .attr("width", xScale.bandwidth())
    .attr("y", d => yScale(d.percentage))
    .attr("height", d => innerHeight - yScale(d.percentage))
    .attr("fill", d => rwiFill(d))
    .attr("fill-opacity", 1)
    .attr("stroke", d => d3.color(rwiFill(d)).darker(0.3))
    .attr("stroke-width", 1)
    .style("cursor", "default")
    .on("mouseover", function(event, d) {
      d3.selectAll(".d3-tooltip").remove();

      const tooltip = d3.select("body").append("div")
        .attr("class", "d3-tooltip")
        .style("opacity", 0);
        
      const html = `<div>RWI Wealth Category: ${d.bin}</div><div>Percentage of Area: ${d.percentage.toFixed(1)}%</div>`;
      
      // calculate position to avoid bleeding off screen
      const tooltipWidth = 220;
      const windowWidth = window.innerWidth;
      const mouseX = event.pageX;
      
      let leftPos = mouseX + 10;
      if (leftPos + tooltipWidth > windowWidth) {
        leftPos = mouseX - tooltipWidth - 10;
      }
      
      tooltip
        .html(html)
        .style("left", leftPos + "px")
        .style("top", (event.pageY - 35) + "px")
        .transition()
        .duration(200)
        .style("opacity", 1);
    })
    .on("mousemove", function(event) {
      const tooltip = d3.select(".d3-tooltip");
      if (!tooltip.empty()) {
        const tooltipWidth = 220;
        const windowWidth = window.innerWidth;
        const mouseX = event.pageX;
        
        let leftPos = mouseX + 10;
        if (leftPos + tooltipWidth > windowWidth) {
          leftPos = mouseX - tooltipWidth - 10;
        }
        
        tooltip
          .style("left", leftPos + "px")
          .style("top", (event.pageY - 35) + "px");
      }
    })
    .on("mouseout", function() {
      d3.select(".d3-tooltip")
        .transition()
        .duration(200)
        .style("opacity", 0)
        .remove();
    });

  // ========================================
  // BAR PERCENTAGE LABELS
  // ========================================
  g.selectAll(".bar-label")
    .data(completeData)
    .enter().append("text")
    .attr("class", "plot-bar-label")
    .attr("x", d => xScale(d.bin) + xScale.bandwidth()/2)
    .attr("y", d => d.percentage > 0 ? yScale(d.percentage) - 8 : innerHeight/2)
    .attr("text-anchor", "middle")
    .attr("fill", d => d.percentage > 0 ? "black" : "#6c757d")
    .style("font-size", `${fontSizes.barLabel}px`)
    .attr("font-style", d => d.percentage > 0 ? "normal" : "italic")
    .text(d => d.percentage > 0 ? `${d.percentage.toFixed(1)}%` : "")
    .style("display", d => d.percentage > 2 || d.percentage === 0 ? "block" : "none");

  // ========================================
  // X-AXIS
  // ========================================
  const xAxisGroup = g.append("g")
    .attr("class", "x-axis")
    .attr("transform", `translate(0,${innerHeight})`);
    
  xAxisGroup.call(d3.axisBottom(xScale)
    .tickSizeOuter(0)
    .tickSizeInner(0));
 
  // x-axis tick labels with wrapping
  const barWidth = xScale.bandwidth();
  const xAxisTickSize = PlotHelpers.calculateXAxisTickSize(barWidth);
  
  xAxisGroup.selectAll(".tick text")
    .each(function(d) {
      const text = d3.select(this);
      const labelText = text.text();
      
      text.style("font-size", `${xAxisTickSize}px`);
      
      const lines = PlotHelpers.wrapBarLabel(labelText, barWidth, `${xAxisTickSize}px system-ui`);
      text.text(null);
      
      lines.forEach((line, i) => {
        text.append("tspan")
          .attr("x", 0)
          .attr("dy", i === 0 ? "1.2em" : "1.1em")
          .text(line);
      });
    });
    
  // ========================================
  // TITLE
  // ========================================
  const heightScale = height / PlotHelpers.PLOT_BASE.HEIGHT;
  const titleY = PlotHelpers.getTitleY(height, heightScale);
  
  titleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-title")
      .attr("x", 20)
      .attr("y", titleY + (i * lineHeights.title))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.title}px`)
      .text(line);
  });
    
  // ========================================
  // SUBTITLE
  // ========================================
  const subtitleY = PlotHelpers.getSubtitleY(titleY, titleLines.length, lineHeights.title, heightScale);
  
  subtitleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-subtitle")
      .attr("x", 20)
      .attr("y", subtitleY + (i * lineHeights.subtitle))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.subtitle}px`)
      .text(line);
  });
    
  // ========================================
  // Y-AXIS LABEL
  // ========================================
  const widthScale = width / PlotHelpers.PLOT_BASE.WIDTH;
  const yAxisLabelX = -(margin.top + innerHeight/2);
  const yAxisLabelY = PlotHelpers.getYAxisLabelY(widthScale);
  
  yAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("transform", "rotate(-90)")
      .attr("y", yAxisLabelY + (i * lineHeights.axisLabel))
      .attr("x", yAxisLabelX)
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // X-AXIS LABEL
  // ========================================
  const xAxisLabelX = margin.left + innerWidth/2;
  const xAxisLabelY = PlotHelpers.getXAxisLabelY(height, captionHeight, heightScale);
  
  xAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("x", xAxisLabelX)
      .attr("y", xAxisLabelY - ((xAxisLabelLines.length - 1 - i) * lineHeights.axisLabel))
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // CAPTION
  // ========================================
  const captionY = PlotHelpers.getCaptionY(height, heightScale);
  
  captionLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-caption")
      .attr("x", 20)
      .attr("y", captionY - ((captionLines.length - 1 - i) * lineHeights.caption))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.caption}px`)
      .text(line);
  });
  
  return svg.node();
}


// ------------------------------------------------------------
// plot_uba_area
// ------------------------------------------------------------
function plot_uba_area(uba_area, {
  cityName = globalCity, 
  countryName = globalCountry,
  width,
  height
} = {}) {
  
  // ========================================
  // DATA PREPARATION
  // ========================================
  const sortedData = uba_area.slice().sort((a, b) => 
    PlotHelpers.parseUbaAreaRange(a.bin) - PlotHelpers.parseUbaAreaRange(b.bin)
  );

  // color mapping for years
  const ubaAreaColorMap = {
    "Before 1985": "#f6f5d6",
    "1986-1995": "#e5c782",
    "1996-2005": "#cc7b6f",
    "2006-2015": "#62534e"
  };
  const defaultColor = "#999999"; // (fallback gray if no color map match)
  
  const allUbaAreaBins = sortedData.map(d => d.bin);
  
  // complete data with gray bars for visual completeness
  const completeData = allUbaAreaBins.map(bin => {
    const existing = sortedData.find(d => d.bin === bin);
    return existing || { bin, count: 0, percentage: 0 };
  });

  // ========================================
  // STYLING CALCULATIONS
  // ========================================
  // (use helper functions from plot-helpers.js for all styling calculations)
  const fontSizes = PlotHelpers.calculateFontSizes(width, height);
  const lineHeights = PlotHelpers.calculateLineHeights(fontSizes);
  
  // text content
  const titleText = "Urban Built-Up Area Expansion";
  const titleLocation = countryName ? `${cityName}, ${countryName}` : cityName;
  const xAxisLabelText = "Year of Urban Expansion";
  const yAxisLabelText = "Percentage of Area (%)";
  const captionText = "Data: DLR, 2015, \"World Settlement Footprint Evolution - Landsat 5/7 - Global\"";
  
  // text wrapping
  const titleLines = PlotHelpers.wrapText(titleText, width - 40, `${fontSizes.title}px system-ui`);
  const subtitleLines = PlotHelpers.wrapText(titleLocation, width - 40, `${fontSizes.subtitle}px system-ui`);
  const xAxisLabelLines = PlotHelpers.wrapText(xAxisLabelText, width * 0.8, `${fontSizes.axisLabel}px system-ui`);
  const yAxisLabelLines = PlotHelpers.wrapText(yAxisLabelText, height * 0.6, `${fontSizes.axisLabel}px system-ui`);
  const captionLines = PlotHelpers.wrapText(captionText, width - 40, `${fontSizes.caption}px system-ui`);

  // calculate text dimensions for margins
  const titleHeight = titleLines.length * lineHeights.title;
  const subtitleHeight = subtitleLines.length * lineHeights.subtitle;
  const xAxisLabelHeight = xAxisLabelLines.length * lineHeights.axisLabel;
  const captionHeight = captionLines.length * lineHeights.caption;
  const yAxisLabelWidth = yAxisLabelLines.length * lineHeights.axisLabel;

  // calculate margins using helper
  const margin = PlotHelpers.calculateMargins(width, height, {
    titleHeight,
    subtitleHeight,
    xAxisLabelHeight,
    captionHeight,
    yAxisLabelWidth
  });
  
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  
  // ========================================
  // SCALES
  // ========================================
  const xScale = d3.scaleBand()
    .domain(completeData.map(d => d.bin))
    .range([0, innerWidth])
    .padding(0.1);
    
  const yScale = d3.scaleLinear()
    .domain([0, 100])
    .range([innerHeight, 0]);

  // ========================================
  // SVG CREATION
  // ========================================
  const svg = d3.create("svg")
    .attr("viewBox", `0 0 ${width} ${height}`)
    .attr("preserveAspectRatio", "xMidYMid meet")
    .style("width", "100%")
    .style("height", "auto")
    .style("max-width", `${width}px`);

  const g = svg.append("g")
    .attr("transform", `translate(${margin.left},${margin.top})`);
  
  // ========================================
  // Y-AXIS
  // ========================================
  const yTicks = PlotHelpers.calculateYTicks(innerHeight);
  const yAxisGroup = g.append("g").attr("class", "y-axis");
  const yAxisCall = d3.axisLeft(yScale)
    .ticks(yTicks)
    .tickSizeOuter(0)
    .tickSizeInner(-innerWidth)
    .tickFormat(d3.format("~s"));

  yAxisGroup.call(yAxisCall);
  yAxisGroup.selectAll(".tick text")
    .style("font-size", `${fontSizes.yAxisTick}px`);
    
  // ========================================
  // BARS
  // ========================================
  // gray background bars
  g.selectAll(".background-bar")
    .data(completeData)
    .enter().append("rect")
    .attr("class", "background-bar")
    .attr("x", d => xScale(d.bin))
    .attr("width", xScale.bandwidth())
    .attr("y", 0)
    .attr("height", innerHeight);
    
  // data bars with smart tooltips (to avoid bleeding off screen)
  g.selectAll(".data-bar")
    .data(completeData.filter(d => d.percentage > 0))
    .enter().append("rect")
    .attr("class", "data-bar")
    .attr("x", d => xScale(d.bin))
    .attr("width", xScale.bandwidth())
    .attr("y", d => yScale(d.percentage))
    .attr("height", d => innerHeight - yScale(d.percentage))
    .attr("fill", d => ubaAreaColorMap[d.bin] || defaultColor)
    .attr("fill-opacity", 1)
    .attr("stroke", d => d3.color(ubaAreaColorMap[d.bin] || defaultColor).darker(0.3))
    .attr("stroke-width", 1)
    .style("cursor", "default")
    .on("mouseover", function(event, d) {
      d3.selectAll(".d3-tooltip").remove();

      const tooltip = d3.select("body").append("div")
        .attr("class", "d3-tooltip")
        .style("opacity", 0);
        
      const html = `<div>Year: ${d.year}</div><div>Percentage of Area: ${d.percentage.toFixed(1)}%</div>`;
      
      // calculate position to avoid bleeding off screen
      const tooltipWidth = 220;
      const windowWidth = window.innerWidth;
      const mouseX = event.pageX;
      
      let leftPos = mouseX + 10;
      if (leftPos + tooltipWidth > windowWidth) {
        leftPos = mouseX - tooltipWidth - 10;
      }
      
      tooltip
        .html(html)
        .style("left", leftPos + "px")
        .style("top", (event.pageY - 35) + "px")
        .transition()
        .duration(200)
        .style("opacity", 1);
    })
    .on("mousemove", function(event) {
      const tooltip = d3.select(".d3-tooltip");
      if (!tooltip.empty()) {
        const tooltipWidth = 220;
        const windowWidth = window.innerWidth;
        const mouseX = event.pageX;
        
        let leftPos = mouseX + 10;
        if (leftPos + tooltipWidth > windowWidth) {
          leftPos = mouseX - tooltipWidth - 10;
        }
        
        tooltip
          .style("left", leftPos + "px")
          .style("top", (event.pageY - 35) + "px");
      }
    })
    .on("mouseout", function() {
      d3.select(".d3-tooltip")
        .transition()
        .duration(200)
        .style("opacity", 0)
        .remove();
    });

  // ========================================
  // BAR PERCENTAGE LABELS
  // ========================================
  g.selectAll(".bar-label")
    .data(completeData)
    .enter().append("text")
    .attr("class", "plot-bar-label")
    .attr("x", d => xScale(d.bin) + xScale.bandwidth()/2)
    .attr("y", d => d.percentage > 0 ? yScale(d.percentage) - 8 : innerHeight/2)
    .attr("text-anchor", "middle")
    .attr("fill", d => d.percentage > 0 ? "black" : "#6c757d")
    .style("font-size", `${fontSizes.barLabel}px`)
    .attr("font-style", d => d.percentage > 0 ? "normal" : "italic")
    .text(d => d.percentage > 0 ? `${d.percentage.toFixed(1)}%` : "")
    .style("display", d => d.percentage > 2 || d.percentage === 0 ? "block" : "none");

  // ========================================
  // X-AXIS
  // ========================================
  const xAxisGroup = g.append("g")
    .attr("class", "x-axis")
    .attr("transform", `translate(0,${innerHeight})`);
    
  xAxisGroup.call(d3.axisBottom(xScale)
    .tickSizeOuter(0)
    .tickSizeInner(0));
 
  // x-axis tick labels with wrapping
  const barWidth = xScale.bandwidth();
  const xAxisTickSize = PlotHelpers.calculateXAxisTickSize(barWidth);
  
  xAxisGroup.selectAll(".tick text")
    .each(function(d) {
      const text = d3.select(this);
      const labelText = text.text();
      
      text.style("font-size", `${xAxisTickSize}px`);
      
      const lines = PlotHelpers.wrapBarLabel(labelText, barWidth, `${xAxisTickSize}px system-ui`);
      text.text(null);
      
      lines.forEach((line, i) => {
        text.append("tspan")
          .attr("x", 0)
          .attr("dy", i === 0 ? "1.2em" : "1.1em")
          .text(line);
      });
    });
    
  // ========================================
  // TITLE
  // ========================================
  const heightScale = height / PlotHelpers.PLOT_BASE.HEIGHT;
  const titleY = PlotHelpers.getTitleY(height, heightScale);
  
  titleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-title")
      .attr("x", 20)
      .attr("y", titleY + (i * lineHeights.title))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.title}px`)
      .text(line);
  });
    
  // ========================================
  // SUBTITLE
  // ========================================
  const subtitleY = PlotHelpers.getSubtitleY(titleY, titleLines.length, lineHeights.title, heightScale);
  
  subtitleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-subtitle")
      .attr("x", 20)
      .attr("y", subtitleY + (i * lineHeights.subtitle))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.subtitle}px`)
      .text(line);
  });
    
  // ========================================
  // Y-AXIS LABEL
  // ========================================
  const widthScale = width / PlotHelpers.PLOT_BASE.WIDTH;
  const yAxisLabelX = -(margin.top + innerHeight/2);
  const yAxisLabelY = PlotHelpers.getYAxisLabelY(widthScale);
  
  yAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("transform", "rotate(-90)")
      .attr("y", yAxisLabelY + (i * lineHeights.axisLabel))
      .attr("x", yAxisLabelX)
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // X-AXIS LABEL
  // ========================================
  const xAxisLabelX = margin.left + innerWidth/2;
  const xAxisLabelY = PlotHelpers.getXAxisLabelY(height, captionHeight, heightScale);
  
  xAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("x", xAxisLabelX)
      .attr("y", xAxisLabelY - ((xAxisLabelLines.length - 1 - i) * lineHeights.axisLabel))
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // CAPTION
  // ========================================
  const captionY = PlotHelpers.getCaptionY(height, heightScale);
  
  captionLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-caption")
      .attr("x", 20)
      .attr("y", captionY - ((captionLines.length - 1 - i) * lineHeights.caption))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.caption}px`)
      .text(line);
  });
  
  return svg.node();
}


// ------------------------------------------------------------
// plot_ubaa
// ------------------------------------------------------------
function plot_ubaa(uba, {
  cityName = globalCity,
  countryName = globalCountry,
  width,
  height
} = {}) {
  
  // ========================================
  // DATA PREPARATION
  // ========================================
  // get year range for title
  // keep the harmonized series only (wsf_harmonized.csv mixes several sources) and map
  // its columns (year / cumulative_sq_km) to what this chart reads (team fix)
  uba = uba.filter(d => !d.source || d.source === "WSF Harmonized")
           .map((d, i) => ({ year: i + 1,
                             yearName: +(d.yearName ?? d.year),
                             uba: +(d.uba ?? d.cumulative_sq_km) }));
  const minYear = d3.min(uba, d => d.yearName);
  const maxYear = d3.max(uba, d => d.yearName);

  // ========================================
  // STYLING CALCULATIONS
  // ========================================
  // (use helper functions from plot-helpers.js for all styling calculations)
  const fontSizes = PlotHelpers.calculateFontSizes(width, height);
  const lineHeights = PlotHelpers.calculateLineHeights(fontSizes);
  
  // text content
  const titleText = `Urban Built-up Area, ${minYear}-${maxYear}`;
  const titleLocation = cityName;
  const xAxisLabelText = "Year";
  const yAxisLabelText = "Urban Built-up Area (sq km)";
  const captionText = ""; // (empty for this plot)
  
  // text wrapping
  const titleLines = PlotHelpers.wrapText(titleText, width - 40, `${fontSizes.title}px system-ui`);
  const subtitleLines = PlotHelpers.wrapText(titleLocation, width - 40, `${fontSizes.subtitle}px system-ui`);
  const xAxisLabelLines = PlotHelpers.wrapText(xAxisLabelText, width * 0.8, `${fontSizes.axisLabel}px system-ui`);
  const yAxisLabelLines = PlotHelpers.wrapText(yAxisLabelText, height * 0.6, `${fontSizes.axisLabel}px system-ui`);
  const captionLines = PlotHelpers.wrapText(captionText, width - 40, `${fontSizes.caption}px system-ui`);

  // calculate text dimensions for margins
  const titleHeight = titleLines.length * lineHeights.title;
  const subtitleHeight = subtitleLines.length * lineHeights.subtitle;
  const xAxisLabelHeight = xAxisLabelLines.length * lineHeights.axisLabel;
  const captionHeight = captionLines.length * lineHeights.caption;
  const yAxisLabelWidth = yAxisLabelLines.length * lineHeights.axisLabel;

  // calculate margins using helper
  const margin = PlotHelpers.calculateMargins(width, height, {
    titleHeight,
    subtitleHeight,
    xAxisLabelHeight,
    captionHeight,
    yAxisLabelWidth
  });
  
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  
  // ========================================
  // SCALES
  // ========================================
  // (linear scales for line charts)
  const xScale = d3.scaleLinear()
    .domain(d3.extent(uba, d => d.yearName))
    .range([0, innerWidth]);
    
  const yScale = d3.scaleLinear()
    .domain([0, Math.max(...uba.map(d => d.uba)) * 1.1])
    .range([innerHeight, 0]);

  // ========================================
  // SVG CREATION
  // ========================================
  const svg = d3.create("svg")
    .attr("viewBox", `0 0 ${width} ${height}`)
    .attr("preserveAspectRatio", "xMidYMid meet")
    .style("width", "100%")
    .style("height", "auto")
    .style("max-width", `${width}px`);

  const g = svg.append("g")
    .attr("transform", `translate(${margin.left},${margin.top})`);
  
  // ========================================
  // Y-AXIS
  // ========================================
  const yTicks = PlotHelpers.calculateYTicks(innerHeight);
  const yAxisGroup = g.append("g").attr("class", "y-axis");
  const yAxisCall = d3.axisLeft(yScale)
    .ticks(yTicks)
    .tickSizeOuter(0)
    .tickSizeInner(-innerWidth)
    .tickFormat(d3.format("~s"));

  yAxisGroup.call(yAxisCall);
  yAxisGroup.selectAll(".tick text")
    .style("font-size", `${fontSizes.yAxisTick}px`);
  
  // ========================================
  // X-AXIS
  // ========================================
  const tickCount = PlotHelpers.calculateXAxisTickCount(innerWidth);
  
  const xAxisGroup = g.append("g")
    .attr("class", "x-axis")
    .attr("transform", `translate(0,${innerHeight})`);
    
  xAxisGroup.call(d3.axisBottom(xScale)
    .ticks(tickCount) // smart tick count based on width
    .tickFormat(d3.format("d"))  // simple integer format for years
    .tickSizeOuter(0)
    .tickSizeInner(-innerHeight));

  // x-axis tick labels with wrapping
  const tickSpacing = innerWidth / tickCount;
  xAxisGroup.selectAll(".tick text")
    .each(function() {
      const text = d3.select(this);
      const labelText = text.text();
      
      text.style("font-size", `${fontSizes.xAxisTick}px`);
      
      const lines = PlotHelpers.wrapLineChartLabel(labelText, tickSpacing, `${fontSizes.xAxisTick}px system-ui`);
      text.text(null);
      
      lines.forEach((line, i) => {
        text.append("tspan")
          .attr("x", 0)
          .attr("dy", i === 0 ? "1.2em" : "1.1em")
          .text(line);
      });
    });
  
  // ========================================
  // LINE
  // ========================================
  const line = d3.line()
    .defined(d => d.uba !== null) // (skip null values)
    .x(d => xScale(d.yearName))
    .y(d => yScale(d.uba));
    
  g.append("path")
    .datum(uba)
    .attr("fill", "none")
    .attr("stroke", "black")
    .attr("stroke-width", Math.max(1.5, Math.min(3, width / 400)))
    .attr("d", line);
  
  // ========================================
  // DOTS
  // ========================================
  g.selectAll(".dot")
    .data(uba.filter(d => d.uba !== null)) // (skip null values)
    .enter().append("circle")
    .attr("class", "dot")
    .attr("cx", d => xScale(d.yearName))
    .attr("cy", d => yScale(d.uba))
    .attr("r", Math.max(2, Math.min(3, width / 200)))
    .attr("fill", "black")
    .style("cursor", "default")
    .on("mouseover", function(event, d) {
      d3.selectAll(".d3-tooltip").remove();

      const tooltip = d3.select("body").append("div")
        .attr("class", "d3-tooltip")
        .style("opacity", 0);
        
      const html = `<div>Year: ${d.yearName}</div><div>Urban Built-up Area: ${d.uba.toLocaleString()} sq km</div>`;
      
      // calculate position to avoid bleeding off screen
      const tooltipWidth = 220;
      const windowWidth = window.innerWidth;
      const mouseX = event.pageX;
      
      let leftPos = mouseX + 10;
      if (leftPos + tooltipWidth > windowWidth) {
        leftPos = mouseX - tooltipWidth - 10;
      }
      
      tooltip
        .html(html)
        .style("left", leftPos + "px")
        .style("top", (event.pageY - 35) + "px")
        .transition()
        .duration(200)
        .style("opacity", 1);
    })
    .on("mousemove", function(event) {
      const tooltip = d3.select(".d3-tooltip");
      if (!tooltip.empty()) {
        const tooltipWidth = 220;
        const windowWidth = window.innerWidth;
        const mouseX = event.pageX;
        
        let leftPos = mouseX + 10;
        if (leftPos + tooltipWidth > windowWidth) {
          leftPos = mouseX - tooltipWidth - 10;
        }
        
        tooltip
          .style("left", leftPos + "px")
          .style("top", (event.pageY - 35) + "px");
      }
    })
    .on("mouseout", function() {
      d3.select(".d3-tooltip")
        .transition()
        .duration(200)
        .style("opacity", 0)
        .remove();
    });
  
  // ========================================
  // TITLE
  // ========================================
  const heightScale = height / PlotHelpers.PLOT_BASE.HEIGHT;
  const titleY = PlotHelpers.getTitleY(height, heightScale);
  
  titleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-title")
      .attr("x", 20)
      .attr("y", titleY + (i * lineHeights.title))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.title}px`)
      .text(line);
  });
    
  // ========================================
  // SUBTITLE
  // ========================================
  const subtitleY = PlotHelpers.getSubtitleY(titleY, titleLines.length, lineHeights.title, heightScale);
  
  subtitleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-subtitle")
      .attr("x", 20)
      .attr("y", subtitleY + (i * lineHeights.subtitle))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.subtitle}px`)
      .text(line);
  });
    
  // ========================================
  // Y-AXIS LABEL
  // ========================================
  const widthScale = width / PlotHelpers.PLOT_BASE.WIDTH;
  const yAxisLabelX = -(margin.top + innerHeight/2);
  const yAxisLabelY = PlotHelpers.getYAxisLabelY(widthScale);
  
  yAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("transform", "rotate(-90)")
      .attr("y", yAxisLabelY + (i * lineHeights.axisLabel))
      .attr("x", yAxisLabelX)
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // X-AXIS LABEL
  // ========================================
  const xAxisLabelX = margin.left + innerWidth/2;
  const xAxisLabelY = PlotHelpers.getXAxisLabelY(height, captionHeight, heightScale);
  
  xAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("x", xAxisLabelX)
      .attr("y", xAxisLabelY - ((xAxisLabelLines.length - 1 - i) * lineHeights.axisLabel))
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // CAPTION
  // ========================================
  // (empty for this plot)
  if (captionText) {
    const captionY = PlotHelpers.getCaptionY(height, heightScale);
    
    captionLines.forEach((line, i) => {
      svg.append("text")
        .attr("class", "plot-caption")
        .attr("x", 20)
        .attr("y", captionY - ((captionLines.length - 1 - i) * lineHeights.caption))
        .attr("text-anchor", "start")
        .style("font-size", `${fontSizes.caption}px`)
        .text(line);
    });
  }
  
  return svg.node();
}


// ------------------------------------------------------------
// plot_wsf_harmonized
// ------------------------------------------------------------
function plot_wsf_harmonized(data, {
  cityName = globalCity,
  countryName = globalCountry,
  width,
  height,
  separate = false
} = {}) {
  
  // ========================================
  // DATA PREPARATION
  // ========================================
  if (!data || !data.length) return null;  // no data -> render nothing
  // wsf_harmonized.csv mixes several sources: show the harmonized series, or (separate)
  // the WSF Evolution and WSF Tracker series side by side (team options)
  const _bySource = src => data
    .filter(d => d.source === src && d.cumulative_sq_km != null && d.cumulative_sq_km !== "" && !isNaN(+d.cumulative_sq_km))
    .map(d => ({ yearName: +d.year, value: +d.cumulative_sq_km }))
    .sort((p, q) => p.yearName - q.yearName);
  const series = (separate
    ? [ { label: "WSF Evolution", color: "#2166ac", dash: "6,3", data: _bySource("WSF Evolution") },
        { label: "WSF Tracker",   color: "#b2182b", dash: "6,3", data: _bySource("WSF Tracker") } ]
    : [ { label: "WSF Harmonized", color: "black", dash: null, data: _bySource("WSF Harmonized") } ]
  ).filter(sr => sr.data.length);
  if (!series.length) return null;
  const allPoints = series.flatMap(sr => sr.data);
  const minYear = d3.min(allPoints, d => d.yearName);
  const maxYear = d3.max(allPoints, d => d.yearName);

  // ========================================
  // STYLING CALCULATIONS
  // ========================================
  // (use helper functions from plot-helpers.js for all styling calculations)
  const fontSizes = PlotHelpers.calculateFontSizes(width, height);
  const lineHeights = PlotHelpers.calculateLineHeights(fontSizes);
  
  // text content
  const titleText = `Urban Built-up Area, ${minYear}-${maxYear}`;
  const titleLocation = cityName;
  const xAxisLabelText = "Year";
  const yAxisLabelText = "Urban Built-up Area (sq km)";
  const captionText = ""; // (empty for this plot)
  
  // text wrapping
  const titleLines = PlotHelpers.wrapText(titleText, width - 40, `${fontSizes.title}px system-ui`);
  const subtitleLines = PlotHelpers.wrapText(titleLocation, width - 40, `${fontSizes.subtitle}px system-ui`);
  const xAxisLabelLines = PlotHelpers.wrapText(xAxisLabelText, width * 0.8, `${fontSizes.axisLabel}px system-ui`);
  const yAxisLabelLines = PlotHelpers.wrapText(yAxisLabelText, height * 0.6, `${fontSizes.axisLabel}px system-ui`);
  const captionLines = PlotHelpers.wrapText(captionText, width - 40, `${fontSizes.caption}px system-ui`);

  // calculate text dimensions for margins
  const titleHeight = titleLines.length * lineHeights.title;
  const subtitleHeight = subtitleLines.length * lineHeights.subtitle;
  const xAxisLabelHeight = xAxisLabelLines.length * lineHeights.axisLabel;
  const captionHeight = captionLines.length * lineHeights.caption;
  const yAxisLabelWidth = yAxisLabelLines.length * lineHeights.axisLabel;

  // calculate margins using helper
  const margin = PlotHelpers.calculateMargins(width, height, {
    titleHeight,
    subtitleHeight,
    xAxisLabelHeight,
    captionHeight,
    yAxisLabelWidth
  });
  
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  
  // ========================================
  // SCALES
  // ========================================
  // (linear scales for line charts)
  const xScale = d3.scaleLinear()
    .domain([minYear, maxYear])
    .range([0, innerWidth]);
    
  const yScale = d3.scaleLinear()
    .domain([Math.min(0, d3.min(allPoints, d => d.value) * 1.1), (d3.max(allPoints, d => d.value) || 1) * 1.1])
    .range([innerHeight, 0]);

  // ========================================
  // SVG CREATION
  // ========================================
  const svg = d3.create("svg")
    .attr("viewBox", `0 0 ${width} ${height}`)
    .attr("preserveAspectRatio", "xMidYMid meet")
    .style("width", "100%")
    .style("height", "auto")
    .style("max-width", `${width}px`);

  const g = svg.append("g")
    .attr("transform", `translate(${margin.left},${margin.top})`);
  
  // ========================================
  // Y-AXIS
  // ========================================
  const yTicks = PlotHelpers.calculateYTicks(innerHeight);
  const yAxisGroup = g.append("g").attr("class", "y-axis");
  const yAxisCall = d3.axisLeft(yScale)
    .ticks(yTicks)
    .tickSizeOuter(0)
    .tickSizeInner(-innerWidth)
    .tickFormat(d => d === 0 ? "0" : (Math.abs(d) < 1 ? d.toFixed(2) : d3.format("~s")(d)));

  yAxisGroup.call(yAxisCall);
  yAxisGroup.selectAll(".tick text")
    .style("font-size", `${fontSizes.yAxisTick}px`);
  
  // ========================================
  // X-AXIS
  // ========================================
  const tickCount = PlotHelpers.calculateXAxisTickCount(innerWidth);
  
  const xAxisGroup = g.append("g")
    .attr("class", "x-axis")
    .attr("transform", `translate(0,${innerHeight})`);
    
  xAxisGroup.call(d3.axisBottom(xScale)
    .ticks(tickCount) // smart tick count based on width
    .tickFormat(d3.format("d"))  // simple integer format for years
    .tickSizeOuter(0)
    .tickSizeInner(-innerHeight));

  // x-axis tick labels with wrapping
  const tickSpacing = innerWidth / tickCount;
  xAxisGroup.selectAll(".tick text")
    .each(function() {
      const text = d3.select(this);
      const labelText = text.text();
      
      text.style("font-size", `${fontSizes.xAxisTick}px`);
      
      const lines = PlotHelpers.wrapLineChartLabel(labelText, tickSpacing, `${fontSizes.xAxisTick}px system-ui`);
      text.text(null);
      
      lines.forEach((line, i) => {
        text.append("tspan")
          .attr("x", 0)
          .attr("dy", i === 0 ? "1.2em" : "1.1em")
          .text(line);
      });
    });
  
  // ========================================
  // LINES + DOTS (one per series)
  // ========================================
  const line = d3.line()
    .defined(d => d.value !== null)
    .x(d => xScale(d.yearName))
    .y(d => yScale(d.value));
  const _tooltipPos = event => {
    const tooltipWidth = 220;
    let leftPos = event.pageX + 10;
    if (leftPos + tooltipWidth > window.innerWidth) leftPos = event.pageX - tooltipWidth - 10;
    return { left: leftPos + "px", top: (event.pageY - 35) + "px" };
  };
  series.forEach(sr => {
    g.append("path")
      .datum(sr.data)
      .attr("fill", "none")
      .attr("stroke", sr.color)
      .attr("stroke-width", Math.max(1.5, Math.min(3, width / 400)))
      .attr("stroke-dasharray", sr.dash)
      .attr("d", line);
    g.selectAll(null)
      .data(sr.data)
      .enter().append("circle")
      .attr("class", "dot")
      .attr("cx", d => xScale(d.yearName))
      .attr("cy", d => yScale(d.value))
      .attr("r", Math.max(2, Math.min(3, width / 200)))
      .attr("fill", sr.color)
      .style("cursor", "default")
      .on("mouseover", function(event, d) {
        d3.selectAll(".d3-tooltip").remove();
        const pos = _tooltipPos(event);
        d3.select("body").append("div")
          .attr("class", "d3-tooltip")
          .style("opacity", 0)
          .html(`<div>Year: ${d.yearName}</div>` + (series.length > 1 ? `<div>${sr.label}</div>` : "") +
                `<div>Urban Built-up Area: ${d.value.toLocaleString(undefined, {maximumFractionDigits: 2})} sq km</div>`)
          .style("left", pos.left)
          .style("top", pos.top)
          .transition().duration(200).style("opacity", 1);
      })
      .on("mousemove", function(event) {
        const tooltip = d3.select(".d3-tooltip");
        if (!tooltip.empty()) { const pos = _tooltipPos(event); tooltip.style("left", pos.left).style("top", pos.top); }
      })
      .on("mouseout", function() {
        d3.select(".d3-tooltip").transition().duration(200).style("opacity", 0).remove();
      });
  });

  // legend only when comparing sources
  if (series.length > 1) {
    PlotHelpers.addLegend(svg, series.map(sr => ({ label: sr.label, color: sr.color, dashed: !!sr.dash })), width, height, 'top-right');
  }
  
  // ========================================
  // TITLE
  // ========================================
  const heightScale = height / PlotHelpers.PLOT_BASE.HEIGHT;
  const titleY = PlotHelpers.getTitleY(height, heightScale);
  
  titleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-title")
      .attr("x", 20)
      .attr("y", titleY + (i * lineHeights.title))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.title}px`)
      .text(line);
  });
    
  // ========================================
  // SUBTITLE
  // ========================================
  const subtitleY = PlotHelpers.getSubtitleY(titleY, titleLines.length, lineHeights.title, heightScale);
  
  subtitleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-subtitle")
      .attr("x", 20)
      .attr("y", subtitleY + (i * lineHeights.subtitle))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.subtitle}px`)
      .text(line);
  });
    
  // ========================================
  // Y-AXIS LABEL
  // ========================================
  const widthScale = width / PlotHelpers.PLOT_BASE.WIDTH;
  const yAxisLabelX = -(margin.top + innerHeight/2);
  const yAxisLabelY = PlotHelpers.getYAxisLabelY(widthScale);
  
  yAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("transform", "rotate(-90)")
      .attr("y", yAxisLabelY + (i * lineHeights.axisLabel))
      .attr("x", yAxisLabelX)
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // X-AXIS LABEL
  // ========================================
  const xAxisLabelX = margin.left + innerWidth/2;
  const xAxisLabelY = PlotHelpers.getXAxisLabelY(height, captionHeight, heightScale);
  
  xAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("x", xAxisLabelX)
      .attr("y", xAxisLabelY - ((xAxisLabelLines.length - 1 - i) * lineHeights.axisLabel))
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // CAPTION
  // ========================================
  // (empty for this plot)
  if (captionText) {
    const captionY = PlotHelpers.getCaptionY(height, heightScale);
    
    captionLines.forEach((line, i) => {
      svg.append("text")
        .attr("class", "plot-caption")
        .attr("x", 20)
        .attr("y", captionY - ((captionLines.length - 1 - i) * lineHeights.caption))
        .attr("text-anchor", "start")
        .style("font-size", `${fontSizes.caption}px`)
        .text(line);
    });
  }
  
  return svg.node();
}


// ------------------------------------------------------------
// plot_wsf_growth
// ------------------------------------------------------------
function plot_wsf_growth(data, {
  cityName = globalCity,
  countryName = globalCountry,
  width,
  height,
  separate = false,
  smooth = 0   // rolling-average window in years (0/1 = none) (team option)
} = {}) {
  
  // ========================================
  // DATA PREPARATION
  // ========================================
  if (!data || !data.length) return null;  // no data -> render nothing
  // wsf_harmonized.csv mixes several sources: show the harmonized series, or (separate)
  // the WSF Evolution and WSF Tracker series side by side (team options)
  const _bySource = src => data
    .filter(d => d.source === src && d.growth_percentage != null && d.growth_percentage !== "" && !isNaN(+d.growth_percentage))
    .map(d => ({ yearName: +d.year, value: +d.growth_percentage }))
    .sort((p, q) => p.yearName - q.yearName);
  const series = (separate
    ? [ { label: "WSF Evolution", color: "#2166ac", dash: "6,3", data: _bySource("WSF Evolution") },
        { label: "WSF Tracker",   color: "#b2182b", dash: "6,3", data: _bySource("WSF Tracker") } ]
    : [ { label: "WSF Harmonized", color: "black", dash: null, data: _bySource("WSF Harmonized") } ]
  ).filter(sr => sr.data.length);
  // optional rolling average (team option)
  if (smooth > 1) series.forEach(sr => {
    sr.data = sr.data.map((d, i, arr) => {
      const w = arr.slice(Math.max(0, i - Math.floor(smooth / 2)), Math.min(arr.length, i + Math.ceil(smooth / 2)));
      return { ...d, value: Math.round(d3.mean(w, v => v.value) * 100) / 100 };
    });
  });
  if (!series.length) return null;
  const allPoints = series.flatMap(sr => sr.data);
  const minYear = d3.min(allPoints, d => d.yearName);
  const maxYear = d3.max(allPoints, d => d.yearName);

  // ========================================
  // STYLING CALCULATIONS
  // ========================================
  // (use helper functions from plot-helpers.js for all styling calculations)
  const fontSizes = PlotHelpers.calculateFontSizes(width, height);
  const lineHeights = PlotHelpers.calculateLineHeights(fontSizes);
  
  // text content
  const titleText = `Urban Built-up Area Growth Rate, ${minYear}-${maxYear}`;
  const titleLocation = cityName;
  const xAxisLabelText = "Year";
  const yAxisLabelText = "Growth Rate (%)";
  const captionText = ""; // (empty for this plot)
  
  // text wrapping
  const titleLines = PlotHelpers.wrapText(titleText, width - 40, `${fontSizes.title}px system-ui`);
  const subtitleLines = PlotHelpers.wrapText(titleLocation, width - 40, `${fontSizes.subtitle}px system-ui`);
  const xAxisLabelLines = PlotHelpers.wrapText(xAxisLabelText, width * 0.8, `${fontSizes.axisLabel}px system-ui`);
  const yAxisLabelLines = PlotHelpers.wrapText(yAxisLabelText, height * 0.6, `${fontSizes.axisLabel}px system-ui`);
  const captionLines = PlotHelpers.wrapText(captionText, width - 40, `${fontSizes.caption}px system-ui`);

  // calculate text dimensions for margins
  const titleHeight = titleLines.length * lineHeights.title;
  const subtitleHeight = subtitleLines.length * lineHeights.subtitle;
  const xAxisLabelHeight = xAxisLabelLines.length * lineHeights.axisLabel;
  const captionHeight = captionLines.length * lineHeights.caption;
  const yAxisLabelWidth = yAxisLabelLines.length * lineHeights.axisLabel;

  // calculate margins using helper
  const margin = PlotHelpers.calculateMargins(width, height, {
    titleHeight,
    subtitleHeight,
    xAxisLabelHeight,
    captionHeight,
    yAxisLabelWidth
  });
  
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  
  // ========================================
  // SCALES
  // ========================================
  // (linear scales for line charts)
  const xScale = d3.scaleLinear()
    .domain([minYear, maxYear])
    .range([0, innerWidth]);
    
  const yScale = d3.scaleLinear()
    .domain([Math.min(0, d3.min(allPoints, d => d.value) * 1.1), (d3.max(allPoints, d => d.value) || 1) * 1.1])
    .range([innerHeight, 0]);

  // ========================================
  // SVG CREATION
  // ========================================
  const svg = d3.create("svg")
    .attr("viewBox", `0 0 ${width} ${height}`)
    .attr("preserveAspectRatio", "xMidYMid meet")
    .style("width", "100%")
    .style("height", "auto")
    .style("max-width", `${width}px`);

  const g = svg.append("g")
    .attr("transform", `translate(${margin.left},${margin.top})`);
  
  // ========================================
  // Y-AXIS
  // ========================================
  const yTicks = PlotHelpers.calculateYTicks(innerHeight);
  const yAxisGroup = g.append("g").attr("class", "y-axis");
  const yAxisCall = d3.axisLeft(yScale)
    .ticks(yTicks)
    .tickSizeOuter(0)
    .tickSizeInner(-innerWidth)
    .tickFormat(d => d === 0 ? "0" : (Math.abs(d) < 1 ? d.toFixed(2) : d3.format("~s")(d)));

  yAxisGroup.call(yAxisCall);
  yAxisGroup.selectAll(".tick text")
    .style("font-size", `${fontSizes.yAxisTick}px`);
  
  // ========================================
  // X-AXIS
  // ========================================
  const tickCount = PlotHelpers.calculateXAxisTickCount(innerWidth);
  
  const xAxisGroup = g.append("g")
    .attr("class", "x-axis")
    .attr("transform", `translate(0,${innerHeight})`);
    
  xAxisGroup.call(d3.axisBottom(xScale)
    .ticks(tickCount) // smart tick count based on width
    .tickFormat(d3.format("d"))  // simple integer format for years
    .tickSizeOuter(0)
    .tickSizeInner(-innerHeight));

  // x-axis tick labels with wrapping
  const tickSpacing = innerWidth / tickCount;
  xAxisGroup.selectAll(".tick text")
    .each(function() {
      const text = d3.select(this);
      const labelText = text.text();
      
      text.style("font-size", `${fontSizes.xAxisTick}px`);
      
      const lines = PlotHelpers.wrapLineChartLabel(labelText, tickSpacing, `${fontSizes.xAxisTick}px system-ui`);
      text.text(null);
      
      lines.forEach((line, i) => {
        text.append("tspan")
          .attr("x", 0)
          .attr("dy", i === 0 ? "1.2em" : "1.1em")
          .text(line);
      });
    });
  
  // ========================================
  // LINES + DOTS (one per series)
  // ========================================
  const line = d3.line()
    .defined(d => d.value !== null)
    .x(d => xScale(d.yearName))
    .y(d => yScale(d.value));
  const _tooltipPos = event => {
    const tooltipWidth = 220;
    let leftPos = event.pageX + 10;
    if (leftPos + tooltipWidth > window.innerWidth) leftPos = event.pageX - tooltipWidth - 10;
    return { left: leftPos + "px", top: (event.pageY - 35) + "px" };
  };
  series.forEach(sr => {
    g.append("path")
      .datum(sr.data)
      .attr("fill", "none")
      .attr("stroke", sr.color)
      .attr("stroke-width", Math.max(1.5, Math.min(3, width / 400)))
      .attr("stroke-dasharray", sr.dash)
      .attr("d", line);
    g.selectAll(null)
      .data(sr.data)
      .enter().append("circle")
      .attr("class", "dot")
      .attr("cx", d => xScale(d.yearName))
      .attr("cy", d => yScale(d.value))
      .attr("r", Math.max(2, Math.min(3, width / 200)))
      .attr("fill", sr.color)
      .style("cursor", "default")
      .on("mouseover", function(event, d) {
        d3.selectAll(".d3-tooltip").remove();
        const pos = _tooltipPos(event);
        d3.select("body").append("div")
          .attr("class", "d3-tooltip")
          .style("opacity", 0)
          .html(`<div>Year: ${d.yearName}</div>` + (series.length > 1 ? `<div>${sr.label}</div>` : "") +
                `<div>Growth Rate: ${d.value.toLocaleString(undefined, {maximumFractionDigits: 2})}%</div>`)
          .style("left", pos.left)
          .style("top", pos.top)
          .transition().duration(200).style("opacity", 1);
      })
      .on("mousemove", function(event) {
        const tooltip = d3.select(".d3-tooltip");
        if (!tooltip.empty()) { const pos = _tooltipPos(event); tooltip.style("left", pos.left).style("top", pos.top); }
      })
      .on("mouseout", function() {
        d3.select(".d3-tooltip").transition().duration(200).style("opacity", 0).remove();
      });
  });

  // legend only when comparing sources
  if (series.length > 1) {
    PlotHelpers.addLegend(svg, series.map(sr => ({ label: sr.label, color: sr.color, dashed: !!sr.dash })), width, height, 'top-right');
  }
  
  // ========================================
  // TITLE
  // ========================================
  const heightScale = height / PlotHelpers.PLOT_BASE.HEIGHT;
  const titleY = PlotHelpers.getTitleY(height, heightScale);
  
  titleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-title")
      .attr("x", 20)
      .attr("y", titleY + (i * lineHeights.title))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.title}px`)
      .text(line);
  });
    
  // ========================================
  // SUBTITLE
  // ========================================
  const subtitleY = PlotHelpers.getSubtitleY(titleY, titleLines.length, lineHeights.title, heightScale);
  
  subtitleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-subtitle")
      .attr("x", 20)
      .attr("y", subtitleY + (i * lineHeights.subtitle))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.subtitle}px`)
      .text(line);
  });
    
  // ========================================
  // Y-AXIS LABEL
  // ========================================
  const widthScale = width / PlotHelpers.PLOT_BASE.WIDTH;
  const yAxisLabelX = -(margin.top + innerHeight/2);
  const yAxisLabelY = PlotHelpers.getYAxisLabelY(widthScale);
  
  yAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("transform", "rotate(-90)")
      .attr("y", yAxisLabelY + (i * lineHeights.axisLabel))
      .attr("x", yAxisLabelX)
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // X-AXIS LABEL
  // ========================================
  const xAxisLabelX = margin.left + innerWidth/2;
  const xAxisLabelY = PlotHelpers.getXAxisLabelY(height, captionHeight, heightScale);
  
  xAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("x", xAxisLabelX)
      .attr("y", xAxisLabelY - ((xAxisLabelLines.length - 1 - i) * lineHeights.axisLabel))
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // CAPTION
  // ========================================
  // (empty for this plot)
  if (captionText) {
    const captionY = PlotHelpers.getCaptionY(height, heightScale);
    
    captionLines.forEach((line, i) => {
      svg.append("text")
        .attr("class", "plot-caption")
        .attr("x", 20)
        .attr("y", captionY - ((captionLines.length - 1 - i) * lineHeights.caption))
        .attr("text-anchor", "start")
        .style("font-size", `${fontSizes.caption}px`)
        .text(line);
    });
  }
  
  return svg.node();
}


// ------------------------------------------------------------
// plot_ubap
// ------------------------------------------------------------
function plot_ubap(uba, {
  cityName = globalCity,
  countryName = globalCountry,
  width,
  height
} = {}) {
  
  // ========================================
  // DATA PREPARATION
  // ========================================
  // Get year range for title
  const minYear = d3.min(uba, d => d.yearName);
  const maxYear = d3.max(uba, d => d.yearName);

  // ========================================
  // STYLING CALCULATIONS
  // ========================================
  // (use helper functions from plot-helpers.js for all styling calculations)
  const fontSizes = PlotHelpers.calculateFontSizes(width, height);
  const lineHeights = PlotHelpers.calculateLineHeights(fontSizes);
  
  // text content
  const titleText = `Urban Built-up Area Growth Percentage, ${minYear}-${maxYear}`;
  const titleLocation = cityName;
  const xAxisLabelText = "Year";
  const yAxisLabelText = "Urban Built-up area Growth Percentage (%)";
  const captionText = ""; // (empty for this plot)
  
  // text wrapping
  const titleLines = PlotHelpers.wrapText(titleText, width - 40, `${fontSizes.title}px system-ui`);
  const subtitleLines = PlotHelpers.wrapText(titleLocation, width - 40, `${fontSizes.subtitle}px system-ui`);
  const xAxisLabelLines = PlotHelpers.wrapText(xAxisLabelText, width * 0.8, `${fontSizes.axisLabel}px system-ui`);
  const yAxisLabelLines = PlotHelpers.wrapText(yAxisLabelText, height * 0.6, `${fontSizes.axisLabel}px system-ui`);
  const captionLines = PlotHelpers.wrapText(captionText, width - 40, `${fontSizes.caption}px system-ui`);

  // calculate text dimensions for margins
  const titleHeight = titleLines.length * lineHeights.title;
  const subtitleHeight = subtitleLines.length * lineHeights.subtitle;
  const xAxisLabelHeight = xAxisLabelLines.length * lineHeights.axisLabel;
  const captionHeight = captionLines.length * lineHeights.caption;
  const yAxisLabelWidth = yAxisLabelLines.length * lineHeights.axisLabel;

  // calculate margins using helper
  const margin = PlotHelpers.calculateMargins(width, height, {
    titleHeight,
    subtitleHeight,
    xAxisLabelHeight,
    captionHeight,
    yAxisLabelWidth
  });
  
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  
  // ========================================
  // SCALES
  // ========================================
  // (linear scales for line charts)
  const xScale = d3.scaleLinear()
    .domain(d3.extent(uba, d => d.yearName))
    .range([0, innerWidth]);
    
  const yScale = d3.scaleLinear()
    .domain([0, Math.max(...uba.map(d => d.ubaGrowthPercentage)) * 1.1])
    .range([innerHeight, 0]);

  // ========================================
  // SVG CREATION
  // ========================================
  const svg = d3.create("svg")
    .attr("viewBox", `0 0 ${width} ${height}`)
    .attr("preserveAspectRatio", "xMidYMid meet")
    .style("width", "100%")
    .style("height", "auto")
    .style("max-width", `${width}px`);

  const g = svg.append("g")
    .attr("transform", `translate(${margin.left},${margin.top})`);
  
  // ========================================
  // Y-AXIS
  // ========================================
  const yTicks = PlotHelpers.calculateYTicks(innerHeight);
  const yAxisGroup = g.append("g").attr("class", "y-axis");
  const yAxisCall = d3.axisLeft(yScale)
    .ticks(yTicks)
    .tickSizeOuter(0)
    .tickSizeInner(-innerWidth)
    .tickFormat(d => d);

  yAxisGroup.call(yAxisCall);
  yAxisGroup.selectAll(".tick text")
    .style("font-size", `${fontSizes.yAxisTick}px`);
  
  // ========================================
  // X-AXIS
  // ========================================
  const tickCount = PlotHelpers.calculateXAxisTickCount(innerWidth);
  
  const xAxisGroup = g.append("g")
    .attr("class", "x-axis")
    .attr("transform", `translate(0,${innerHeight})`);
    
  xAxisGroup.call(d3.axisBottom(xScale)
    .ticks(tickCount) // smart tick count based on width
    .tickFormat(d3.format("d"))  // simple integer format for years
    .tickSizeOuter(0)
    .tickSizeInner(-innerHeight));

  // x-axis tick labels with wrapping
  const tickSpacing = innerWidth / tickCount;
  xAxisGroup.selectAll(".tick text")
    .each(function() {
      const text = d3.select(this);
      const labelText = text.text();
      
      text.style("font-size", `${fontSizes.xAxisTick}px`);
      
      const lines = PlotHelpers.wrapLineChartLabel(labelText, tickSpacing, `${fontSizes.xAxisTick}px system-ui`);
      text.text(null);

      lines.forEach((line, i) => {
        text.append("tspan")
          .attr("x", 0)
          .attr("dy", i === 0 ? "1.2em" : "1.1em")
          .text(line);
      });
    });
  
  // ========================================
  // LINE
  // ========================================
  const line = d3.line()
    .defined(d => d.ubaGrowthPercentage !== null) // (skip null values)
    .x(d => xScale(d.yearName))
    .y(d => yScale(d.ubaGrowthPercentage));
    
  g.append("path")
    .datum(uba)
    .attr("fill", "none")
    .attr("stroke", "black")
    .attr("stroke-width", Math.max(1.5, Math.min(3, width / 400)))
    .attr("d", line);
  
  // ========================================
  // DOTS
  // ========================================
  g.selectAll(".dot")
    .data(uba.filter(d => d.ubaGrowthPercentage !== null)) // (skip null values)
    .enter().append("circle")
    .attr("class", "dot")
    .attr("cx", d => xScale(d.yearName))
    .attr("cy", d => yScale(d.ubaGrowthPercentage))
    .attr("r", Math.max(2, Math.min(3, width / 200)))
    .attr("fill", "black")
    .style("cursor", "default")
    .on("mouseover", function(event, d) {
      d3.selectAll(".d3-tooltip").remove();

      const tooltip = d3.select("body").append("div")
        .attr("class", "d3-tooltip")
        .style("opacity", 0);
        
      const html = `<div>Year: ${d.yearName}</div><div>Growth Percentage: ${d.ubaGrowthPercentage !== null ? d.ubaGrowthPercentage.toFixed(2) + '%' : 'N/A'}</div>`;
      
      // calculate position to avoid bleeding off screen
      const tooltipWidth = 220;
      const windowWidth = window.innerWidth;
      const mouseX = event.pageX;
      
      let leftPos = mouseX + 10;
      if (leftPos + tooltipWidth > windowWidth) {
        leftPos = mouseX - tooltipWidth - 10;
      }
      
      tooltip
        .html(html)
        .style("left", leftPos + "px")
        .style("top", (event.pageY - 35) + "px")
        .transition()
        .duration(200)
        .style("opacity", 1);
    })
    .on("mousemove", function(event) {
      const tooltip = d3.select(".d3-tooltip");
      if (!tooltip.empty()) {
        const tooltipWidth = 220;
        const windowWidth = window.innerWidth;
        const mouseX = event.pageX;
        
        let leftPos = mouseX + 10;
        if (leftPos + tooltipWidth > windowWidth) {
          leftPos = mouseX - tooltipWidth - 10;
        }
        
        tooltip
          .style("left", leftPos + "px")
          .style("top", (event.pageY - 35) + "px");
      }
    })
    .on("mouseout", function() {
      d3.select(".d3-tooltip")
        .transition()
        .duration(200)
        .style("opacity", 0)
        .remove();
    });
  
  // ========================================
  // TITLE
  // ========================================
  const heightScale = height / PlotHelpers.PLOT_BASE.HEIGHT;
  const titleY = PlotHelpers.getTitleY(height, heightScale);
  
  titleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-title")
      .attr("x", 20)
      .attr("y", titleY + (i * lineHeights.title))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.title}px`)
      .text(line);
  });
    
  // ========================================
  // SUBTITLE
  // ========================================
  const subtitleY = PlotHelpers.getSubtitleY(titleY, titleLines.length, lineHeights.title, heightScale);
  
  subtitleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-subtitle")
      .attr("x", 20)
      .attr("y", subtitleY + (i * lineHeights.subtitle))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.subtitle}px`)
      .text(line);
  });
    
  // ========================================
  // Y-AXIS LABEL
  // ========================================
  const widthScale = width / PlotHelpers.PLOT_BASE.WIDTH;
  const yAxisLabelX = -(margin.top + innerHeight/2);
  const yAxisLabelY = PlotHelpers.getYAxisLabelY(widthScale);
  
  yAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("transform", "rotate(-90)")
      .attr("y", yAxisLabelY + (i * lineHeights.axisLabel))
      .attr("x", yAxisLabelX)
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // X-AXIS LABEL
  // ========================================
  const xAxisLabelX = margin.left + innerWidth/2;
  const xAxisLabelY = PlotHelpers.getXAxisLabelY(height, captionHeight, heightScale);
  
  xAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("x", xAxisLabelX)
      .attr("y", xAxisLabelY - ((xAxisLabelLines.length - 1 - i) * lineHeights.axisLabel))
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // CAPTION
  // ========================================
  // (empty for this plot)
  if (captionText) {
    const captionY = PlotHelpers.getCaptionY(height, heightScale);
    
    captionLines.forEach((line, i) => {
      svg.append("text")
        .attr("class", "plot-caption")
        .attr("x", 20)
        .attr("y", captionY - ((captionLines.length - 1 - i) * lineHeights.caption))
        .attr("text-anchor", "start")
        .style("font-size", `${fontSizes.caption}px`)
        .text(line);
    });
  }
  
  return svg.node();
}


// ------------------------------------------------------------
// plot_lc
// ------------------------------------------------------------
function plot_lc(lc, {
  cityName = globalCity,
  countryName = globalCountry,
  width,
  height
} = {}) {
  
  // ========================================
  // DATA PREPARATION
  // ========================================
  if (!lc || !lc.length) return null;  // no data -> render nothing (team fix)
  // the landcover CSV has "Land Cover Type" + "Pixel Count" (raw counts):
  // map to the fields this chart reads and compute percentages (team fix)
  const lcTotal = lc.reduce((s, d) => s + (+(d["Pixel Count"] ?? d.pixelCount) || 0), 0);
  lc = lc.map(d => {
    const px = +(d["Pixel Count"] ?? d.pixelCount) || 0;
    return { lcType: d["Land Cover Type"] ?? d.lcType, pixelCount: px,
             percentage: d.percentage ?? (lcTotal ? px / lcTotal * 100 : 0) };
  });

  // filter and prepare data
  const filtered = lc
    .filter(d => d.percentage > 0)
    .sort((a, b) => b.percentage - a.percentage);
    
  const hierarchyData = {
    name: `Land Cover in ${cityName}`,
    children: filtered.map(d => ({
      name: d.lcType,
      value: d.percentage,
      pixelCount: d.pixelCount
    }))
  };
  
  // color scale - dynamic mapping based on actual land cover types present in the data
  const landCoverColors = {
    "Cropland": "#eaa86f",
    "Built-up": "#d3605f", 
    "Grassland": "#9bbb7f",
    "Tree cover": "#629777",
    "Permanent water bodies": "#61acdc",
    "Shrubland": "#e2c985",
    "Bare / sparse vegetation": "#b4ada4",
    "Herbaceous wetland": "#979ec9",
    "Snow and ice": "#e2e3e3",
    "Mangroves": "#48d394",
    "Moss and lichens": "#f6eba0"
  };
  
  // color scale based on actual land cover types present in the data
  const actualLandCoverTypes = hierarchyData.children.map(d => d.name);
  const colorScale = d3.scaleOrdinal()
    .domain(actualLandCoverTypes)
    .range(actualLandCoverTypes.map(type => landCoverColors[type] || "#cccccc"));
  
  // ========================================
  // STYLING CALCULATIONS
  // ========================================
  // (use helper functions from plot-helpers.js for all styling calculations)
  const fontSizes = PlotHelpers.calculateFontSizes(width, height);
  const lineHeights = PlotHelpers.calculateLineHeights(fontSizes);
  
  // text content
  const titleText = "Land Cover Types";
  const titleLocation = countryName ? `${cityName}, ${countryName}` : cityName;
  const captionText = ""; // (empty for this plot)

  // text wrapping
  const titleLines = PlotHelpers.wrapText(titleText, width - 40, `${fontSizes.title}px system-ui`);
  const subtitleLines = PlotHelpers.wrapText(titleLocation, width - 40, `${fontSizes.subtitle}px system-ui`);
  const captionLines = PlotHelpers.wrapText(captionText, width - 40, `${fontSizes.caption}px system-ui`);

  // calculate text dimensions
  const titleHeight = titleLines.length * lineHeights.title;
  const subtitleHeight = subtitleLines.length * lineHeights.subtitle;
  const captionHeight = captionText ? captionLines.length * lineHeights.caption : 0;

  
  // treemap top offset for title/subtitle
  const topOffset = titleHeight + subtitleHeight + 10;
  
  // ========================================
  // CREATE HIERARCHY AND LAYOUT
  // ========================================
  const treemapHeight = height - topOffset - (captionHeight > 0 ? captionHeight + 10 : 0);

  const root = d3.hierarchy(hierarchyData)
    .sum(d => d.value)
    .sort((a, b) => b.value - a.value);
    
  d3.treemap()
    .size([width, treemapHeight])
    .padding(2)
    .round(true)(root);
  
  // ========================================
  // SVG CREATION
  // ========================================
  const svg = d3.create("svg")
    .attr("viewBox", `0 0 ${width} ${height}`)
    .attr("preserveAspectRatio", "xMidYMid meet")
    .style("width", "100%")
    .style("height", "auto")
    .style("max-width", `${width}px`);
  
  // ========================================
  // TITLE
  // ========================================
  const heightScale = height / PlotHelpers.PLOT_BASE.HEIGHT;
  const titleY = PlotHelpers.getTitleY(height, heightScale);
  
  titleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-title")
      .attr("x", 20)
      .attr("y", titleY + (i * lineHeights.title))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.title}px`)
      .text(line);
  });
    
  // ========================================
  // SUBTITLE
  // ========================================
  const subtitleY = PlotHelpers.getSubtitleY(titleY, titleLines.length, lineHeights.title, heightScale);
  
  subtitleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-subtitle")
      .attr("x", 20)
      .attr("y", subtitleY + (i * lineHeights.subtitle))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.subtitle}px`)
      .text(line);
  });
  
  // ========================================
  // TREEMAP CELLS
  // ========================================
  const leaf = svg.selectAll("g")
    .data(root.leaves())
    .join("g")
    .attr("transform", d => `translate(${d.x0},${d.y0 + topOffset})`);
    
  // rectangles with tooltips
  leaf.append("rect")
    .attr("fill", d => colorScale(d.data.name))
    .attr("fill-opacity", 0.8)
    .attr("stroke", "white")
    .attr("stroke-width", 2)
    .attr("width", d => d.x1 - d.x0)
    .attr("height", d => d.y1 - d.y0)
    .style("cursor", "default")
    .on("mouseover", function(event, d) {
      d3.select(this).attr("fill-opacity", 1);
      d3.selectAll(".d3-tooltip").remove();
      
      const tooltip = d3.select("body").append("div")
        .attr("class", "d3-tooltip")
        .style("opacity", 0);
        
      const html = `<div><strong>${d.data.name}</strong>: ${(d.data.value ?? 0).toFixed(1)}%</div>`;
      
      const tooltipWidth = 220;
      const windowWidth = window.innerWidth;
      const mouseX = event.pageX;
      
      let leftPos = mouseX + 10;
      if (leftPos + tooltipWidth > windowWidth) {
        leftPos = mouseX - tooltipWidth - 10;
      }
      
      tooltip
        .html(html)
        .style("left", leftPos + "px")
        .style("top", (event.pageY - 35) + "px")
        .transition()
        .duration(200)
        .style("opacity", 1);
    })
    .on("mousemove", function(event) {
      const tooltip = d3.select(".d3-tooltip");
      if (!tooltip.empty()) {
        const tooltipWidth = 220;
        const windowWidth = window.innerWidth;
        const mouseX = event.pageX;
        
        let leftPos = mouseX + 10;
        if (leftPos + tooltipWidth > windowWidth) {
          leftPos = mouseX - tooltipWidth - 10;
        }
        
        tooltip
          .style("left", leftPos + "px")
          .style("top", (event.pageY - 35) + "px");
      }
    })
    .on("mouseout", function() {
      d3.select(this).attr("fill-opacity", 0.8);
      d3.select(".d3-tooltip")
        .transition()
        .duration(200)
        .style("opacity", 0)
        .remove();
    });
    
  // ========================================
  // TREEMAP LABELS
  // ========================================
  leaf.filter(d => PlotHelpers.shouldShowTreemapLabel(d.x1 - d.x0, d.y1 - d.y0))
    .each(function(d) {
      const g = d3.select(this);
      const rectWidth = d.x1 - d.x0;
      
      // calculate dynamic font size using helper
      const dynamicFontSize = PlotHelpers.calculateTreemapLabelSize(rectWidth, width);
      
      // split text into lines using helper
      const lines = PlotHelpers.wrapTreemapLabel(d.data.name, rectWidth, dynamicFontSize);
      
      // add text lines
      lines.forEach((line, i) => {
        if (i < 2) { // (only show first 2 lines)
          g.append("text")
            .attr("x", 4)
            .attr("y", 20 + (i * (dynamicFontSize + 2)))
            .style("font-family", "system-ui")
            .style("font-weight", "450")
            .style("font-size", `${dynamicFontSize}px`)
            .style("fill", "#333")
            .style("pointer-events", "none")
            .text(line);
        }
      });
    });
    
  // ========================================
  // PERCENTAGE LABELS
  // ========================================
  leaf.filter(d => PlotHelpers.shouldShowTreemapPercentage(d.x1 - d.x0, d.y1 - d.y0))
    .append("text")
    .attr("x", 4)
    .attr("y", d => {
      const rectWidth = d.x1 - d.x0;
      const fontSize = PlotHelpers.calculateTreemapPercentageSize(rectWidth, width);
      const labelFontSize = PlotHelpers.calculateTreemapLabelSize(rectWidth, width);
      return 40 + labelFontSize;
    })
    .style("font-family", "system-ui")
    .style("font-size", d => {
      const rectWidth = d.x1 - d.x0;
      return `${PlotHelpers.calculateTreemapPercentageSize(rectWidth, width)}px`;
    })
    .style("fill", "#141414")
    .style("pointer-events", "none")
    .text(d => `${(d.data.value ?? 0).toFixed(1)}%`);

    // ========================================
    // CAPTION
    // ========================================
    // (empty for this plot)
    if (captionText) {
      const captionY = PlotHelpers.getCaptionY(height, heightScale);
      
      captionLines.forEach((line, i) => {
        svg.append("text")
          .attr("class", "plot-caption")
          .attr("x", 20)
          .attr("y", captionY - ((captionLines.length - 1 - i) * lineHeights.caption))
          .attr("text-anchor", "start")
          .style("font-size", `${fontSizes.caption}px`)
          .text(line);
      });
    }
  
  return svg.node();
}


// ------------------------------------------------------------
// plot_uddm
// ------------------------------------------------------------
function plot_uddm(pg, uba, pug, {
  cityName = globalCity,
  countryName = globalCountry,
  width
} = {}) {
  
  // base dimensions for calculations
  const numColumns = 2;
  const gridGap = Math.max(15, width * 0.03);
  const baseChartWidth = 400; // (fixed base for consistent proportions)
  const baseChartHeight = baseChartWidth * 0.75;
  
  const margin = PlotHelpers.calculateChartMargins(baseChartWidth, baseChartHeight);
  const fontSizes = PlotHelpers.calculateMultiChartFontSizes(baseChartWidth);
  const strokeSizes = PlotHelpers.calculateMultiChartStrokeSizes(baseChartWidth);
  const { strokeWidth, dotRadius } = strokeSizes;
  
  const innerWidth = baseChartWidth - margin.left - margin.right;
  const innerHeight = baseChartHeight - margin.top - margin.bottom;
  
  // year ranges
  const pgYearRange = [d3.min(pg, d => d.yearName), d3.max(pg, d => d.yearName)];
  const ubaYearRange = [d3.min(uba, d => d.yearName), d3.max(uba, d => d.yearName)];
  const pugYearRange = [d3.min(pug, d => d.yearName), d3.max(pug, d => d.yearName)];
  
  // helper to create standard line chart
  function createLineChart({
    data, xField, yField, xLabel, yLabel, title, yFormat, tooltipFormat,
    xScale: customXScale, yScale: customYScale
  }) {
    const svg = d3.create("svg")
      .attr("viewBox", `0 0 ${baseChartWidth} ${baseChartHeight}`)
      .attr("preserveAspectRatio", "xMidYMid meet")
      .style("width", "100%")
      .style("height", "auto");
    
    const g = svg.append("g")
      .attr("transform", `translate(${margin.left},${margin.top})`);
    
    const xScale = customXScale || d3.scaleLinear()
      .domain(d3.extent(data, d => d[xField]))
      .range([0, innerWidth]);
    
    const yScale = customYScale || d3.scaleLinear()
      .domain([0, d3.max(data, d => d[yField]) * 1.1])
      .range([innerHeight, 0]);
    
    // y-axis
    const yTicks = PlotHelpers.calculateYTicks(innerHeight);
    const yAxis = g.append("g");
    yAxis.call(d3.axisLeft(yScale).ticks(yTicks).tickFormat(yFormat).tickSizeOuter(0).tickSizeInner(-innerWidth));
    yAxis.select(".domain").remove();
    yAxis.selectAll(".tick line").attr("stroke", "#f0f0f0");
    yAxis.selectAll(".tick text").style("font-size", `${fontSizes.tickLabel}px`);
    
    // x-axis
    const xAxis = g.append("g").attr("transform", `translate(0,${innerHeight})`);
    xAxis.call(d3.axisBottom(xScale).tickFormat(d3.format("d")).tickSizeOuter(0));
    xAxis.select(".domain").attr("stroke", "currentColor");
    
    const yearRange = d3.max(data, d => d[xField]) - d3.min(data, d => d[xField]);
    const tickSpacing = innerWidth / yearRange;
    const tickInterval = tickSpacing < 25 ? 5 : tickSpacing < 40 ? 3 : tickSpacing < 55 ? 2 : 1;
    const minYear = d3.min(data, d => d[xField]);
    const maxYear = d3.max(data, d => d[xField]);
    
    xAxis.selectAll(".tick text").each(function(d) {
      const year = parseInt(d);
      if ((year - minYear) % tickInterval !== 0 && year !== maxYear) {
        d3.select(this).remove();
      } else {
        d3.select(this).style("font-size", `${fontSizes.tickLabel}px`);
      }
    });
    
    // line
    const line = d3.line()
      .defined(d => d[yField] != null && !isNaN(d[yField]))
      .x(d => xScale(d[xField]))
      .y(d => yScale(d[yField]));
    
    g.append("path")
      .datum(data)
      .attr("fill", "none")
      .attr("stroke", "black")
      .attr("stroke-width", strokeWidth)
      .attr("d", line);
    
    // dots
    g.selectAll(".dot")
      .data(data.filter(d => d[yField] != null))
      .enter().append("circle")
      .attr("cx", d => xScale(d[xField]))
      .attr("cy", d => yScale(d[yField]))
      .attr("r", dotRadius)
      .attr("fill", "black")
      .on("mouseover", function(event, d) {
        d3.selectAll(".d3-tooltip").remove();
        const tooltip = d3.select("body").append("div").attr("class", "d3-tooltip");
        const left = Math.min(event.pageX + 10, window.innerWidth - 210);
        tooltip.html(tooltipFormat(d))
          .style("left", left + "px")
          .style("top", (event.pageY - 35) + "px")
          .style("opacity", 1);
      })
      .on("mouseout", () => d3.selectAll(".d3-tooltip").remove());
    
    // title
    svg.append("text")
      .attr("x", margin.left)
      .attr("y", 18)
      .style("font-size", `${fontSizes.title}px`)
      .style("font-weight", "500")
      .text(title);
    
    // y label
    svg.append("text")
      .attr("transform", "rotate(-90)")
      .attr("y", 12)
      .attr("x", -(margin.top + innerHeight/2))
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(yLabel);
    
    // x label
    svg.append("text")
      .attr("x", margin.left + innerWidth/2)
      .attr("y", baseChartHeight - 10)
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(xLabel);
    
    return svg.node();
  }
  
  // create all charts
  const charts = [];
  
  charts.push(createLineChart({
    data: pg, xField: 'yearName', yField: 'population',
    xLabel: 'Year', yLabel: 'Population',
    title: `Population Growth, ${pgYearRange[0]}-${pgYearRange[1]}`,
    yFormat: d => PlotHelpers.formatPopulation(d),
    tooltipFormat: d => `<div>Year: ${d.yearName}</div><div>Population: ${d.population.toLocaleString()}</div>`
  }));
  
  charts.push(createLineChart({
    data: pg, xField: 'yearName', yField: 'populationGrowthPercentage',
    xLabel: 'Year', yLabel: 'Growth %',
    title: `Population Growth %, ${pgYearRange[0]}-${pgYearRange[1]}`,
    yFormat: d => d,
    tooltipFormat: d => `<div>Year: ${d.yearName}</div><div>Growth: ${d.populationGrowthPercentage.toFixed(2)}%</div>`
  }));
  
  const ubaXScale = d3.scaleLinear().domain([1, uba.length]).range([0, innerWidth]);
  const ubaWithYear = uba.map((d, i) => ({ ...d, year: i + 1 }));
  const chart3 = createLineChart({
    data: ubaWithYear, xField: 'year', yField: 'uba',
    xLabel: 'Year', yLabel: 'Built-up Area (sq km)',
    title: `Urban Built-up Area, ${ubaYearRange[0]}-${ubaYearRange[1]}`,
    yFormat: d3.format("~s"), xScale: ubaXScale,
    tooltipFormat: d => `<div>Year: ${d.yearName}</div><div>Area: ${d.uba.toLocaleString()} sq km</div>`
  });
  d3.select(chart3).selectAll("g:last-of-type .tick text").text(function() {
    const val = parseFloat(d3.select(this).text());
    const idx = Math.round(val) - 1;
    return idx >= 0 && idx < uba.length ? uba[idx].yearName : "";
  });
  charts.push(chart3);
  
  charts.push(createLineChart({
    data: uba, xField: 'yearName', yField: 'ubaGrowthPercentage',
    xLabel: 'Year', yLabel: 'Growth %',
    title: `Built-up Area Growth %, ${ubaYearRange[0]}-${ubaYearRange[1]}`,
    yFormat: d => d,
    tooltipFormat: d => `<div>Year: ${d.yearName}</div><div>Growth: ${d.ubaGrowthPercentage.toFixed(2)}%</div>`
  }));
  
  charts.push(createLineChart({
    data: pug, xField: 'yearName', yField: 'density',
    xLabel: 'Year', yLabel: 'Density (people/sq km)',
    title: `Density, ${pugYearRange[0]}-${pugYearRange[1]}`,
    yFormat: d3.format("~s"),
    tooltipFormat: d => `<div>Year: ${d.yearName}</div><div>Density: ${d.density.toFixed(0)}</div>`
  }));
  
  // chart (6)
  const svg6 = d3.create("svg")
    .attr("viewBox", `0 0 ${baseChartWidth} ${baseChartHeight}`)
    .attr("preserveAspectRatio", "xMidYMid meet")
    .style("width", "100%")
    .style("height", "auto");
  
  const g6 = svg6.append("g").attr("transform", `translate(${margin.left},${margin.top})`);
  
  const xScale6 = d3.scaleLinear().domain([0, 2]).range([0, innerWidth]);
  const yScale6 = d3.scaleLinear().domain(d3.extent(pug, d => d.yearName)).range([innerHeight, 0]);
  
  const yAxis6 = g6.append("g");
  yAxis6.call(d3.axisLeft(yScale6).ticks(PlotHelpers.calculateYTicks(innerHeight)).tickFormat(d3.format("d")).tickSizeOuter(0).tickSizeInner(-innerWidth));
  yAxis6.select(".domain").attr("stroke", "currentColor");
  yAxis6.selectAll(".tick line").attr("stroke", "#f0f0f0");
  yAxis6.selectAll(".tick text").style("font-size", `${fontSizes.tickLabel}px`);
  
  const xAxis6 = g6.append("g").attr("transform", `translate(0,${innerHeight})`);
  xAxis6.call(d3.axisBottom(xScale6).ticks(2).tickSizeOuter(0).tickSizeInner(-innerHeight));
  xAxis6.select(".domain").attr("stroke", "currentColor");
  xAxis6.selectAll(".tick line").attr("stroke", "#f0f0f0");
  xAxis6.selectAll(".tick text").style("font-size", `${fontSizes.tickLabel}px`);
  
  g6.append("line")
    .attr("x1", xScale6(1)).attr("x2", xScale6(1))
    .attr("y1", 0).attr("y2", innerHeight)
    .attr("stroke", "#999").attr("stroke-width", 1.5).attr("stroke-dasharray", "4,4");
  
  const line6 = d3.line()
    .defined(d => d.populationUrbanGrowthRatio != null)
    .x(d => xScale6(d.populationUrbanGrowthRatio))
    .y(d => yScale6(d.yearName));
  
  g6.append("path")
    .datum(pug)
    .attr("fill", "none")
    .attr("stroke", "black")
    .attr("stroke-width", strokeWidth)
    .attr("d", line6);
  
  g6.selectAll(".dot")
    .data(pug.filter(d => d.populationUrbanGrowthRatio != null))
    .enter().append("circle")
    .attr("cx", d => xScale6(d.populationUrbanGrowthRatio))
    .attr("cy", d => yScale6(d.yearName))
    .attr("r", dotRadius)
    .attr("fill", "black");
  
  const annotY = margin.top + yScale6(d3.min(pug, d => d.yearName)) - 5;
  const annotSize = Math.max(6, fontSizes.annotation * 0.8);
  
  svg6.append("text").attr("x", margin.left + xScale6(1)).attr("y", annotY + 40)
    .attr("text-anchor", "middle").attr("fill", "#555")
    .style("font-size", `${annotSize}px`).style("font-weight", "600").text("Balanced");
  
  svg6.append("text").attr("x", margin.left + xScale6(0.5)).attr("y", annotY + 35)
    .attr("text-anchor", "middle").attr("fill", "#555")
    .style("font-size", `${annotSize}px`).style("font-weight", "600").text("Potential");
  svg6.append("text").attr("x", margin.left + xScale6(0.5)).attr("y", annotY + 45)
    .attr("text-anchor", "middle").attr("fill", "#555")
    .style("font-size", `${annotSize}px`).style("font-weight", "600").text("Sprawl");
  
  svg6.append("text").attr("x", margin.left + xScale6(1.5)).attr("y", annotY + 35)
    .attr("text-anchor", "middle").attr("fill", "#555")
    .style("font-size", `${annotSize}px`).style("font-weight", "600").text("Potential");
  svg6.append("text").attr("x", margin.left + xScale6(1.5)).attr("y", annotY + 45)
    .attr("text-anchor", "middle").attr("fill", "#555")
    .style("font-size", `${annotSize}px`).style("font-weight", "600").text("Densification");
  
  svg6.append("text").attr("x", margin.left).attr("y", 18)
    .style("font-size", `${fontSizes.title}px`).style("font-weight", "500")
    .text(`Pop-Urban Growth Ratio, ${pugYearRange[0]}-${pugYearRange[1]}`);
  
  svg6.append("text").attr("transform", "rotate(-90)").attr("y", 12)
    .attr("x", -(margin.top + innerHeight/2)).attr("text-anchor", "middle")
    .style("font-size", `${fontSizes.axisLabel}px`).text("Year");
  
  charts.push(svg6.node());
  
  // container
  const container = document.createElement('div');
  container.style.cssText = `
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: ${gridGap}px;
    width: 100%;
  `;
  
  charts.forEach(chart => {
    const div = document.createElement('div');
    div.style.cssText = 'width: 100%; min-width: 0;';
    div.appendChild(chart);
    container.appendChild(div);
  });
  
  return container;
}


// ------------------------------------------------------------
// plot_pv_area
// ------------------------------------------------------------
function plot_pv_area(pv_area, {
  cityName = globalCity, 
  countryName = globalCountry,
  width,
  height
} = {}) {
  
  // ========================================
  // DATA PREPARATION
  // ========================================
  const sortedData = pv_area.slice().sort((a, b) => 
    PlotHelpers.parsePvAreaRange(a.bin) - PlotHelpers.parsePvAreaRange(b.bin)
  );

  // color mapping for condition levels
  const pvAreaColorMap = {
    "Less than Favorable": "#FF9800",
    "Favorable": "#FFC107",
    "Excellent": "#4CAF50"
  };
  const defaultColor = "#999999"; // (fallback gray if no color map match)

  // map from bin values to condition names
  const binToConditionMap = {
    "<3.5": "Less than Favorable",
    "3.5-4.5": "Favorable", 
    ">4.5": "Excellent"
  };
  
  const allPvAreaBins = sortedData.map(d => d.bin);
  
  // complete data with gray bars for visual completeness
  const completeData = allPvAreaBins.map(bin => {
    const existing = sortedData.find(d => d.bin === bin);
    return existing || { bin, count: 0, percentage: 0 };
  });

  // ========================================
  // STYLING CALCULATIONS
  // ========================================
  // (use helper functions from plot-helpers.js for all styling calculations)
  const fontSizes = PlotHelpers.calculateFontSizes(width, height);
  const lineHeights = PlotHelpers.calculateLineHeights(fontSizes);
  
  // text content
  const titleText = "Photovoltaic Power Potential Yield";
  const titleLocation = countryName ? `${cityName}, ${countryName}` : cityName;
  const xAxisLabelText = "Power Potential of a Theoretical 1 kWp PV System (kWh)";
  const yAxisLabelText = "Percentage of Area (%)";
  const captionText = "Data: Solargis/World Bank, Global Solar Atlas 2 | Condition Classification: World Bank";
  
  // text wrapping
  const titleLines = PlotHelpers.wrapText(titleText, width - 40, `${fontSizes.title}px system-ui`);
  const subtitleLines = PlotHelpers.wrapText(titleLocation, width - 40, `${fontSizes.subtitle}px system-ui`);
  const xAxisLabelLines = PlotHelpers.wrapText(xAxisLabelText, width * 0.8, `${fontSizes.axisLabel}px system-ui`);
  const yAxisLabelLines = PlotHelpers.wrapText(yAxisLabelText, height * 0.6, `${fontSizes.axisLabel}px system-ui`);
  const captionLines = PlotHelpers.wrapText(captionText, width - 40, `${fontSizes.caption}px system-ui`);

  // calculate text dimensions for margins
  const titleHeight = titleLines.length * lineHeights.title;
  const subtitleHeight = subtitleLines.length * lineHeights.subtitle;
  const xAxisLabelHeight = xAxisLabelLines.length * lineHeights.axisLabel;
  const captionHeight = captionLines.length * lineHeights.caption;
  const yAxisLabelWidth = yAxisLabelLines.length * lineHeights.axisLabel;

  // calculate margins using helper
  const margin = PlotHelpers.calculateMargins(width, height, {
    titleHeight,
    subtitleHeight,
    xAxisLabelHeight,
    captionHeight,
    yAxisLabelWidth
  });
  
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  
  // ========================================
  // SCALES
  // ========================================
  const xScale = d3.scaleBand()
    .domain(completeData.map(d => d.bin))
    .range([0, innerWidth])
    .padding(0.1);
    
  const yScale = d3.scaleLinear()
    .domain([0, 100])
    .range([innerHeight, 0]);

  // ========================================
  // SVG CREATION
  // ========================================
  const svg = d3.create("svg")
    .attr("viewBox", `0 0 ${width} ${height}`)
    .attr("preserveAspectRatio", "xMidYMid meet")
    .style("width", "100%")
    .style("height", "auto")
    .style("max-width", `${width}px`);

  const g = svg.append("g")
    .attr("transform", `translate(${margin.left},${margin.top})`);
  
  // ========================================
  // Y-AXIS
  // ========================================
  const yTicks = PlotHelpers.calculateYTicks(innerHeight);
  const yAxisGroup = g.append("g").attr("class", "y-axis");
  const yAxisCall = d3.axisLeft(yScale)
    .ticks(yTicks)
    .tickSizeOuter(0)
    .tickSizeInner(-innerWidth)
    .tickFormat(d3.format("~s"));

  yAxisGroup.call(yAxisCall);
  yAxisGroup.selectAll(".tick text")
    .style("font-size", `${fontSizes.yAxisTick}px`);
    
  // ========================================
  // BARS
  // ========================================
  // gray background bars
  g.selectAll(".background-bar")
    .data(completeData)
    .enter().append("rect")
    .attr("class", "background-bar")
    .attr("x", d => xScale(d.bin))
    .attr("width", xScale.bandwidth())
    .attr("y", 0)
    .attr("height", innerHeight);
    
  // data bars with smart tooltips
  g.selectAll(".data-bar")
    .data(completeData.filter(d => d.percentage > 0))
    .enter().append("rect")
    .attr("class", "data-bar")
    .attr("x", d => xScale(d.bin))
    .attr("width", xScale.bandwidth())
    .attr("y", d => yScale(d.percentage))
    .attr("height", d => innerHeight - yScale(d.percentage))
    .attr("fill", d => pvAreaColorMap[d.condition] || defaultColor)
    .attr("fill-opacity", 0.4)
    .attr("stroke", d => d3.color(pvAreaColorMap[d.condition] || defaultColor).darker(0.3))
    .attr("stroke-width", 1)
    .style("cursor", "default")
    .on("mouseover", function(event, d) {
      d3.selectAll(".d3-tooltip").remove();

      const tooltip = d3.select("body").append("div")
        .attr("class", "d3-tooltip")
        .style("opacity", 0);
        
      const html = `<div>Condition: ${d.condition}</div><div>Percentage of Area: ${d.percentage.toFixed(1)}%</div>`;
      
      // calculate position to avoid bleeding off screen
      const tooltipWidth = 220;
      const windowWidth = window.innerWidth;
      const mouseX = event.pageX;
      
      let leftPos = mouseX + 10;
      if (leftPos + tooltipWidth > windowWidth) {
        leftPos = mouseX - tooltipWidth - 10;
      }
      
      tooltip
        .html(html)
        .style("left", leftPos + "px")
        .style("top", (event.pageY - 35) + "px")
        .transition()
        .duration(200)
        .style("opacity", 1);
    })
    .on("mousemove", function(event) {
      const tooltip = d3.select(".d3-tooltip");
      if (!tooltip.empty()) {
        const tooltipWidth = 220;
        const windowWidth = window.innerWidth;
        const mouseX = event.pageX;
        
        let leftPos = mouseX + 10;
        if (leftPos + tooltipWidth > windowWidth) {
          leftPos = mouseX - tooltipWidth - 10;
        }
        
        tooltip
          .style("left", leftPos + "px")
          .style("top", (event.pageY - 35) + "px");
      }
    })
    .on("mouseout", function() {
      d3.select(".d3-tooltip")
        .transition()
        .duration(200)
        .style("opacity", 0)
        .remove();
    });

  // ========================================
  // BAR PERCENTAGE LABELS
  // ========================================
  g.selectAll(".bar-label")
    .data(completeData)
    .enter().append("text")
    .attr("class", "plot-bar-label")
    .attr("x", d => xScale(d.bin) + xScale.bandwidth()/2)
    .attr("y", d => d.percentage > 0 ? yScale(d.percentage) - 8 : innerHeight/2)
    .attr("text-anchor", "middle")
    .attr("fill", d => d.percentage > 0 ? "black" : "#6c757d")
    .style("font-size", `${fontSizes.barLabel}px`)
    .attr("font-style", d => d.percentage > 0 ? "normal" : "italic")
    .text(d => d.percentage > 0 ? `${d.percentage.toFixed(1)}%` : "")
    .style("display", d => d.percentage > 2 || d.percentage === 0 ? "block" : "none");

  // ========================================
  // X-AXIS
  // ========================================
  const xAxisGroup = g.append("g")
    .attr("class", "x-axis")
    .attr("transform", `translate(0,${innerHeight})`);
    
  xAxisGroup.call(d3.axisBottom(xScale)
    .tickSizeOuter(0)
    .tickSizeInner(0));
 
  // x-axis tick labels with wrapping
  const barWidth = xScale.bandwidth();
  const xAxisTickSize = PlotHelpers.calculateXAxisTickSize(barWidth);
  
  xAxisGroup.selectAll(".tick text")
    .each(function(d) {
      const text = d3.select(this);
      const labelText = text.text();
      
      text.style("font-size", `${xAxisTickSize}px`);
      
      const lines = PlotHelpers.wrapBarLabel(labelText, barWidth, `${xAxisTickSize}px system-ui`);
      text.text(null);
      
      lines.forEach((line, i) => {
        text.append("tspan")
          .attr("x", 0)
          .attr("dy", i === 0 ? "1.2em" : "1.1em")
          .text(line);
      });
    });
    
  // ========================================
  // TITLE
  // ========================================
  const heightScale = height / PlotHelpers.PLOT_BASE.HEIGHT;
  const titleY = PlotHelpers.getTitleY(height, heightScale);
  
  titleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-title")
      .attr("x", 20)
      .attr("y", titleY + (i * lineHeights.title))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.title}px`)
      .text(line);
  });
    
  // ========================================
  // SUBTITLE
  // ========================================
  const subtitleY = PlotHelpers.getSubtitleY(titleY, titleLines.length, lineHeights.title, heightScale);
  
  subtitleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-subtitle")
      .attr("x", 20)
      .attr("y", subtitleY + (i * lineHeights.subtitle))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.subtitle}px`)
      .text(line);
  });
    
  // ========================================
  // Y-AXIS LABEL
  // ========================================
  const widthScale = width / PlotHelpers.PLOT_BASE.WIDTH;
  const yAxisLabelX = -(margin.top + innerHeight/2);
  const yAxisLabelY = PlotHelpers.getYAxisLabelY(widthScale);
  
  yAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("transform", "rotate(-90)")
      .attr("y", yAxisLabelY + (i * lineHeights.axisLabel))
      .attr("x", yAxisLabelX)
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // X-AXIS LABEL
  // ========================================
  const xAxisLabelX = margin.left + innerWidth/2;
  const xAxisLabelY = PlotHelpers.getXAxisLabelY(height, captionHeight, heightScale);
  
  xAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("x", xAxisLabelX)
      .attr("y", xAxisLabelY - ((xAxisLabelLines.length - 1 - i) * lineHeights.axisLabel))
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // CAPTION
  // ========================================
  const captionY = PlotHelpers.getCaptionY(height, heightScale);
  
  captionLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-caption")
      .attr("x", 20)
      .attr("y", captionY - ((captionLines.length - 1 - i) * lineHeights.caption))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.caption}px`)
      .text(line);
  });
  
  return svg.node();
}


// ------------------------------------------------------------
// plot_pv_alt
// ------------------------------------------------------------
function plot_pv_alt(pv, {
  cityName = globalCity, 
  countryName = globalCountry,
  width,
  height
} = {}) {
  
  // ========================================
  // DATA PREPARATION
  // ========================================
  // normalize columns: solar_monthly_stats has month/max/min/mean; this chart reads
  // monthName/maxPv. Map them here (team fix)
  const _months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  pv = pv.map(d => ({ month: +d.month,
                      monthName: d.monthName ?? _months[(+d.month || 0) - 1],
                      maxPv: +(d.maxPv ?? d.max ?? d.mean ?? 0) }));
  
  // ========================================
  // STYLING CALCULATIONS
  // ========================================
  // (use helper functions from plot-helpers.js for all styling calculations)
  const fontSizes = PlotHelpers.calculateFontSizes(width, height);
  const lineHeights = PlotHelpers.calculateLineHeights(fontSizes);
  
  // text content
  const titleText = "Seasonal Availability of Solar Energy, January - December";
  const titleLocation = countryName ? `${cityName}, ${countryName}` : cityName;
  const xAxisLabelText = "Month";
  const yAxisLabelText = "Daily PV energy yield (kWh/kWp)";
  const captionText = ""; // (empty for this plot)
  
  // text wrapping
  const titleLines = PlotHelpers.wrapText(titleText, width - 40, `${fontSizes.title}px system-ui`);
  const subtitleLines = PlotHelpers.wrapText(titleLocation, width - 40, `${fontSizes.subtitle}px system-ui`);
  const xAxisLabelLines = PlotHelpers.wrapText(xAxisLabelText, width * 0.8, `${fontSizes.axisLabel}px system-ui`);
  const yAxisLabelLines = PlotHelpers.wrapText(yAxisLabelText, height * 0.6, `${fontSizes.axisLabel}px system-ui`);
  const captionLines = PlotHelpers.wrapText(captionText, width - 40, `${fontSizes.caption}px system-ui`);

  // calculate text dimensions for margins
  const titleHeight = titleLines.length * lineHeights.title;
  const subtitleHeight = subtitleLines.length * lineHeights.subtitle;
  const xAxisLabelHeight = xAxisLabelLines.length * lineHeights.axisLabel;
  const captionHeight = captionLines.length * lineHeights.caption;
  const yAxisLabelWidth = yAxisLabelLines.length * lineHeights.axisLabel;

  // calculate margins using helper
  const margin = PlotHelpers.calculateMargins(width, height, {
    titleHeight,
    subtitleHeight,
    xAxisLabelHeight,
    captionHeight,
    yAxisLabelWidth
  });
  
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  
  // ========================================
  // SCALES
  // ========================================
  const xScale = d3.scaleBand()
    .domain(pv.map(d => d.monthName))
    .range([0, innerWidth])
    .padding(0.1);
    
  const yScale = d3.scaleLinear()
    .domain([0, Math.max(...pv.map(d => d.maxPv)) * 1.1])
    .range([innerHeight, 0]);

  // ========================================
  // SVG CREATION
  // ========================================
  const svg = d3.create("svg")
    .attr("viewBox", `0 0 ${width} ${height}`)
    .attr("preserveAspectRatio", "xMidYMid meet")
    .style("width", "100%")
    .style("height", "auto")
    .style("max-width", `${width}px`);

  const g = svg.append("g")
    .attr("transform", `translate(${margin.left},${margin.top})`)
    .attr("class", "pv-alt-plot"); // Special class for this plot
  
  // ========================================
  // COLORED BACKGROUND ZONES
  // ========================================
  // "excellent" conditions (above 4.5) - green
  g.append("rect")
    .attr("x", 0)
    .attr("y", 0)
    .attr("width", innerWidth)
    .attr("height", yScale(4.5))
    .attr("fill", "#4CAF50")
    .attr("fill-opacity", 0.40);
  
  // "favorable" conditions (3.5 to 4.5) - yellow
  g.append("rect")
    .attr("x", 0)
    .attr("y", yScale(4.5))
    .attr("width", innerWidth)
    .attr("height", yScale(3.5) - yScale(4.5))
    .attr("fill", "#FFC107")
    .attr("fill-opacity", 0.40);
  
  // "less than favorable" (below 3.5) - orange
  g.append("rect")
    .attr("x", 0)
    .attr("y", yScale(3.5))
    .attr("width", innerWidth)
    .attr("height", innerHeight - yScale(3.5))
    .attr("fill", "#FF9800")
    .attr("fill-opacity", 0.40);
  
  // ========================================
  // Y-AXIS
  // ========================================
  const yTicks = PlotHelpers.calculateYTicks(innerHeight);
  const yAxisGroup = g.append("g").attr("class", "y-axis");
  const yAxisCall = d3.axisLeft(yScale)
    .ticks(yTicks)
    .tickSizeOuter(0)
    .tickSizeInner(0) // (no inner tick lines (no grid))
    .tickFormat(d3.format("~s"));

  yAxisGroup.call(yAxisCall);
  yAxisGroup.selectAll(".tick text")
    .style("font-size", `${fontSizes.yAxisTick}px`);
  
  // ========================================
  // X-AXIS
  // ========================================
  const xAxisGroup = g.append("g")
    .attr("class", "x-axis")
    .attr("transform", `translate(0,${innerHeight})`);
    
  xAxisGroup.call(d3.axisBottom(xScale)
    .tickSizeOuter(0)
    .tickSizeInner(0)); // (no inner tick lines (no grid))

  // calculate how many ticks to show based on available width
  const barWidth = xScale.bandwidth();
  const availableSpacePerTick = barWidth + (xScale.step() - barWidth);
  
  // determine tick interval (show every nth month)
  let tickInterval;
  if (availableSpacePerTick < 60) {
    tickInterval = 3; // (show every 3rd month (Jan, Apr, Jul, Oct)
  } else if (availableSpacePerTick < 80) {
    tickInterval = 2; // (show every 2nd month)
  } else {
    tickInterval = 1; // (show all months)
  }

  // filter and style tick labels
  xAxisGroup.selectAll(".tick text")
    .each(function(d, i) {
      const text = d3.select(this);
      
      // (hide ticks that don't match the interval)
      if (i % tickInterval !== 0) {
        text.remove();
        return;
      }
      
      const labelText = text.text();
      text.style("font-size", `${fontSizes.xAxisTick}px`);
      
      const lines = PlotHelpers.wrapBarLabel(labelText, barWidth * tickInterval, `${fontSizes.xAxisTick}px system-ui`);
      text.text(null);
      
      lines.forEach((line, j) => {
        text.append("tspan")
          .attr("x", 0)
          .attr("dy", j === 0 ? "1.2em" : "1.1em")
          .text(line);
      });
    });
  
  // ========================================
  // ZONE LABELS
  // ========================================
  // "excellent" label
  g.append("text")
    .attr("class", "plot-annotation-text")
    .attr("x", innerWidth - 10)
    .attr("y", yScale(4.75))
    .attr("text-anchor", "end")
    .attr("fill", "#4CAF50")
    .style("font-size", `${fontSizes.annotation}px`)
    .style("font-weight", "bold")
    .text("Excellent");
  
  // "favorable" label
  g.append("text")
    .attr("class", "plot-annotation-text")
    .attr("x", innerWidth - 10)
    .attr("y", yScale(4.0))
    .attr("text-anchor", "end")
    .attr("fill", "#B8860B") // (darker yellow)
    .style("font-size", `${fontSizes.annotation}px`)
    .style("font-weight", "bold")
    .text("Favorable");
  
  // "less than favorable" label
  g.append("text")
    .attr("class", "plot-annotation-text")
    .attr("x", innerWidth - 10)
    .attr("y", yScale(1.75))
    .attr("text-anchor", "end")
    .attr("fill", "#FF9800")
    .style("font-size", `${fontSizes.annotation}px`)
    .style("font-weight", "bold")
    .text("Less than Favorable");
  
  // ========================================
  // LINE
  // ========================================
  const line = d3.line()
    .x(d => xScale(d.monthName) + xScale.bandwidth() / 2)
    .y(d => yScale(d.maxPv));
    
  g.append("path")
    .datum(pv)
    .attr("fill", "none")
    .attr("stroke", "black")
    .attr("stroke-width", Math.max(1.5, Math.min(3, width / 400)))
    .attr("d", line);
  
  // ========================================
  // DOTS
  // ========================================
  g.selectAll(".dot")
    .data(pv)
    .enter().append("circle")
    .attr("class", "dot")
    .attr("cx", d => xScale(d.monthName) + xScale.bandwidth() / 2)
    .attr("cy", d => yScale(d.maxPv))
    .attr("r", Math.max(2, Math.min(3, width / 200)))
    .attr("fill", "black")
    .style("cursor", "default")
    .on("mouseover", function(event, d) {
      d3.selectAll(".d3-tooltip").remove();

      const tooltip = d3.select("body").append("div")
        .attr("class", "d3-tooltip")
        .style("opacity", 0);
      
      // determine condition
      let condition;
      if (d.maxPv >= 4.5) condition = "Excellent";
      else if (d.maxPv >= 3.5) condition = "Favorable";
      else condition = "Less than Favorable";
        
      const html = `<div>Month: ${d.monthName}</div><div>Daily PV energy yield: ${(+d.maxPv).toFixed(3)} kWh/kWp</div><div>Conditions: ${condition}</div>`;
      
      const tooltipWidth = 220;
      const windowWidth = window.innerWidth;
      const mouseX = event.pageX;
      
      let leftPos = mouseX + 10;
      if (leftPos + tooltipWidth > windowWidth) {
        leftPos = mouseX - tooltipWidth - 10;
      }
      
      tooltip
        .html(html)
        .style("left", leftPos + "px")
        .style("top", (event.pageY - 35) + "px")
        .transition()
        .duration(200)
        .style("opacity", 1);
    })
    .on("mousemove", function(event) {
      const tooltip = d3.select(".d3-tooltip");
      if (!tooltip.empty()) {
        const tooltipWidth = 220;
        const windowWidth = window.innerWidth;
        const mouseX = event.pageX;
        
        let leftPos = mouseX + 10;
        if (leftPos + tooltipWidth > windowWidth) {
          leftPos = mouseX - tooltipWidth - 10;
        }
        
        tooltip
          .style("left", leftPos + "px")
          .style("top", (event.pageY - 35) + "px");
      }
    })
    .on("mouseout", function() {
      d3.select(".d3-tooltip")
        .transition()
        .duration(200)
        .style("opacity", 0)
        .remove();
    });
  
  // ========================================
  // TITLE
  // ========================================
  const heightScale = height / PlotHelpers.PLOT_BASE.HEIGHT;
  const titleY = PlotHelpers.getTitleY(height, heightScale);
  
  titleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-title")
      .attr("x", 20)
      .attr("y", titleY + (i * lineHeights.title))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.title}px`)
      .text(line);
  });
    
  // ========================================
  // SUBTITLE
  // ========================================
  const subtitleY = PlotHelpers.getSubtitleY(titleY, titleLines.length, lineHeights.title, heightScale);
  
  subtitleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-subtitle")
      .attr("x", 20)
      .attr("y", subtitleY + (i * lineHeights.subtitle))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.subtitle}px`)
      .text(line);
  });
    
  // ========================================
  // Y-AXIS LABEL
  // ========================================
  const widthScale = width / PlotHelpers.PLOT_BASE.WIDTH;
  const yAxisLabelX = -(margin.top + innerHeight/2);
  const yAxisLabelY = PlotHelpers.getYAxisLabelY(widthScale);
  
  yAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("transform", "rotate(-90)")
      .attr("y", yAxisLabelY + (i * lineHeights.axisLabel))
      .attr("x", yAxisLabelX)
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // X-AXIS LABEL
  // ========================================
  const xAxisLabelX = margin.left + innerWidth/2;
  const xAxisLabelY = PlotHelpers.getXAxisLabelY(height, captionHeight, heightScale);
  
  xAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("x", xAxisLabelX)
      .attr("y", xAxisLabelY - ((xAxisLabelLines.length - 1 - i) * lineHeights.axisLabel))
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // CAPTION
  // ========================================
  // (empty for this plot)
  if (captionText) {
    const captionY = PlotHelpers.getCaptionY(height, heightScale);
    
    captionLines.forEach((line, i) => {
      svg.append("text")
        .attr("class", "plot-caption")
        .attr("x", 20)
        .attr("y", captionY - ((captionLines.length - 1 - i) * lineHeights.caption))
        .attr("text-anchor", "start")
        .style("font-size", `${fontSizes.caption}px`)
        .text(line);
    });
  }
  
  return svg.node();
}


// ------------------------------------------------------------
// plot_pv_d
// ------------------------------------------------------------
function plot_pv_d(pv, {
  cityName = globalCity,
  countryName = globalCountry,
  width,
  height,
  showPercentages = true
} = {}) {
  
  // ========================================
  // DATA PREPARATION
  // ========================================
  // count occurrences of each condition level
  const conditionCounts = d3.rollup(pv, v => v.length, d => d.condition);
  
  // define all possible condition levels in order
  const allConditionLevels = [
    "Excellent", "Favorable", "Less than Favorable"
  ];
  
  // condition mapping
  const conditionMapping = {
    "Excellent": "Excellent",
    "Favorable": "Favorable",
    "Less than Favorable": "Less than Favorable",
  };
  
  // data array with counts and percentages
  const distributionData = allConditionLevels.map(level => ({
    condition: level,
    count: conditionCounts.get(conditionMapping[level]) || 0,
    percentage: ((conditionCounts.get(conditionMapping[level]) || 0) / pv.length * 100)
  }));
  
  // color mapping for condition levels
  const colorMap = {
    "Excellent": "#4CAF50",
    "Favorable": "#FFC107",
    "Less than Favorable": "#8B0000",
  };
  
  // ========================================
  // STYLING CALCULATIONS
  // ========================================
  // (use helper functions from plot-helpers.js for all styling calculations)
  const fontSizes = PlotHelpers.calculateFontSizes(width, height);
  const lineHeights = PlotHelpers.calculateLineHeights(fontSizes);
  const dynamicScale = PlotHelpers.calculateDynamicScale(width);
  const showValueLabels = PlotHelpers.shouldShowBarLabels(width);
  const labelFontSize = PlotHelpers.calculateBarChartLabelFontSize(dynamicScale);
  
  // text content
  const titleText = "Photovoltaic Potential Condition Level Distribution";
  const titleLocation = countryName ? `${cityName}, ${countryName} (${pv.length}-month period)` : `${cityName} (${pv.length}-month period)`;
  const xAxisLabelText = "Month";
  const yAxisLabelText = "Condition";
  const captionText = "Data: Solargis/World Bank, Global Solar Atlas 2 | Condition Classification: World Bank";
  
  // text wrapping
  const titleLines = PlotHelpers.wrapText(titleText, width - 40, `${fontSizes.title}px system-ui`);
  const subtitleLines = PlotHelpers.wrapText(titleLocation, width - 40, `${fontSizes.subtitle}px system-ui`);
  const xAxisLabelLines = PlotHelpers.wrapText(xAxisLabelText, width * 0.8, `${fontSizes.axisLabel}px system-ui`);
  const yAxisLabelLines = PlotHelpers.wrapText(yAxisLabelText, height * 0.6, `${fontSizes.axisLabel}px system-ui`);
  const captionLines = PlotHelpers.wrapText(captionText, width - 40, `${fontSizes.caption}px system-ui`);

  // calculate text dimensions for margins
  const titleHeight = titleLines.length * lineHeights.title;
  const subtitleHeight = subtitleLines.length * lineHeights.subtitle;
  const xAxisLabelHeight = xAxisLabelLines.length * lineHeights.axisLabel;
  const captionHeight = captionLines.length * lineHeights.caption;
  const yAxisLabelWidth = yAxisLabelLines.length * lineHeights.axisLabel;

  // calculate margins using helpers
  const baseMargin = PlotHelpers.calculateMargins(width, height, {
    titleHeight,
    subtitleHeight,
    xAxisLabelHeight,
    captionHeight,
    yAxisLabelWidth
  });
  
  const margin = PlotHelpers.calculateBarChartMargins(baseMargin, dynamicScale, showValueLabels);
  
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  
  // ========================================
  // SCALES
  // ========================================
  // (note: use helper function from plot-helpers.js for consistency with other plots, even though fixed domain, i.e., always 12 months in a year)
  const domainMax = PlotHelpers.calculateTimePeriodDomain(pv, 'month');
  
  const xScale = d3.scaleLinear()
    .domain([0, domainMax])
    .range([0, innerWidth]);
  
  const yScale = d3.scaleBand()
    .domain(allConditionLevels)
    .range([0, innerHeight])
    .padding(0.2);

  // ========================================
  // SVG CREATION
  // ========================================
  const svg = d3.create("svg")
    .attr("viewBox", `0 0 ${width} ${height}`)
    .attr("preserveAspectRatio", "xMidYMid meet")
    .style("width", "100%")
    .style("height", "auto")
    .style("max-width", `${width}px`);

  const g = svg.append("g")
    .attr("transform", `translate(${margin.left},${margin.top})`);
  
  // ========================================
  // GRID LINES
  // ========================================
  const xAxisGrid = d3.axisBottom(xScale)
    .ticks(Math.max(4, Math.min(12, Math.floor(innerWidth / 80))))
    .tickSize(innerHeight)
    .tickFormat("");
  
  g.append("g")
    .attr("class", "grid")
    .call(xAxisGrid)
    .call(g => g.select(".domain").remove())
    .call(g => g.selectAll(".tick line")
      .attr("stroke", "#f0f0f0")
      .attr("stroke-opacity", 1)
      .attr("stroke-width", 1));
  
  // ========================================
  // BACKGROUND "DUMMY" BARS
  // ========================================
  g.selectAll(".dummy-bar")
    .data(distributionData)
    .enter().append("rect")
    .attr("class", "dummy-bar")
    .attr("x", 0)
    .attr("y", d => yScale(d.condition))
    .attr("width", xScale(domainMax))
    .attr("height", yScale.bandwidth())
    .attr("fill", "#f8f9fa")
    .attr("fill-opacity", 0.3)
    .attr("stroke", "#dee2e6")
    .attr("stroke-width", Math.max(0.5, 1 * dynamicScale));
  
  // ========================================
  // DATA BARS
  // ========================================
  g.selectAll(".data-bar")
    .data(distributionData.filter(d => d.count > 0))
    .enter().append("rect")
    .attr("class", "data-bar")
    .attr("x", 0)
    .attr("y", d => yScale(d.condition))
    .attr("width", d => xScale(d.count))
    .attr("height", yScale.bandwidth())
    .attr("fill", d => colorMap[d.condition])
    .attr("fill-opacity", 0.40)
    .attr("stroke", "white")
    .attr("stroke-opacity", 0.3)
    .attr("stroke-width", Math.max(0.5, 1 * dynamicScale));
  
  // ========================================
  // VALUE LABELS
  // ========================================
  // (only if wide enough)
  if (showValueLabels) {
    g.selectAll(".label")
      .data(distributionData)
      .enter().append("text")
      .attr("class", "label")
      .attr("x", xScale(domainMax) + 10)
      .attr("y", d => yScale(d.condition) + yScale.bandwidth() / 2)
      .attr("text-anchor", "start")
      .attr("dominant-baseline", "middle")
      .attr("fill", d => d.count > 0 ? "black" : "#6c757d")
      .attr("font-size", `${Math.max(9, Math.min(13, 11 * dynamicScale))}px`)
      .attr("font-family", "system-ui")
      .attr("font-style", d => d.count > 0 ? "normal" : "italic")
      .text(d => d.count > 0 ?
        (showPercentages ? `${d.count} months (${d.percentage.toFixed(1)}%)` : `${d.count} months`) :
        "0 months (0.0%)");
  }
  
  // ========================================
  // Y-AXIS
  // ========================================
  const yAxisGroup = g.append("g");
  yAxisGroup.call(d3.axisLeft(yScale)
    .tickSize(0)
    .tickPadding(10));
  yAxisGroup.select(".domain").remove();
  
  // calculate label box dimensions using helper
  const labelBox = PlotHelpers.calculateYAxisLabelBox(margin.left, yScale.bandwidth());
  
  // replace text with wrapped text using foreignObject
  yAxisGroup.selectAll(".tick text").remove();
  yAxisGroup.selectAll(".tick")
    .append("foreignObject")
    .attr("width", labelBox.width)
    .attr("height", labelBox.height)
    .attr("x", labelBox.x)
    .attr("y", labelBox.y)
    .append("xhtml:div")
    .style("width", labelBox.width + "px")
    .style("height", labelBox.height + "px")
    .style("display", "flex")
    .style("align-items", "center")
    .style("justify-content", "flex-end")
    .style("font-size", `${labelFontSize}px`)
    .style("font-family", "system-ui")
    .style("text-align", "right")
    .style("line-height", "1.1")
    .style("word-wrap", "break-word")
    .style("overflow-wrap", "break-word")
    .style("hyphens", "auto")
    .html(d => d);
  
  // ========================================
  // X-AXIS
  // ========================================
  const xAxisGroup = g.append("g")
    .attr("transform", `translate(0,${innerHeight})`);
  xAxisGroup.call(d3.axisBottom(xScale)
    .ticks(Math.max(4, Math.min(12, Math.floor(innerWidth / 80))))
    .tickSize(Math.max(3, 6 * dynamicScale))
    .tickSizeOuter(0));
  xAxisGroup.select(".domain").attr("stroke", "currentColor");
  xAxisGroup.selectAll(".tick text")
    .attr("font-size", `${labelFontSize}px`)
    .attr("font-family", "system-ui")
    .attr("dy", "0.5em");
  
  // ========================================
  // TITLE
  // ========================================
  const heightScale = height / PlotHelpers.PLOT_BASE.HEIGHT;
  const titleY = PlotHelpers.getTitleY(height, heightScale);
  
  titleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-title")
      .attr("x", 20)
      .attr("y", titleY + (i * lineHeights.title))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.title}px`)
      .text(line);
  });
    
  // ========================================
  // SUBTITLE
  // ========================================
  const subtitleY = PlotHelpers.getSubtitleY(titleY, titleLines.length, lineHeights.title, heightScale);
  
  subtitleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-subtitle")
      .attr("x", 20)
      .attr("y", subtitleY + (i * lineHeights.subtitle))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.subtitle}px`)
      .text(line);
  });
    
  // ========================================
  // Y-AXIS LABEL
  // ========================================
  const widthScale = width / PlotHelpers.PLOT_BASE.WIDTH;
  const yAxisLabelX = -(margin.top + innerHeight/2);
  const yAxisLabelY = PlotHelpers.getYAxisLabelY(widthScale);
  
  yAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("transform", "rotate(-90)")
      .attr("y", yAxisLabelY + (i * lineHeights.axisLabel))
      .attr("x", yAxisLabelX)
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // X-AXIS LABEL
  // ========================================
  const xAxisLabelX = margin.left + innerWidth/2;
  const xAxisLabelY = PlotHelpers.getXAxisLabelY(height, captionHeight, heightScale);
  
  xAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("x", xAxisLabelX)
      .attr("y", xAxisLabelY - ((xAxisLabelLines.length - 1 - i) * lineHeights.axisLabel))
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // CAPTION
  // ========================================
  const captionY = PlotHelpers.getCaptionY(height, heightScale);
  
  captionLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-caption")
      .attr("x", 20)
      .attr("y", captionY - ((captionLines.length - 1 - i) * lineHeights.caption))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.caption}px`)
      .text(line);
  });
  
  return svg.node();
}


// ------------------------------------------------------------
// plot_pv
// ------------------------------------------------------------
function plot_pv(pv, {
  cityName = globalCity, 
  countryName = globalCountry,
  width,
  height
} = {}) {
  
  // ========================================
  // DATA PREPARATION
  // ========================================
  // (note: no data preparation needed for this plot)
  
  // ========================================
  // STYLING CALCULATIONS
  // ========================================
  // (use helper functions from plot-helpers.js for all styling calculations)
  const fontSizes = PlotHelpers.calculateFontSizes(width, height);
  const lineHeights = PlotHelpers.calculateLineHeights(fontSizes);
  
  // text content
  const titleText = "Seasonal Availability of Solar Energy, January - December";
  const titleLocation = countryName ? `${cityName}, ${countryName}` : cityName;
  const xAxisLabelText = "Month";
  const yAxisLabelText = "Daily PV energy yield (kWh/kWp)";
  const captionText = ""; // (empty for this plot)
  
  // text wrapping
  const titleLines = PlotHelpers.wrapText(titleText, width - 40, `${fontSizes.title}px system-ui`);
  const subtitleLines = PlotHelpers.wrapText(titleLocation, width - 40, `${fontSizes.subtitle}px system-ui`);
  const xAxisLabelLines = PlotHelpers.wrapText(xAxisLabelText, width * 0.8, `${fontSizes.axisLabel}px system-ui`);
  const yAxisLabelLines = PlotHelpers.wrapText(yAxisLabelText, height * 0.6, `${fontSizes.axisLabel}px system-ui`);
  const captionLines = PlotHelpers.wrapText(captionText, width - 40, `${fontSizes.caption}px system-ui`);

  // calculate text dimensions for margins
  const titleHeight = titleLines.length * lineHeights.title;
  const subtitleHeight = subtitleLines.length * lineHeights.subtitle;
  const xAxisLabelHeight = xAxisLabelLines.length * lineHeights.axisLabel;
  const captionHeight = captionLines.length * lineHeights.caption;
  const yAxisLabelWidth = yAxisLabelLines.length * lineHeights.axisLabel;

  // calculate margins using helper
  const margin = PlotHelpers.calculateMargins(width, height, {
    titleHeight,
    subtitleHeight,
    xAxisLabelHeight,
    captionHeight,
    yAxisLabelWidth
  });
  
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  
  // ========================================
  // SCALES
  // ========================================
  const xScale = d3.scaleBand()
    .domain(pv.map(d => d.monthName))
    .range([0, innerWidth])
    .padding(0.1);
    
  const yScale = d3.scaleLinear()
    .domain([0, Math.max(...pv.map(d => d.maxPv)) * 1.1])
    .range([innerHeight, 0]);

  // ========================================
  // SVG CREATION
  // ========================================
  const svg = d3.create("svg")
    .attr("viewBox", `0 0 ${width} ${height}`)
    .attr("preserveAspectRatio", "xMidYMid meet")
    .style("width", "100%")
    .style("height", "auto")
    .style("max-width", `${width}px`);

  const g = svg.append("g")
    .attr("transform", `translate(${margin.left},${margin.top})`);
  
  // ========================================
  // Y-AXIS
  // ========================================
  const yTicks = PlotHelpers.calculateYTicks(innerHeight);
  const yAxisGroup = g.append("g").attr("class", "y-axis");
  const yAxisCall = d3.axisLeft(yScale)
    .ticks(yTicks)
    .tickSizeOuter(0)
    .tickSizeInner(-innerWidth)
    .tickFormat(d3.format("~s"));

  yAxisGroup.call(yAxisCall);
  yAxisGroup.selectAll(".tick text")
    .style("font-size", `${fontSizes.yAxisTick}px`);
  
  // ========================================
  // X-AXIS
  // ========================================
  const xAxisGroup = g.append("g")
    .attr("class", "x-axis")
    .attr("transform", `translate(0,${innerHeight})`);
    
  xAxisGroup.call(d3.axisBottom(xScale)
    .tickSizeOuter(0)
    .tickSizeInner(-innerHeight));

  // calculate how many ticks to show based on available width
  const barWidth = xScale.bandwidth();
  const availableSpacePerTick = barWidth + (xScale.step() - barWidth);
  
  // determine tick interval (show every nth month)
  let tickInterval;
  if (availableSpacePerTick < 60) {
    tickInterval = 3; // (show every 3rd month (Jan, Apr, Jul, Oct))
  } else if (availableSpacePerTick < 80) {
    tickInterval = 2; // show every 2nd month
  } else {
    tickInterval = 1; // show all months
  }

  // filter and style tick labels
  xAxisGroup.selectAll(".tick text")
    .each(function(d, i) {
      const text = d3.select(this);
      
      // hide ticks that don't match the interval
      if (i % tickInterval !== 0) {
        text.remove();
        return;
      }
      
      const labelText = text.text();
      text.style("font-size", `${fontSizes.xAxisTick}px`);
      
      const lines = PlotHelpers.wrapBarLabel(labelText, barWidth * tickInterval, `${fontSizes.xAxisTick}px system-ui`);
      text.text(null);
      
      lines.forEach((line, j) => {
        text.append("tspan")
          .attr("x", 0)
          .attr("dy", j === 0 ? "1.2em" : "1.1em")
          .text(line);
      });
    });
  
  // ========================================
  // ANNOTATION LINES
  // ========================================
  // (threshold lines for conditions)
  const annotationStrokeWidth = PlotHelpers.calculateAnnotationStrokeWidth(width);

  // "excellent" conditions at 4.5
  PlotHelpers.addHorizontalAnnotation(g, 4.5, yScale, innerWidth, "Excellent Conditions", fontSizes.annotation, annotationStrokeWidth);

  // "favorable" conditions at 3.5
  PlotHelpers.addHorizontalAnnotation(g, 3.5, yScale, innerWidth, "Favorable Conditions", fontSizes.annotation, annotationStrokeWidth);
  
  // ========================================
  // LINE
  // ========================================
  const line = d3.line()
    .x(d => xScale(d.monthName) + xScale.bandwidth() / 2)
    .y(d => yScale(d.maxPv));
    
  g.append("path")
    .datum(pv)
    .attr("fill", "none")
    .attr("stroke", "black")
    .attr("stroke-width", Math.max(1.5, Math.min(3, width / 400)))
    .attr("d", line);
  
  // ========================================
  // DOTS
  // ========================================
  g.selectAll(".dot")
    .data(pv)
    .enter().append("circle")
    .attr("class", "dot")
    .attr("cx", d => xScale(d.monthName) + xScale.bandwidth() / 2)
    .attr("cy", d => yScale(d.maxPv))
    .attr("r", Math.max(2, Math.min(3, width / 200)))
    .attr("fill", "black")
    .style("cursor", "default")
    .on("mouseover", function(event, d) {
      d3.selectAll(".d3-tooltip").remove();

      const tooltip = d3.select("body").append("div")
        .attr("class", "d3-tooltip")
        .style("opacity", 0);
        
      const html = `<div>Month: ${d.monthName}</div><div>Daily PV energy yield: ${(+d.maxPv).toFixed(3)} kWh/kWp</div>`;
      
      const tooltipWidth = 220;
      const windowWidth = window.innerWidth;
      const mouseX = event.pageX;
      
      let leftPos = mouseX + 10;
      if (leftPos + tooltipWidth > windowWidth) {
        leftPos = mouseX - tooltipWidth - 10;
      }
      
      tooltip
        .html(html)
        .style("left", leftPos + "px")
        .style("top", (event.pageY - 35) + "px")
        .transition()
        .duration(200)
        .style("opacity", 1);
    })
    .on("mousemove", function(event) {
      const tooltip = d3.select(".d3-tooltip");
      if (!tooltip.empty()) {
        const tooltipWidth = 220;
        const windowWidth = window.innerWidth;
        const mouseX = event.pageX;
        
        let leftPos = mouseX + 10;
        if (leftPos + tooltipWidth > windowWidth) {
          leftPos = mouseX - tooltipWidth - 10;
        }
        
        tooltip
          .style("left", leftPos + "px")
          .style("top", (event.pageY - 35) + "px");
      }
    })
    .on("mouseout", function() {
      d3.select(".d3-tooltip")
        .transition()
        .duration(200)
        .style("opacity", 0)
        .remove();
    });
  
  // ========================================
  // TITLE
  // ========================================
  const heightScale = height / PlotHelpers.PLOT_BASE.HEIGHT;
  const titleY = PlotHelpers.getTitleY(height, heightScale);
  
  titleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-title")
      .attr("x", 20)
      .attr("y", titleY + (i * lineHeights.title))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.title}px`)
      .text(line);
  });
    
  // ========================================
  // SUBTITLE
  // ========================================
  const subtitleY = PlotHelpers.getSubtitleY(titleY, titleLines.length, lineHeights.title, heightScale);
  
  subtitleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-subtitle")
      .attr("x", 20)
      .attr("y", subtitleY + (i * lineHeights.subtitle))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.subtitle}px`)
      .text(line);
  });
    
  // ========================================
  // Y-AXIS LABEL
  // ========================================
  const widthScale = width / PlotHelpers.PLOT_BASE.WIDTH;
  const yAxisLabelX = -(margin.top + innerHeight/2);
  const yAxisLabelY = PlotHelpers.getYAxisLabelY(widthScale);
  
  yAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("transform", "rotate(-90)")
      .attr("y", yAxisLabelY + (i * lineHeights.axisLabel))
      .attr("x", yAxisLabelX)
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // X-AXIS LABEL
  // ========================================
  const xAxisLabelX = margin.left + innerWidth/2;
  const xAxisLabelY = PlotHelpers.getXAxisLabelY(height, captionHeight, heightScale);
  
  xAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("x", xAxisLabelX)
      .attr("y", xAxisLabelY - ((xAxisLabelLines.length - 1 - i) * lineHeights.axisLabel))
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // CAPTION
  // ========================================
  // (empty for this plot)
  if (captionText) {
    const captionY = PlotHelpers.getCaptionY(height, heightScale);
    
    captionLines.forEach((line, i) => {
      svg.append("text")
        .attr("class", "plot-caption")
        .attr("x", 20)
        .attr("y", captionY - ((captionLines.length - 1 - i) * lineHeights.caption))
        .attr("text-anchor", "start")
        .style("font-size", `${fontSizes.caption}px`)
        .text(line);
    });
  }
  
  return svg.node();
}


// ------------------------------------------------------------
// plot_aq
// ------------------------------------------------------------
function plot_aq(aq_area, {
  cityName = globalCity, 
  countryName = globalCountry,
  width,
  height
} = {}) {
  
  // ========================================
  // DATA PREPARATION
  // ========================================
  const sortedData = aq_area.slice().sort((a, b) => 
    PlotHelpers.parseAirQualityRange(a.bin) - PlotHelpers.parseAirQualityRange(b.bin)
  );

  // air quality colors
  const airQualityColorMap = {
    "0-5": "#fff7de",
    "5-10": "#f8dbc4",
    "10-15": "#eec0ae",
    "15-20": "#e0a79d",
    "20-30": "#d5949f",
    "30-40": "#cf94aa",
    "40-50": "#c394b5",
    "50-100": "#b495c4",
    "100+": "#a07ca0"
  };
  const defaultColor = "#999999"; // (fallback gray if no color map match)
  
  const allAirQualityBins = sortedData.map(d => d.bin);
  
  // complete data with gray bars for visual completeness
  const completeData = allAirQualityBins.map(bin => {
    const existing = sortedData.find(d => d.bin === bin);
    return existing || { bin, count: 0, percentage: 0 };
  });

  // ========================================
  // STYLING CALCULATIONS
  // ========================================
  // (use helper functions from plot-helpers.js for all styling calculations)
  const fontSizes = PlotHelpers.calculateFontSizes(width, height);
  const lineHeights = PlotHelpers.calculateLineHeights(fontSizes);
  
  // text content
  const titleText = "Air Quality";
  const titleLocation = countryName ? `${cityName}, ${countryName}` : cityName;
  const xAxisLabelText = "Concentrations of PM2.5";
  const yAxisLabelText = "Percentage of Area (%)";
  const captionText = ""; // (empty for this plot)
  
  // text wrapping
  const titleLines = PlotHelpers.wrapText(titleText, width - 40, `${fontSizes.title}px system-ui`);
  const subtitleLines = PlotHelpers.wrapText(titleLocation, width - 40, `${fontSizes.subtitle}px system-ui`);
  const xAxisLabelLines = PlotHelpers.wrapText(xAxisLabelText, width * 0.8, `${fontSizes.axisLabel}px system-ui`);
  const yAxisLabelLines = PlotHelpers.wrapText(yAxisLabelText, height * 0.6, `${fontSizes.axisLabel}px system-ui`);
  const captionLines = PlotHelpers.wrapText(captionText, width - 40, `${fontSizes.caption}px system-ui`);

  // calculate text dimensions for margins
  const titleHeight = titleLines.length * lineHeights.title;
  const subtitleHeight = subtitleLines.length * lineHeights.subtitle;
  const xAxisLabelHeight = xAxisLabelLines.length * lineHeights.axisLabel;
  const captionHeight = captionLines.length * lineHeights.caption;
  const yAxisLabelWidth = yAxisLabelLines.length * lineHeights.axisLabel;

  // calculate margins using helper
  const margin = PlotHelpers.calculateMargins(width, height, {
    titleHeight,
    subtitleHeight,
    xAxisLabelHeight,
    captionHeight,
    yAxisLabelWidth
  });
  
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  
  // ========================================
  // SCALES
  // ========================================
  const xScale = d3.scaleBand()
    .domain(completeData.map(d => d.bin))
    .range([0, innerWidth])
    .padding(0.1);
    
  const yScale = d3.scaleLinear()
    .domain([0, 100])
    .range([innerHeight, 0]);

  // ========================================
  // SVG CREATION
  // ========================================
  const svg = d3.create("svg")
    .attr("viewBox", `0 0 ${width} ${height}`)
    .attr("preserveAspectRatio", "xMidYMid meet")
    .style("width", "100%")
    .style("height", "auto")
    .style("max-width", `${width}px`);

  const g = svg.append("g")
    .attr("transform", `translate(${margin.left},${margin.top})`);
  
  // ========================================
  // Y-AXIS
  // ========================================
  const yTicks = PlotHelpers.calculateYTicks(innerHeight);
  const yAxisGroup = g.append("g").attr("class", "y-axis");
  const yAxisCall = d3.axisLeft(yScale)
    .ticks(yTicks)
    .tickSizeOuter(0)
    .tickSizeInner(-innerWidth)
    .tickFormat(d3.format("~s"));

  yAxisGroup.call(yAxisCall);
  yAxisGroup.selectAll(".tick text")
    .style("font-size", `${fontSizes.yAxisTick}px`);
    
  // ========================================
  // BARS
  // ========================================
  // gray background bars
  g.selectAll(".background-bar")
    .data(completeData)
    .enter().append("rect")
    .attr("class", "background-bar")
    .attr("x", d => xScale(d.bin))
    .attr("width", xScale.bandwidth())
    .attr("y", 0)
    .attr("height", innerHeight);
    
  // data bars with smart tooltips
  g.selectAll(".data-bar")
    .data(completeData.filter(d => d.percentage > 0))
    .enter().append("rect")
    .attr("class", "data-bar")
    .attr("x", d => xScale(d.bin))
    .attr("width", xScale.bandwidth())
    .attr("y", d => yScale(d.percentage))
    .attr("height", d => innerHeight - yScale(d.percentage))
    .attr("fill", d => airQualityColorMap[d.bin] || defaultColor)
    .attr("fill-opacity", 1)
    .attr("stroke", d => d3.color(airQualityColorMap[d.bin] || defaultColor).darker(0.5))
    .attr("stroke-width", 1)
    .style("cursor", "default")
    .on("mouseover", function(event, d) {
      d3.selectAll(".d3-tooltip").remove();

      const tooltip = d3.select("body").append("div")
        .attr("class", "d3-tooltip")
        .style("opacity", 0);
        
      const html = `<div>PM 2.5: ${d.bin} µg/m<sup>3</sup></div><div>Percentage of Area: ${d.percentage.toFixed(1)}%</div>`;
      
      // calculate position to avoid bleeding off screen
      const tooltipWidth = 220;
      const windowWidth = window.innerWidth;
      const mouseX = event.pageX;
      
      let leftPos = mouseX + 10;
      if (leftPos + tooltipWidth > windowWidth) {
        leftPos = mouseX - tooltipWidth - 10;
      }
      
      tooltip
        .html(html)
        .style("left", leftPos + "px")
        .style("top", (event.pageY - 35) + "px")
        .transition()
        .duration(200)
        .style("opacity", 1);
    })
    .on("mousemove", function(event) {
      const tooltip = d3.select(".d3-tooltip");
      if (!tooltip.empty()) {
        const tooltipWidth = 220;
        const windowWidth = window.innerWidth;
        const mouseX = event.pageX;
        
        let leftPos = mouseX + 10;
        if (leftPos + tooltipWidth > windowWidth) {
          leftPos = mouseX - tooltipWidth - 10;
        }
        
        tooltip
          .style("left", leftPos + "px")
          .style("top", (event.pageY - 35) + "px");
      }
    })
    .on("mouseout", function() {
      d3.select(".d3-tooltip")
        .transition()
        .duration(200)
        .style("opacity", 0)
        .remove();
    });

  // ========================================
  // BAR PERCENTAGE LABELS
  // ========================================
  g.selectAll(".bar-label")
    .data(completeData)
    .enter().append("text")
    .attr("class", "plot-bar-label")
    .attr("x", d => xScale(d.bin) + xScale.bandwidth()/2)
    .attr("y", d => d.percentage > 0 ? yScale(d.percentage) - 8 : innerHeight/2)
    .attr("text-anchor", "middle")
    .attr("fill", d => d.percentage > 0 ? "black" : "#6c757d")
    .style("font-size", `${fontSizes.barLabel}px`)
    .attr("font-style", d => d.percentage > 0 ? "normal" : "italic")
    .text(d => d.percentage > 0 ? `${d.percentage.toFixed(1)}%` : "")
    .style("display", d => d.percentage > 2 || d.percentage === 0 ? "block" : "none");

  // ========================================
  // X-AXIS
  // ========================================
  const xAxisGroup = g.append("g")
    .attr("class", "x-axis")
    .attr("transform", `translate(0,${innerHeight})`);
    
  xAxisGroup.call(d3.axisBottom(xScale)
    .tickSizeOuter(0)
    .tickSizeInner(0));
 
  // x-axis tick labels with wrapping
  const barWidth = xScale.bandwidth();
  const xAxisTickSize = PlotHelpers.calculateXAxisTickSize(barWidth);
  
  xAxisGroup.selectAll(".tick text")
    .each(function(d) {
      const text = d3.select(this);
      const labelText = text.text();
      
      text.style("font-size", `${xAxisTickSize}px`);
      
      const lines = PlotHelpers.wrapBarLabel(labelText, barWidth, `${xAxisTickSize}px system-ui`);
      text.text(null);
      
      lines.forEach((line, i) => {
        text.append("tspan")
          .attr("x", 0)
          .attr("dy", i === 0 ? "1.2em" : "1.1em")
          .text(line);
      });
    });
    
  // ========================================
  // TITLE
  // ========================================
  const heightScale = height / PlotHelpers.PLOT_BASE.HEIGHT;
  const titleY = PlotHelpers.getTitleY(height, heightScale);
  
  titleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-title")
      .attr("x", 20)
      .attr("y", titleY + (i * lineHeights.title))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.title}px`)
      .text(line);
  });
    
  // ========================================
  // SUBTITLE
  // ========================================
  const subtitleY = PlotHelpers.getSubtitleY(titleY, titleLines.length, lineHeights.title, heightScale);
  
  subtitleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-subtitle")
      .attr("x", 20)
      .attr("y", subtitleY + (i * lineHeights.subtitle))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.subtitle}px`)
      .text(line);
  });
    
  // ========================================
  // Y-AXIS LABEL
  // ========================================
  const widthScale = width / PlotHelpers.PLOT_BASE.WIDTH;
  const yAxisLabelX = -(margin.top + innerHeight/2);
  const yAxisLabelY = PlotHelpers.getYAxisLabelY(widthScale);
  
  yAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("transform", "rotate(-90)")
      .attr("y", yAxisLabelY + (i * lineHeights.axisLabel))
      .attr("x", yAxisLabelX)
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // X-AXIS LABEL
  // ========================================
  const xAxisLabelX = margin.left + innerWidth/2;
  const xAxisLabelY = PlotHelpers.getXAxisLabelY(height, captionHeight, heightScale);
  
  xAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("x", xAxisLabelX)
      .attr("y", xAxisLabelY - ((xAxisLabelLines.length - 1 - i) * lineHeights.axisLabel))
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // CAPTION
  // ========================================
  // (empty for this plot)
  if (captionText) {
    const captionY = PlotHelpers.getCaptionY(height, heightScale);
    
    captionLines.forEach((line, i) => {
      svg.append("text")
        .attr("class", "plot-caption")
        .attr("x", 20)
        .attr("y", captionY - ((captionLines.length - 1 - i) * lineHeights.caption))
        .attr("text-anchor", "start")
        .style("font-size", `${fontSizes.caption}px`)
        .text(line);
    });
  }
  
  return svg.node();
}


// ------------------------------------------------------------
// plot_summer_area
// ------------------------------------------------------------
function plot_summer_area(summer_area, {
  cityName = globalCity, 
  countryName = globalCountry,
  width,
  height
} = {}) {
  
  // ========================================
  // DATA PREPARATION
  // ========================================
  // drop nodata: off-AOI cells are filled with 0 and binned as "0-5" (real surface
  // temps are never ~0C); drop empty bins; recompute % on valid cells (team fix)
  summer_area = (summer_area || []).filter(d => +d.count > 0 && parseInt(d.bin) !== 0);
  const _validTotal = summer_area.reduce((s, d) => s + (+d.count), 0) || 1;
  summer_area = summer_area.map(d => ({ ...d, percentage: (+d.count) / _validTotal * 100 }));
  const sortedData = summer_area.slice().sort((a, b) => {
    const aTemp = parseInt(a.bin.split('-')[0]);
    const bTemp = parseInt(b.bin.split('-')[0]);
    return aTemp - bTemp;
  });

  // get temperature range from data
  const minTemp = parseInt(sortedData[0].bin.split('-')[0]);
  const maxTemp = parseInt(sortedData[sortedData.length - 1].bin.split('-')[1]);
  
  // color scale: blue (cool) to red (hot) gradient
  const colorScale = d3.scaleLinear()
    .domain([
      minTemp, 
      minTemp + (maxTemp - minTemp) * 0.33,
      minTemp + (maxTemp - minTemp) * 0.67,
      maxTemp
    ])
    .range(["#8db4d4", "#d3daba", "#f2cb94", "#e37b74"])
    .interpolate(d3.interpolateRgb);

  // create color map for all temperature bins
  const tempColorMap = {};
  sortedData.forEach(d => {
    const binStart = parseInt(d.bin.split('-')[0]);
    const binEnd = parseInt(d.bin.split('-')[1]);
    const binMidpoint = (binStart + binEnd) / 2;
    tempColorMap[d.bin] = colorScale(binMidpoint);
  });
  const defaultColor = "#ff6b35"; // (fallback color)
  
  const allTempBins = sortedData.map(d => d.bin);
  
  // complete data with gray bars for visual completeness
  const completeData = allTempBins.map(bin => {
    const existing = sortedData.find(d => d.bin === bin);
    return existing || { bin, count: 0, percentage: 0 };
  });

  // ========================================
  // STYLING CALCULATIONS
  // ========================================
  // (use helper functions from plot-helpers.js for all styling calculations)
  const fontSizes = PlotHelpers.calculateFontSizes(width, height);
  const lineHeights = PlotHelpers.calculateLineHeights(fontSizes);
  
  // text content
  const titleText = "Summer Surface Temperature Distribution";
  const titleLocation = countryName ? `${cityName}, ${countryName}` : cityName;
  const xAxisLabelText = "Mean Surface Temperature (°C)";
  const yAxisLabelText = "Percentage of Area (%)";
  const captionText = "Data: Landsat Level 2 Surface Temperature Science Product courtesy of the U.S. Geological Survey.";
  
  // text wrapping
  const titleLines = PlotHelpers.wrapText(titleText, width - 40, `${fontSizes.title}px system-ui`);
  const subtitleLines = PlotHelpers.wrapText(titleLocation, width - 40, `${fontSizes.subtitle}px system-ui`);
  const xAxisLabelLines = PlotHelpers.wrapText(xAxisLabelText, width * 0.8, `${fontSizes.axisLabel}px system-ui`);
  const yAxisLabelLines = PlotHelpers.wrapText(yAxisLabelText, height * 0.6, `${fontSizes.axisLabel}px system-ui`);
  const captionLines = PlotHelpers.wrapText(captionText, width - 40, `${fontSizes.caption}px system-ui`);

  // calculate text dimensions for margins
  const titleHeight = titleLines.length * lineHeights.title;
  const subtitleHeight = subtitleLines.length * lineHeights.subtitle;
  const xAxisLabelHeight = xAxisLabelLines.length * lineHeights.axisLabel;
  const captionHeight = captionLines.length * lineHeights.caption;
  const yAxisLabelWidth = yAxisLabelLines.length * lineHeights.axisLabel;

  // calculate margins using helper
  const margin = PlotHelpers.calculateMargins(width, height, {
    titleHeight,
    subtitleHeight,
    xAxisLabelHeight,
    captionHeight,
    yAxisLabelWidth
  });
  
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  
  // ========================================
  // SCALES
  // ========================================
  const xScale = d3.scaleBand()
    .domain(completeData.map(d => d.bin))
    .range([0, innerWidth])
    .padding(0.1);
    
  const yScale = d3.scaleLinear()
    .domain([0, 100])
    .range([innerHeight, 0]);

  // ========================================
  // SVG CREATION
  // ========================================
  const svg = d3.create("svg")
    .attr("viewBox", `0 0 ${width} ${height}`)
    .attr("preserveAspectRatio", "xMidYMid meet")
    .style("width", "100%")
    .style("height", "auto")
    .style("max-width", `${width}px`);

  const g = svg.append("g")
    .attr("transform", `translate(${margin.left},${margin.top})`);
  
  // ========================================
  // Y-AXIS
  // ========================================
  const yTicks = PlotHelpers.calculateYTicks(innerHeight);
  const yAxisGroup = g.append("g").attr("class", "y-axis");
  const yAxisCall = d3.axisLeft(yScale)
    .ticks(yTicks)
    .tickSizeOuter(0)
    .tickSizeInner(-innerWidth)
    .tickFormat(d3.format("~s"));

  yAxisGroup.call(yAxisCall);
  yAxisGroup.selectAll(".tick text")
    .style("font-size", `${fontSizes.yAxisTick}px`);
    
  // ========================================
  // BARS
  // ========================================
  // gray background bars
  g.selectAll(".background-bar")
    .data(completeData)
    .enter().append("rect")
    .attr("class", "background-bar")
    .attr("x", d => xScale(d.bin))
    .attr("width", xScale.bandwidth())
    .attr("y", 0)
    .attr("height", innerHeight);
    
  // data bars with temperature gradient colors
  g.selectAll(".data-bar")
    .data(completeData.filter(d => d.percentage > 0))
    .enter().append("rect")
    .attr("class", "data-bar")
    .attr("x", d => xScale(d.bin))
    .attr("width", xScale.bandwidth())
    .attr("y", d => yScale(d.percentage))
    .attr("height", d => innerHeight - yScale(d.percentage))
    .attr("fill", d => tempColorMap[d.bin] || defaultColor)
    .attr("fill-opacity", 1)
    .attr("stroke", d => d3.color(tempColorMap[d.bin] || defaultColor).darker(0.3))
    .attr("stroke-width", 1)
    .style("cursor", "default")
    .on("mouseover", function(event, d) {
      d3.selectAll(".d3-tooltip").remove();

      const tooltip = d3.select("body").append("div")
        .attr("class", "d3-tooltip")
        .style("opacity", 0);
        
      const html = `<div>Temperature: ${d.bin}°C</div><div>Percentage of Area: ${d.percentage.toFixed(1)}%</div>`;
      
      // calculate position to avoid bleeding off screen
      const tooltipWidth = 220;
      const windowWidth = window.innerWidth;
      const mouseX = event.pageX;
      
      let leftPos = mouseX + 10;
      if (leftPos + tooltipWidth > windowWidth) {
        leftPos = mouseX - tooltipWidth - 10;
      }
      
      tooltip
        .html(html)
        .style("left", leftPos + "px")
        .style("top", (event.pageY - 35) + "px")
        .transition()
        .duration(200)
        .style("opacity", 1);
    })
    .on("mousemove", function(event) {
      const tooltip = d3.select(".d3-tooltip");
      if (!tooltip.empty()) {
        const tooltipWidth = 220;
        const windowWidth = window.innerWidth;
        const mouseX = event.pageX;
        
        let leftPos = mouseX + 10;
        if (leftPos + tooltipWidth > windowWidth) {
          leftPos = mouseX - tooltipWidth - 10;
        }
        
        tooltip
          .style("left", leftPos + "px")
          .style("top", (event.pageY - 35) + "px");
      }
    })
    .on("mouseout", function() {
      d3.select(".d3-tooltip")
        .transition()
        .duration(200)
        .style("opacity", 0)
        .remove();
    });

  // ========================================
  // BAR PERCENTAGE LABELS
  // ========================================
  g.selectAll(".bar-label")
    .data(completeData)
    .enter().append("text")
    .attr("class", "plot-bar-label")
    .attr("x", d => xScale(d.bin) + xScale.bandwidth()/2)
    .attr("y", d => d.percentage > 0 ? yScale(d.percentage) - 8 : innerHeight/2)
    .attr("text-anchor", "middle")
    .attr("fill", d => d.percentage > 0 ? "black" : "#6c757d")
    .style("font-size", `${fontSizes.barLabel}px`)
    .attr("font-style", d => d.percentage > 0 ? "normal" : "italic")
    .text(d => d.percentage > 0 ? `${d.percentage.toFixed(1)}%` : "")
    .style("display", d => d.percentage > 2 || d.percentage === 0 ? "block" : "none");

  // ========================================
  // X-AXIS
  // ========================================
  const xAxisGroup = g.append("g")
    .attr("class", "x-axis")
    .attr("transform", `translate(0,${innerHeight})`);
    
  xAxisGroup.call(d3.axisBottom(xScale)
    .tickSizeOuter(0)
    .tickSizeInner(0));
 
  // x-axis tick labels with wrapping
  const barWidth = xScale.bandwidth();
  const xAxisTickSize = PlotHelpers.calculateXAxisTickSize(barWidth);
  
  xAxisGroup.selectAll(".tick text")
    .each(function(d) {
      const text = d3.select(this);
      const labelText = text.text();
      
      text.style("font-size", `${xAxisTickSize}px`);
      
      const lines = PlotHelpers.wrapBarLabel(labelText, barWidth, `${xAxisTickSize}px system-ui`);
      text.text(null);
      
      lines.forEach((line, i) => {
        text.append("tspan")
          .attr("x", 0)
          .attr("dy", i === 0 ? "1.2em" : "1.1em")
          .text(line);
      });
    });
    
  // ========================================
  // TITLE
  // ========================================
  const heightScale = height / PlotHelpers.PLOT_BASE.HEIGHT;
  const titleY = PlotHelpers.getTitleY(height, heightScale);
  
  titleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-title")
      .attr("x", 20)
      .attr("y", titleY + (i * lineHeights.title))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.title}px`)
      .text(line);
  });
    
  // ========================================
  // SUBTITLE
  // ========================================
  const subtitleY = PlotHelpers.getSubtitleY(titleY, titleLines.length, lineHeights.title, heightScale);
  
  subtitleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-subtitle")
      .attr("x", 20)
      .attr("y", subtitleY + (i * lineHeights.subtitle))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.subtitle}px`)
      .text(line);
  });
    
  // ========================================
  // Y-AXIS LABEL
  // ========================================
  const widthScale = width / PlotHelpers.PLOT_BASE.WIDTH;
  const yAxisLabelX = -(margin.top + innerHeight/2);
  const yAxisLabelY = PlotHelpers.getYAxisLabelY(widthScale);
  
  yAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("transform", "rotate(-90)")
      .attr("y", yAxisLabelY + (i * lineHeights.axisLabel))
      .attr("x", yAxisLabelX)
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // X-AXIS LABEL
  // ========================================
  const xAxisLabelX = margin.left + innerWidth/2;
  const xAxisLabelY = PlotHelpers.getXAxisLabelY(height, captionHeight, heightScale);
  
  xAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("x", xAxisLabelX)
      .attr("y", xAxisLabelY - ((xAxisLabelLines.length - 1 - i) * lineHeights.axisLabel))
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // CAPTION
  // ========================================
  const captionY = PlotHelpers.getCaptionY(height, heightScale);
  
  captionLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-caption")
      .attr("x", 20)
      .attr("y", captionY - ((captionLines.length - 1 - i) * lineHeights.caption))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.caption}px`)
      .text(line);
  });
  
  return svg.node();
}


// ------------------------------------------------------------
// plot_ndvi_area
// ------------------------------------------------------------
function plot_ndvi_area(ndvi_area, {
  cityName = globalCity, 
  countryName = globalCountry,
  width,
  height
} = {}) {
  
  // ========================================
  // DATA PREPARATION
  // ========================================
  if (!ndvi_area || !ndvi_area.length) return null;  // no data -> render nothing (team fix)
  // show vegetation categories only: drop Water and Built-up bins (team fix)
  const _vegExclude = { "-1-0.015": true, "0.015-0.14": true };
  const sortedData = ndvi_area.slice()
    .filter(d => !_vegExclude[d.bin])
    .sort((a, b) => PlotHelpers.parseNdviRange(a.bin) - PlotHelpers.parseNdviRange(b.bin));

  // color mapping for coverage type
  const ndviColorMap = {
    "Water": "#b2b2d5",
    "Built-up": "#eff4d8",
    "Barren": "#cfe4c7",
    "Shrub and Grassland": "#a5cd9f",
    "Sparse": "#82b685",
    "Dense": "#2e6a34"   // distinct from Sparse (team fix)
  };
  const defaultColor = "#999999"; // (fallback gray if no color map match)

  // map from bin values to type
  const binToTypeMap = {
    "-1-0.015": "Water",
    "0.015-0.14": "Built-up", 
    "0.14-0.18": "Barren", 
    "0.18-0.27": "Shrub and Grassland",
    "0.27-0.36": "Sparse",
    "0.36-1": "Dense"
  };
  
  const allNdviBins = sortedData.map(d => d.bin);
  
  // complete data with gray bars for visual completeness
  const completeData = allNdviBins.map(bin => {
    const existing = sortedData.find(d => d.bin === bin);
    return existing || { bin, count: 0, percentage: 0 };
  });

  // ========================================
  // STYLING CALCULATIONS
  // ========================================
  // (use helper functions from plot-helpers.js for all styling calculations)
  const fontSizes = PlotHelpers.calculateFontSizes(width, height);
  const lineHeights = PlotHelpers.calculateLineHeights(fontSizes);
  
  // text content
  const titleText = "Vegetated Areas";
  const titleLocation = countryName ? `${cityName}, ${countryName}` : cityName;
  const xAxisLabelText = "Normalized Difference Vegetation Index (NDVI)";
  const yAxisLabelText = "Percentage of Area (%)";
  const captionText = "Data: European Space Agency, 2020 | Normalized Difference Vegetation Index";
  
  // text wrapping
  const titleLines = PlotHelpers.wrapText(titleText, width - 40, `${fontSizes.title}px system-ui`);
  const subtitleLines = PlotHelpers.wrapText(titleLocation, width - 40, `${fontSizes.subtitle}px system-ui`);
  const xAxisLabelLines = PlotHelpers.wrapText(xAxisLabelText, width * 0.8, `${fontSizes.axisLabel}px system-ui`);
  const yAxisLabelLines = PlotHelpers.wrapText(yAxisLabelText, height * 0.6, `${fontSizes.axisLabel}px system-ui`);
  const captionLines = PlotHelpers.wrapText(captionText, width - 40, `${fontSizes.caption}px system-ui`);

  // calculate text dimensions for margins
  const titleHeight = titleLines.length * lineHeights.title;
  const subtitleHeight = subtitleLines.length * lineHeights.subtitle;
  const xAxisLabelHeight = xAxisLabelLines.length * lineHeights.axisLabel;
  const captionHeight = captionLines.length * lineHeights.caption;
  const yAxisLabelWidth = yAxisLabelLines.length * lineHeights.axisLabel;

  // calculate margins using helper
  const margin = PlotHelpers.calculateMargins(width, height, {
    titleHeight,
    subtitleHeight,
    xAxisLabelHeight,
    captionHeight,
    yAxisLabelWidth
  });
  
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  
  // ========================================
  // SCALES
  // ========================================
  const xScale = d3.scaleBand()
    .domain(completeData.map(d => d.bin))
    .range([0, innerWidth])
    .padding(0.1);
    
  const yScale = d3.scaleLinear()
    .domain([0, (() => {   // y-axis max from the data (+10%), not fixed 0-100 (team fix)
      const maxPct = Math.max(...completeData.map(d => d.percentage));
      return maxPct < 5 ? Math.ceil(maxPct * 1.1 * 2) / 2 : (Math.ceil(maxPct * 1.1 / 5) * 5 || 100);
    })()])
    .range([innerHeight, 0]);

  // ========================================
  // SVG CREATION
  // ========================================
  const svg = d3.create("svg")
    .attr("viewBox", `0 0 ${width} ${height}`)
    .attr("preserveAspectRatio", "xMidYMid meet")
    .style("width", "100%")
    .style("height", "auto")
    .style("max-width", `${width}px`);

  const g = svg.append("g")
    .attr("transform", `translate(${margin.left},${margin.top})`);
  
  // ========================================
  // Y-AXIS
  // ========================================
  const yTicks = PlotHelpers.calculateYTicks(innerHeight);
  const yAxisGroup = g.append("g").attr("class", "y-axis");
  const yAxisCall = d3.axisLeft(yScale)
    .ticks(yTicks)
    .tickSizeOuter(0)
    .tickSizeInner(-innerWidth)
    .tickFormat(d => d < 1 ? d.toFixed(1) : d); // decimals for small values (team fix)

  yAxisGroup.call(yAxisCall);
  yAxisGroup.selectAll(".tick text")
    .style("font-size", `${fontSizes.yAxisTick}px`);
    
  // ========================================
  // BARS
  // ========================================
  // gray background bars
  g.selectAll(".background-bar")
    .data(completeData)
    .enter().append("rect")
    .attr("class", "background-bar")
    .attr("x", d => xScale(d.bin))
    .attr("width", xScale.bandwidth())
    .attr("y", 0)
    .attr("height", innerHeight);
    
  // data bars with smart tooltips
  g.selectAll(".data-bar")
    .data(completeData.filter(d => d.percentage > 0))
    .enter().append("rect")
    .attr("class", "data-bar")
    .attr("x", d => xScale(d.bin))
    .attr("width", xScale.bandwidth())
    .attr("y", d => yScale(d.percentage))
    .attr("height", d => innerHeight - yScale(d.percentage))
    .attr("fill", d => ndviColorMap[d.type] || defaultColor)
    .attr("fill-opacity", 1)
    .attr("stroke", d => d3.color(ndviColorMap[d.type] || defaultColor).darker(0.3))
    .attr("stroke-width", 1)
    .style("cursor", "default")
    .on("mouseover", function(event, d) {
      d3.selectAll(".d3-tooltip").remove();

      const tooltip = d3.select("body").append("div")
        .attr("class", "d3-tooltip")
        .style("opacity", 0);
        
      const html = `<div>Coverage: ${d.type}</div><div>Percentage of Area: ${d.percentage.toFixed(1)}%</div>`;
      
      // calculate position to avoid bleeding off screen
      const tooltipWidth = 220;
      const windowWidth = window.innerWidth;
      const mouseX = event.pageX;
      
      let leftPos = mouseX + 10;
      if (leftPos + tooltipWidth > windowWidth) {
        leftPos = mouseX - tooltipWidth - 10;
      }
      
      tooltip
        .html(html)
        .style("left", leftPos + "px")
        .style("top", (event.pageY - 35) + "px")
        .transition()
        .duration(200)
        .style("opacity", 1);
    })
    .on("mousemove", function(event) {
      const tooltip = d3.select(".d3-tooltip");
      if (!tooltip.empty()) {
        const tooltipWidth = 220;
        const windowWidth = window.innerWidth;
        const mouseX = event.pageX;
        
        let leftPos = mouseX + 10;
        if (leftPos + tooltipWidth > windowWidth) {
          leftPos = mouseX - tooltipWidth - 10;
        }
        
        tooltip
          .style("left", leftPos + "px")
          .style("top", (event.pageY - 35) + "px");
      }
    })
    .on("mouseout", function() {
      d3.select(".d3-tooltip")
        .transition()
        .duration(200)
        .style("opacity", 0)
        .remove();
    });

  // ========================================
  // BAR PERCENTAGE LABELS
  // ========================================
  g.selectAll(".bar-label")
    .data(completeData)
    .enter().append("text")
    .attr("class", "plot-bar-label")
    .attr("x", d => xScale(d.bin) + xScale.bandwidth()/2)
    .attr("y", d => d.percentage > 0 ? yScale(d.percentage) - 8 : innerHeight/2)
    .attr("text-anchor", "middle")
    .attr("fill", d => d.percentage > 0 ? "black" : "#6c757d")
    .style("font-size", `${fontSizes.barLabel}px`)
    .attr("font-style", d => d.percentage > 0 ? "normal" : "italic")
    .text(d => d.percentage > 0 ? `${d.percentage.toFixed(2)}%` : ""); // 2 decimals, hide 0% (team fix)

  // ========================================
  // X-AXIS
  // ========================================
  const xAxisGroup = g.append("g")
    .attr("class", "x-axis")
    .attr("transform", `translate(0,${innerHeight})`);
    
  xAxisGroup.call(d3.axisBottom(xScale)
    .tickSizeOuter(0)
    .tickSizeInner(0));
 
  // x-axis tick labels with wrapping
  const barWidth = xScale.bandwidth();
  const xAxisTickSize = PlotHelpers.calculateXAxisTickSize(barWidth);
  
  xAxisGroup.selectAll(".tick text")
    .each(function(d) {
      const text = d3.select(this);
      const labelText = text.text();
      
      text.style("font-size", `${xAxisTickSize}px`);
      
      const lines = PlotHelpers.wrapBarLabel(labelText, barWidth, `${xAxisTickSize}px system-ui`);
      text.text(null);
      
      lines.forEach((line, i) => {
        text.append("tspan")
          .attr("x", 0)
          .attr("dy", i === 0 ? "1.2em" : "1.1em")
          .text(line);
      });
    });
    
  // ========================================
  // TITLE
  // ========================================
  const heightScale = height / PlotHelpers.PLOT_BASE.HEIGHT;
  const titleY = PlotHelpers.getTitleY(height, heightScale);
  
  titleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-title")
      .attr("x", 20)
      .attr("y", titleY + (i * lineHeights.title))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.title}px`)
      .text(line);
  });
    
  // ========================================
  // SUBTITLE
  // ========================================
  const subtitleY = PlotHelpers.getSubtitleY(titleY, titleLines.length, lineHeights.title, heightScale);
  
  subtitleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-subtitle")
      .attr("x", 20)
      .attr("y", subtitleY + (i * lineHeights.subtitle))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.subtitle}px`)
      .text(line);
  });
    
  // ========================================
  // Y-AXIS LABEL
  // ========================================
  const widthScale = width / PlotHelpers.PLOT_BASE.WIDTH;
  const yAxisLabelX = -(margin.top + innerHeight/2);
  const yAxisLabelY = PlotHelpers.getYAxisLabelY(widthScale);
  
  yAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("transform", "rotate(-90)")
      .attr("y", yAxisLabelY + (i * lineHeights.axisLabel))
      .attr("x", yAxisLabelX)
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // X-AXIS LABEL
  // ========================================
  const xAxisLabelX = margin.left + innerWidth/2;
  const xAxisLabelY = PlotHelpers.getXAxisLabelY(height, captionHeight, heightScale);
  
  xAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("x", xAxisLabelX)
      .attr("y", xAxisLabelY - ((xAxisLabelLines.length - 1 - i) * lineHeights.axisLabel))
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // CAPTION
  // ========================================
  const captionY = PlotHelpers.getCaptionY(height, heightScale);
  
  captionLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-caption")
      .attr("x", 20)
      .attr("y", captionY - ((captionLines.length - 1 - i) * lineHeights.caption))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.caption}px`)
      .text(line);
  });
  
  return svg.node();
}


// ------------------------------------------------------------
// plot_fe
// ------------------------------------------------------------
function plot_fe(fe, {
  cityName = globalCity,
  countryName = globalCountry,
  width,
  height
} = {}) {
  
  // ========================================
  // DATA PREPARATION
  // ========================================
  // get unique months for x-axis
  const monthNames = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"
  };
  
  // ========================================
  // STYLING CALCULATIONS
  // ========================================
  // (use helper functions from plot-helpers.js for all styling calculations)
  const fontSizes = PlotHelpers.calculateFontSizes(width, height);
  const lineHeights = PlotHelpers.calculateLineHeights(fontSizes);
  
  // text content
  const titleText = "Large flood events, 1985-2025";
  const titleLocation = countryName ? `${cityName}, ${countryName}` : cityName;
  const xAxisLabelText = "Month";
  const yAxisLabelText = "Year";
  const captionText = ""; // (empty for this plot)
  
  // text wrapping
  const titleLines = PlotHelpers.wrapText(titleText, width - 40, `${fontSizes.title}px system-ui`);
  const subtitleLines = PlotHelpers.wrapText(titleLocation, width - 40, `${fontSizes.subtitle}px system-ui`);
  const xAxisLabelLines = PlotHelpers.wrapText(xAxisLabelText, width * 0.8, `${fontSizes.axisLabel}px system-ui`);
  const yAxisLabelLines = PlotHelpers.wrapText(yAxisLabelText, height * 0.6, `${fontSizes.axisLabel}px system-ui`);
  const captionLines = PlotHelpers.wrapText(captionText, width - 40, `${fontSizes.caption}px system-ui`);

  // calculate text dimensions for margins
  const titleHeight = titleLines.length * lineHeights.title;
  const subtitleHeight = subtitleLines.length * lineHeights.subtitle;
  const xAxisLabelHeight = xAxisLabelLines.length * lineHeights.axisLabel;
  const captionHeight = captionLines.length * lineHeights.caption;
  const yAxisLabelWidth = yAxisLabelLines.length * lineHeights.axisLabel;

  // calculate margins using helper
  const margin = PlotHelpers.calculateMargins(width, height, {
    titleHeight,
    subtitleHeight,
    xAxisLabelHeight,
    captionHeight,
    yAxisLabelWidth
  });
  
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  
  // ========================================
  // SCALES
  // ========================================
  const xScale = d3.scaleLinear()
    .domain([0.5, 12.5])
    .range([0, innerWidth]);
    
  const yScale = d3.scaleLinear()
    .domain([1980, 2026])
    .range([innerHeight, 0]);
  
  // bubble radius scale using helper
  const radiusRange = PlotHelpers.calculateBubbleRadiusRange(width);
  const displacedValues = fe.map(d => d.DISPLACED).filter(d => d != null);
  const rScale = d3.scaleSqrt()
    .domain([Math.min(...displacedValues), Math.max(...displacedValues)])
    .range(radiusRange);
  
  // color scale
  const colorScale = d3.scaleOrdinal()
    .domain(["Large event", "Very large event"])
    .range(["#87CEEB", "#000080"]);

  // ========================================
  // SVG CREATION
  // ========================================
  const svg = d3.create("svg")
    .attr("viewBox", `0 0 ${width} ${height}`)
    .attr("preserveAspectRatio", "xMidYMid meet")
    .style("width", "100%")
    .style("height", "auto")
    .style("max-width", `${width}px`);

  const g = svg.append("g")
    .attr("transform", `translate(${margin.left},${margin.top})`);
  
  // ========================================
  // Y-AXIS
  // ========================================
  const yearTicks = PlotHelpers.calculateYearTicks(1985, 2025, width);
  const yAxisGroup = g.append("g").attr("class", "y-axis");
  const yAxisCall = d3.axisLeft(yScale)
    .tickValues(yearTicks.values)
    .tickFormat(d3.format("d"))
    .tickSizeOuter(0)
    .tickSizeInner(-innerWidth);

  yAxisGroup.call(yAxisCall);
  yAxisGroup.selectAll(".tick text")
    .style("font-size", `${fontSizes.yAxisTick}px`);
  
  // ========================================
  // X-AXIS
  // ========================================
  // calculate available space per month
  const totalMonths = 12;
  const availableSpacePerMonth = innerWidth / totalMonths;

  // determine tick interval (show every nth month)
  let tickInterval;
  if (availableSpacePerMonth < 40) {
    tickInterval = 4; // (show every 4th month (Jan, May, Sep))
  } else if (availableSpacePerMonth < 60) {
    tickInterval = 3; // (show every 3rd month (Jan, Apr, Jul, Oct))
  } else if (availableSpacePerMonth < 80) {
    tickInterval = 2; // (show every 2nd month)
  } else {
    tickInterval = 1; // (show all months)
  }

  // filter month ticks based on interval
  const monthTickValues = d3.range(1, 13).filter((m, index) => index % tickInterval === 0);

  const xAxisGroup = g.append("g")
    .attr("class", "x-axis")
    .attr("transform", `translate(0,${innerHeight})`);
    
  xAxisGroup.call(d3.axisBottom(xScale)
    .tickValues(monthTickValues)
    .tickFormat(d => monthNames[d] || "")
    .tickSizeOuter(0)
    .tickSizeInner(-innerHeight));

  xAxisGroup.selectAll(".tick text")
    .style("font-size", `${fontSizes.xAxisTick}px`);
  
  // ========================================
  // BUBBLES
  // ========================================
  g.selectAll(".dot")
    .data(fe)
    .enter().append("circle")
    .attr("class", "dot")
    .attr("cx", d => xScale(d.begin_month))
    .attr("cy", d => yScale(d.begin_year))
    .attr("r", d => rScale(d.DISPLACED))
    .attr("fill", d => colorScale(d.severity))
    .attr("fill-opacity", 0.7)
    .attr("stroke", "black")
    .attr("stroke-width", Math.max(0.5, Math.min(2, width / 400)))
    .style("cursor", "default")
    .on("mouseover", function(event, d) {
      d3.selectAll(".d3-tooltip").remove();

      const tooltip = d3.select("body").append("div")
        .attr("class", "d3-tooltip")
        .style("opacity", 0);
        
      const html = `
        <div><strong>${d.line1}</strong></div>
        <div style="margin-top: 8px;">${d.line2}</div>
        <div style="margin-top: 4px;">${d.line3}</div>
      `;
      
      const tooltipWidth = 280;
      const windowWidth = window.innerWidth;
      const mouseX = event.pageX;
      
      let leftPos = mouseX + 10;
      if (leftPos + tooltipWidth > windowWidth) {
        leftPos = mouseX - tooltipWidth - 10;
      }
      
      tooltip
        .html(html)
        .style("left", leftPos + "px")
        .style("top", (event.pageY - 35) + "px")
        .transition()
        .duration(200)
        .style("opacity", 1);
    })
    .on("mousemove", function(event) {
      const tooltip = d3.select(".d3-tooltip");
      if (!tooltip.empty()) {
        const tooltipWidth = 280;
        const windowWidth = window.innerWidth;
        const mouseX = event.pageX;
        
        let leftPos = mouseX + 10;
        if (leftPos + tooltipWidth > windowWidth) {
          leftPos = mouseX - tooltipWidth - 10;
        }
        
        tooltip
          .style("left", leftPos + "px")
          .style("top", (event.pageY - 35) + "px");
      }
    })
    .on("mouseout", function() {
      d3.select(".d3-tooltip")
        .transition()
        .duration(200)
        .style("opacity", 0)
        .remove();
    });
  
  // ========================================
  // LEGEND
  // ========================================
  const legendData = [
    { label: "Large event", color: "#87CEEB", shape: "circle" },
    { label: "Very large event", color: "#000080", shape: "circle" }
  ];
  
  PlotHelpers.addLegend(svg, legendData, width, height, 'top-right');
  
  // ========================================
  // TITLE
  // ========================================
  const heightScale = height / PlotHelpers.PLOT_BASE.HEIGHT;
  const titleY = PlotHelpers.getTitleY(height, heightScale);
  
  titleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-title")
      .attr("x", 20)
      .attr("y", titleY + (i * lineHeights.title))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.title}px`)
      .text(line);
  });
    
  // ========================================
  // SUBTITLE
  // ========================================
  const subtitleY = PlotHelpers.getSubtitleY(titleY, titleLines.length, lineHeights.title, heightScale);
  
  subtitleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-subtitle")
      .attr("x", 20)
      .attr("y", subtitleY + (i * lineHeights.subtitle))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.subtitle}px`)
      .text(line);
  });
    
  // ========================================
  // Y-AXIS LABEL
  // ========================================
  const widthScale = width / PlotHelpers.PLOT_BASE.WIDTH;
  const yAxisLabelX = -(margin.top + innerHeight/2);
  const yAxisLabelY = PlotHelpers.getYAxisLabelY(widthScale);
  
  yAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("transform", "rotate(-90)")
      .attr("y", yAxisLabelY + (i * lineHeights.axisLabel))
      .attr("x", yAxisLabelX)
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // X-AXIS LABEL
  // ========================================
  const xAxisLabelX = margin.left + innerWidth/2;
  const xAxisLabelY = PlotHelpers.getXAxisLabelY(height, captionHeight, heightScale);
  
  xAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("x", xAxisLabelX)
      .attr("y", xAxisLabelY - ((xAxisLabelLines.length - 1 - i) * lineHeights.axisLabel))
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // CAPTION
  // ========================================
  // (empty for this plot)
  if (captionText) {
    const captionY = PlotHelpers.getCaptionY(height, heightScale);
    
    captionLines.forEach((line, i) => {
      svg.append("text")
        .attr("class", "plot-caption")
        .attr("x", 20)
        .attr("y", captionY - ((captionLines.length - 1 - i) * lineHeights.caption))
        .attr("text-anchor", "start")
        .style("font-size", `${fontSizes.caption}px`)
        .text(line);
    });
  }
  
  return svg.node();
}


// ------------------------------------------------------------
// plot_flood_prob - Multi-line flood charts by probability (matching plot_pu style)
// ------------------------------------------------------------
function plot_flood_prob(data, {
  cityName = globalCity,
  countryName = globalCountry,
  width,
  height,
  floodType = "Flooding"   // e.g. "Pluvial Flooding", "Fluvial Flooding", "Coastal Flooding"
} = {}) {
  
  // ========================================
  // DATA PREPARATION
  // ========================================
  if (!data || !data.length) return null;  // no data -> render nothing
  // probability bins: columns in the *_prob.csv tables; colours + dashes match the
  // flood maps (layers.yml)
  const bins = [
    { key: "1-in-1,000 year", label: "1-in-1,000 year", color: "#A7BCEE", dash: null },
    { key: "1-in-100 year",   label: "1-in-100 year",   color: "#6478D9", dash: "4,3" },
    { key: "1-in-10 year",    label: "1-in-10 year",    color: "#1B35C4", dash: "2,2" }
  ];
  // normalize: sort by calendar year; year = position (1..n), yearName = calendar year
  data = data.slice()
    .sort((a, b) => +(a.yearName ?? a.year) - +(b.yearName ?? b.year))
    .map((d, i) => {
      const row = { year: i + 1, yearName: +(d.yearName ?? d.year) };
      bins.forEach(bin => { row[bin.key] = d[bin.key] != null ? +d[bin.key] : null; });
      return row;
    });
  const maxVal = d3.max(data, d => d3.max(bins, bin => d[bin.key] ?? 0)) || 1;
  
  // get year range for title
  const minYear = d3.min(data, d => d.yearName);
  const maxYear = d3.max(data, d => d.yearName);
  
  // ========================================
  // STYLING CALCULATIONS
  // ========================================
  // (use helper functions from plot-helpers.js for all styling calculations)
  const fontSizes = PlotHelpers.calculateFontSizes(width, height);
  const lineHeights = PlotHelpers.calculateLineHeights(fontSizes);
  
  // text content
  const titleText = `Built-up Area Exposed to ${floodType}, ${minYear}-${maxYear}`;
  const titleLocation = countryName ? `${cityName}, ${countryName}` : cityName;
  const xAxisLabelText = "Year";
  const yAxisLabelText = "Exposed Urban Built-up Area (sq km)";
  const captionText = ""; // (empty for this plot)
  
  // text wrapping
  const titleLines = PlotHelpers.wrapText(titleText, width - 40, `${fontSizes.title}px system-ui`);
  const subtitleLines = PlotHelpers.wrapText(titleLocation, width - 40, `${fontSizes.subtitle}px system-ui`);
  const xAxisLabelLines = PlotHelpers.wrapText(xAxisLabelText, width * 0.8, `${fontSizes.axisLabel}px system-ui`);
  const yAxisLabelLines = PlotHelpers.wrapText(yAxisLabelText, height * 0.6, `${fontSizes.axisLabel}px system-ui`);
  const captionLines = PlotHelpers.wrapText(captionText, width - 40, `${fontSizes.caption}px system-ui`);

  // calculate text dimensions for margins
  const titleHeight = titleLines.length * lineHeights.title;
  const subtitleHeight = subtitleLines.length * lineHeights.subtitle;
  const xAxisLabelHeight = xAxisLabelLines.length * lineHeights.axisLabel;
  const captionHeight = captionLines.length * lineHeights.caption;
  const yAxisLabelWidth = yAxisLabelLines.length * lineHeights.axisLabel;

  // calculate margins using helper
  const margin = PlotHelpers.calculateMargins(width, height, {
    titleHeight,
    subtitleHeight,
    xAxisLabelHeight,
    captionHeight,
    yAxisLabelWidth
  });
  
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  
  // ========================================
  // SCALES
  // ========================================
  const xScale = d3.scaleLinear()
    .domain([1, data.length])
    .range([0, innerWidth]);
    
  const yScale = d3.scaleLinear()
    .domain([0, maxVal * 1.2])
    .range([innerHeight, 0]);

  // ========================================
  // SVG CREATION
  // ========================================
  const svg = d3.create("svg")
    .attr("viewBox", `0 0 ${width} ${height}`)
    .attr("preserveAspectRatio", "xMidYMid meet")
    .style("width", "100%")
    .style("height", "auto")
    .style("max-width", `${width}px`);

  const g = svg.append("g")
    .attr("transform", `translate(${margin.left},${margin.top})`);
  
  // ========================================
  // Y-AXIS
  // ========================================
  const yTicks = PlotHelpers.calculateYTicks(innerHeight);
  const yAxisGroup = g.append("g").attr("class", "y-axis");
  const yAxisCall = d3.axisLeft(yScale)
    .ticks(yTicks)
    .tickSizeOuter(0)
    .tickSizeInner(-innerWidth)
    .tickFormat(d => d === 0 ? "0" : (d < 1 ? d.toFixed(2) : d));  // small decimals; plain 0 (team fix)

  yAxisGroup.call(yAxisCall);
  yAxisGroup.selectAll(".tick text")
    .style("font-size", `${fontSizes.yAxisTick}px`);
  
  // ========================================
  // X-AXIS
  // ========================================
  const xAxisGroup = g.append("g")
    .attr("class", "x-axis")
    .attr("transform", `translate(0,${innerHeight})`);
    
  xAxisGroup.call(d3.axisBottom(xScale)
    .ticks(Math.max(5, Math.min(15, Math.floor(width / 80))))
    .tickFormat(d => {
      const index = Math.round(d) - 1;
      return index >= 0 && index < data.length ? d3.format("d")(data[index].yearName) : "";
    })
    .tickSizeOuter(0)
    .tickSizeInner(-innerHeight));

  xAxisGroup.selectAll(".tick text")
    .style("font-size", `${fontSizes.xAxisTick}px`);
  
  // ========================================
  // LINES
  // ========================================
  const dashArray = `${Math.max(2, Math.min(6, width / 200))},${Math.max(2, Math.min(6, width / 200))}`;
  const strokeWidth = Math.max(1.5, Math.min(3, width / 400));
  
  // one line per return period; split at 2015/2016 (built-up data source change)
  const _seg = arr => [arr.filter(d => d.yearName <= 2015), arr.filter(d => d.yearName >= 2016)];
  bins.forEach(bin => {
    const lineFn = d3.line()
      .defined(d => d[bin.key] !== null)
      .x(d => xScale(d.year))
      .y(d => yScale(d[bin.key]));
    _seg(data).forEach(segment => {
      if (segment.length === 0) return;
      g.append("path")
        .datum(segment)
        .attr("fill", "none")
        .attr("stroke", bin.color)
        .attr("stroke-width", strokeWidth)
        .attr("stroke-dasharray", bin.dash)
        .attr("d", lineFn);
    });
  });
  
  // ========================================
  // INTERACTION AREA (INVISIBLE)
  // ========================================
  // (invisible interaction areas for tooltips)
  g.selectAll(".interaction-area")
    .data(data)
    .enter().append("rect")
    .attr("class", "interaction-area")
    .attr("x", d => xScale(d.year) - 5)
    .attr("y", 0)
    .attr("width", 10)
    .attr("height", innerHeight)
    .attr("fill", "transparent")
    .style("cursor", "default")
    .on("mouseover", function(event, d) {
      d3.selectAll(".d3-tooltip").remove();
      

      const tooltip = d3.select("body").append("div")
        .attr("class", "d3-tooltip")
        .style("opacity", 0);
        
      const html = `<div><strong>Year: ${d.yearName}</strong></div><div>━━━━━━━━━━━━</div>` + bins.map(bin => `<div>${bin.label}: ${d[bin.key] != null ? d[bin.key].toFixed(1) : "–"} sq km</div>`).join("");
      
      const tooltipWidth = 220;
      const windowWidth = window.innerWidth;
      const mouseX = event.pageX;
      
      let leftPos = mouseX + 10;
      if (leftPos + tooltipWidth > windowWidth) {
        leftPos = mouseX - tooltipWidth - 10;
      }
      
      tooltip
        .html(html)
        .style("left", leftPos + "px")
        .style("top", (event.pageY - 35) + "px")
        .transition()
        .duration(200)
        .style("opacity", 1);
    })
    .on("mousemove", function(event) {
      const tooltip = d3.select(".d3-tooltip");
      if (!tooltip.empty()) {
        const tooltipWidth = 220;
        const windowWidth = window.innerWidth;
        const mouseX = event.pageX;
        
        let leftPos = mouseX + 10;
        if (leftPos + tooltipWidth > windowWidth) {
          leftPos = mouseX - tooltipWidth - 10;
        }
        
        tooltip
          .style("left", leftPos + "px")
          .style("top", (event.pageY - 35) + "px");
      }
    })
    .on("mouseout", function() {
      d3.select(".d3-tooltip")
        .transition()
        .duration(200)
        .style("opacity", 0)
        .remove();
    });
  
  // ========================================
  // LEGEND
  // ========================================
  const legendData = bins.map(bin => ({ label: bin.label, color: bin.color, dashed: !!bin.dash }));

  PlotHelpers.addLegend(svg, legendData, width, height, 'top-right');
  // match each legend sample's dash pattern to its line (addLegend uses one dash style)
  svg.selectAll(".plot-legend line").each(function(_, i) {
    d3.select(this).attr("stroke-dasharray", bins[i] && bins[i].dash ? bins[i].dash : "0");
  });
  
  // ========================================
  // TITLE
  // ========================================
  const heightScale = height / PlotHelpers.PLOT_BASE.HEIGHT;
  const titleY = PlotHelpers.getTitleY(height, heightScale);
  
  titleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-title")
      .attr("x", 20)
      .attr("y", titleY + (i * lineHeights.title))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.title}px`)
      .text(line);
  });
    
  // ========================================
  // SUBTITLE
  // ========================================
  const subtitleY = PlotHelpers.getSubtitleY(titleY, titleLines.length, lineHeights.title, heightScale);
  
  subtitleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-subtitle")
      .attr("x", 20)
      .attr("y", subtitleY + (i * lineHeights.subtitle))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.subtitle}px`)
      .text(line);
  });
    
  // ========================================
  // Y-AXIS LABEL
  // ========================================
  const widthScale = width / PlotHelpers.PLOT_BASE.WIDTH;
  const yAxisLabelX = -(margin.top + innerHeight/2);
  const yAxisLabelY = PlotHelpers.getYAxisLabelY(widthScale);
  
  yAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("transform", "rotate(-90)")
      .attr("y", yAxisLabelY + (i * lineHeights.axisLabel))
      .attr("x", yAxisLabelX)
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // X-AXIS LABEL
  // ========================================
  const xAxisLabelX = margin.left + innerWidth/2;
  const xAxisLabelY = PlotHelpers.getXAxisLabelY(height, captionHeight, heightScale);
  
  xAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("x", xAxisLabelX)
      .attr("y", xAxisLabelY - ((xAxisLabelLines.length - 1 - i) * lineHeights.axisLabel))
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // CAPTION
  // ========================================
  // (empty for this plot)
  if (captionText) {
    const captionY = PlotHelpers.getCaptionY(height, heightScale);
    
    captionLines.forEach((line, i) => {
      svg.append("text")
        .attr("class", "plot-caption")
        .attr("x", 20)
        .attr("y", captionY - ((captionLines.length - 1 - i) * lineHeights.caption))
        .attr("text-anchor", "start")
        .style("font-size", `${fontSizes.caption}px`)
        .text(line);
    });
  }
  
  return svg.node();
}


// ------------------------------------------------------------
// plot_fu
// ------------------------------------------------------------
function plot_fu(fu, {
  cityName = globalCity,
  countryName = globalCountry,
  width,
  height
} = {}) {
  
  // ========================================
  // DATA PREPARATION
  // ========================================
  // ensure fu is a number
  if (!fu || !fu.length) return null;  // no data -> render nothing (team fix)
  // normalize: the CSV has year (calendar) + exposed_km2; this chart reads year
  // (position 1..n), yearName (calendar year) and fu (value) (team fix)
  fu = fu.slice()
    .sort((a, b) => +(a.yearName ?? a.year) - +(b.yearName ?? b.year))
    .map((d, i) => ({ year: i + 1,
                      yearName: +(d.yearName ?? d.year),
                      fu: d.fu != null ? +d.fu : +(d.exposed_km2 ?? 0) }));
  
  // get year range for title
  const minYear = d3.min(fu, d => d.yearName);
  const maxYear = d3.max(fu, d => d.yearName);
  
  // ========================================
  // STYLING CALCULATIONS
  // ========================================
  // (use helper functions from plot-helpers.js for all styling calculations)
  const fontSizes = PlotHelpers.calculateFontSizes(width, height);
  const lineHeights = PlotHelpers.calculateLineHeights(fontSizes);
  
  // text content
  const titleText = `Built-up Area Exposed to Fluvial Flooding, ${minYear}-${maxYear}`;
  const titleLocation = countryName ? `${cityName}, ${countryName}` : cityName;
  const xAxisLabelText = "Year";
  const yAxisLabelText = "Exposed Urban Built-up Area (sq km)";
  const captionText = ""; // (empty for this plot)
  
  // text wrapping
  const titleLines = PlotHelpers.wrapText(titleText, width - 40, `${fontSizes.title}px system-ui`);
  const subtitleLines = PlotHelpers.wrapText(titleLocation, width - 40, `${fontSizes.subtitle}px system-ui`);
  const xAxisLabelLines = PlotHelpers.wrapText(xAxisLabelText, width * 0.8, `${fontSizes.axisLabel}px system-ui`);
  const yAxisLabelLines = PlotHelpers.wrapText(yAxisLabelText, height * 0.6, `${fontSizes.axisLabel}px system-ui`);
  const captionLines = PlotHelpers.wrapText(captionText, width - 40, `${fontSizes.caption}px system-ui`);

  // calculate text dimensions for margins
  const titleHeight = titleLines.length * lineHeights.title;
  const subtitleHeight = subtitleLines.length * lineHeights.subtitle;
  const xAxisLabelHeight = xAxisLabelLines.length * lineHeights.axisLabel;
  const captionHeight = captionLines.length * lineHeights.caption;
  const yAxisLabelWidth = yAxisLabelLines.length * lineHeights.axisLabel;

  // calculate margins using helper
  const margin = PlotHelpers.calculateMargins(width, height, {
    titleHeight,
    subtitleHeight,
    xAxisLabelHeight,
    captionHeight,
    yAxisLabelWidth
  });
  
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  
  // ========================================
  // SCALES
  // ========================================
  const xScale = d3.scaleLinear()
    .domain([1, fu.length])
    .range([0, innerWidth]);
    
  const yScale = d3.scaleLinear()
    .domain([0, Math.max(...fu.map(d => d.fu)) * 1.2])
    .range([innerHeight, 0]);

  // ========================================
  // SVG CREATION
  // ========================================
  const svg = d3.create("svg")
    .attr("viewBox", `0 0 ${width} ${height}`)
    .attr("preserveAspectRatio", "xMidYMid meet")
    .style("width", "100%")
    .style("height", "auto")
    .style("max-width", `${width}px`);

  const g = svg.append("g")
    .attr("transform", `translate(${margin.left},${margin.top})`);
  
  // ========================================
  // Y-AXIS
  // ========================================
  const yTicks = PlotHelpers.calculateYTicks(innerHeight);
  const yAxisGroup = g.append("g").attr("class", "y-axis");
  const yAxisCall = d3.axisLeft(yScale)
    .ticks(yTicks)
    .tickSizeOuter(0)
    .tickSizeInner(-innerWidth)
    .tickFormat(d => d === 0 ? "0" : (d < 1 ? d.toFixed(2) : d));  // small decimals; plain 0 (team fix)

  yAxisGroup.call(yAxisCall);
  yAxisGroup.selectAll(".tick text")
    .style("font-size", `${fontSizes.yAxisTick}px`);
  
  // ========================================
  // X-AXIS
  // ========================================
  const xAxisGroup = g.append("g")
    .attr("class", "x-axis")
    .attr("transform", `translate(0,${innerHeight})`);
    
  xAxisGroup.call(d3.axisBottom(xScale)
    .ticks(Math.max(5, Math.min(15, Math.floor(width / 80))))
    .tickFormat(d => {
      const index = Math.round(d) - 1;
      return index >= 0 && index < fu.length ? d3.format("d")(fu[index].yearName) : "";
    })
    .tickSizeOuter(0)
    .tickSizeInner(-innerHeight));

  xAxisGroup.selectAll(".tick text")
    .style("font-size", `${fontSizes.xAxisTick}px`);
  
  // ========================================
  // LINE
  // ========================================
  const line = d3.line()
    .defined(d => d.fu !== null)
    .x(d => xScale(d.year))
    .y(d => yScale(d.fu));
    
  // split at 2015/2016: the built-up data source changes there, so don't join them (team fix)
  [fu.filter(d => d.yearName <= 2015), fu.filter(d => d.yearName >= 2016)].forEach(segment => {
    if (segment.length === 0) return;
    g.append("path")
      .datum(segment)
      .attr("fill", "none")
      .attr("stroke", "black")
      .attr("stroke-width", Math.max(1.5, Math.min(3, width / 400)))
      .attr("d", line);
  });
  
  // ========================================
  // INVISIBLE DOTS
  // ========================================
  g.selectAll(".dot")
    .data(fu.filter(d => d.fu !== null))
    .enter().append("circle")
    .attr("class", "dot")
    .attr("cx", d => xScale(d.year))
    .attr("cy", d => yScale(d.fu))
    .attr("r", 4)
    .attr("fill", "transparent")
    .style("cursor", "default")
    .on("mouseover", function(event, d) {
      d3.selectAll(".d3-tooltip").remove();

      const tooltip = d3.select("body").append("div")
        .attr("class", "d3-tooltip")
        .style("opacity", 0);
        
      const html = `<div>Year: ${d.yearName}</div><div>${yAxisLabelText}: ${d.fu.toLocaleString()}</div>`;
      
      const tooltipWidth = 280;
      const windowWidth = window.innerWidth;
      const mouseX = event.pageX;
      
      let leftPos = mouseX + 10;
      if (leftPos + tooltipWidth > windowWidth) {
        leftPos = mouseX - tooltipWidth - 10;
      }
      
      tooltip
        .html(html)
        .style("left", leftPos + "px")
        .style("top", (event.pageY - 35) + "px")
        .transition()
        .duration(200)
        .style("opacity", 1);
    })
    .on("mousemove", function(event) {
      const tooltip = d3.select(".d3-tooltip");
      if (!tooltip.empty()) {
        const tooltipWidth = 280;
        const windowWidth = window.innerWidth;
        const mouseX = event.pageX;
        
        let leftPos = mouseX + 10;
        if (leftPos + tooltipWidth > windowWidth) {
          leftPos = mouseX - tooltipWidth - 10;
        }
        
        tooltip
          .style("left", leftPos + "px")
          .style("top", (event.pageY - 35) + "px");
      }
    })
    .on("mouseout", function() {
      d3.select(".d3-tooltip")
        .transition()
        .duration(200)
        .style("opacity", 0)
        .remove();
    });
  
  // ========================================
  // TITLE
  // ========================================
  const heightScale = height / PlotHelpers.PLOT_BASE.HEIGHT;
  const titleY = PlotHelpers.getTitleY(height, heightScale);
  
  titleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-title")
      .attr("x", 20)
      .attr("y", titleY + (i * lineHeights.title))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.title}px`)
      .text(line);
  });
    
  // ========================================
  // SUBTITLE
  // ========================================
  const subtitleY = PlotHelpers.getSubtitleY(titleY, titleLines.length, lineHeights.title, heightScale);
  
  subtitleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-subtitle")
      .attr("x", 20)
      .attr("y", subtitleY + (i * lineHeights.subtitle))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.subtitle}px`)
      .text(line);
  });
    
  // ========================================
  // Y-AXIS LABEL
  // ========================================
  const widthScale = width / PlotHelpers.PLOT_BASE.WIDTH;
  const yAxisLabelX = -(margin.top + innerHeight/2);
  const yAxisLabelY = PlotHelpers.getYAxisLabelY(widthScale);
  
  yAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("transform", "rotate(-90)")
      .attr("y", yAxisLabelY + (i * lineHeights.axisLabel))
      .attr("x", yAxisLabelX)
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // X-AXIS LABEL
  // ========================================
  const xAxisLabelX = margin.left + innerWidth/2;
  const xAxisLabelY = PlotHelpers.getXAxisLabelY(height, captionHeight, heightScale);
  
  xAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("x", xAxisLabelX)
      .attr("y", xAxisLabelY - ((xAxisLabelLines.length - 1 - i) * lineHeights.axisLabel))
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // CAPTION
  // ========================================
  // (empty for this plot)
  if (captionText) {
    const captionY = PlotHelpers.getCaptionY(height, heightScale);
    
    captionLines.forEach((line, i) => {
      svg.append("text")
        .attr("class", "plot-caption")
        .attr("x", 20)
        .attr("y", captionY - ((captionLines.length - 1 - i) * lineHeights.caption))
        .attr("text-anchor", "start")
        .style("font-size", `${fontSizes.caption}px`)
        .text(line);
    });
  }
  
  return svg.node();
}


// ------------------------------------------------------------
// plot_pu
// ------------------------------------------------------------
function plot_pu(pu, {
  cityName = globalCity,
  countryName = globalCountry,
  width,
  height
} = {}) {
  
  // ========================================
  // DATA PREPARATION
  // ========================================
  // ensure pu is a number
  if (!pu || !pu.length) return null;  // no data -> render nothing (team fix)
  // normalize: the CSV has year (calendar) + exposed_km2; this chart reads year
  // (position 1..n), yearName (calendar year) and pu (value) (team fix)
  pu = pu.slice()
    .sort((a, b) => +(a.yearName ?? a.year) - +(b.yearName ?? b.year))
    .map((d, i) => ({ year: i + 1,
                      yearName: +(d.yearName ?? d.year),
                      pu: d.pu != null ? +d.pu : +(d.exposed_km2 ?? 0) }));
  
  // get year range for title
  const minYear = d3.min(pu, d => d.yearName);
  const maxYear = d3.max(pu, d => d.yearName);
  
  // ========================================
  // STYLING CALCULATIONS
  // ========================================
  // (use helper functions from plot-helpers.js for all styling calculations)
  const fontSizes = PlotHelpers.calculateFontSizes(width, height);
  const lineHeights = PlotHelpers.calculateLineHeights(fontSizes);
  
  // text content
  const titleText = `Built-up Area Exposed to Pluvial Flooding, ${minYear}-${maxYear}`;
  const titleLocation = countryName ? `${cityName}, ${countryName}` : cityName;
  const xAxisLabelText = "Year";
  const yAxisLabelText = "Exposed Urban Built-up Area (sq km)";
  const captionText = ""; // (empty for this plot)
  
  // text wrapping
  const titleLines = PlotHelpers.wrapText(titleText, width - 40, `${fontSizes.title}px system-ui`);
  const subtitleLines = PlotHelpers.wrapText(titleLocation, width - 40, `${fontSizes.subtitle}px system-ui`);
  const xAxisLabelLines = PlotHelpers.wrapText(xAxisLabelText, width * 0.8, `${fontSizes.axisLabel}px system-ui`);
  const yAxisLabelLines = PlotHelpers.wrapText(yAxisLabelText, height * 0.6, `${fontSizes.axisLabel}px system-ui`);
  const captionLines = PlotHelpers.wrapText(captionText, width - 40, `${fontSizes.caption}px system-ui`);

  // calculate text dimensions for margins
  const titleHeight = titleLines.length * lineHeights.title;
  const subtitleHeight = subtitleLines.length * lineHeights.subtitle;
  const xAxisLabelHeight = xAxisLabelLines.length * lineHeights.axisLabel;
  const captionHeight = captionLines.length * lineHeights.caption;
  const yAxisLabelWidth = yAxisLabelLines.length * lineHeights.axisLabel;

  // calculate margins using helper
  const margin = PlotHelpers.calculateMargins(width, height, {
    titleHeight,
    subtitleHeight,
    xAxisLabelHeight,
    captionHeight,
    yAxisLabelWidth
  });
  
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  
  // ========================================
  // SCALES
  // ========================================
  const xScale = d3.scaleLinear()
    .domain([1, pu.length])
    .range([0, innerWidth]);
    
  const yScale = d3.scaleLinear()
    .domain([0, Math.max(...pu.map(d => d.pu)) * 1.2])
    .range([innerHeight, 0]);

  // ========================================
  // SVG CREATION
  // ========================================
  const svg = d3.create("svg")
    .attr("viewBox", `0 0 ${width} ${height}`)
    .attr("preserveAspectRatio", "xMidYMid meet")
    .style("width", "100%")
    .style("height", "auto")
    .style("max-width", `${width}px`);

  const g = svg.append("g")
    .attr("transform", `translate(${margin.left},${margin.top})`);
  
  // ========================================
  // Y-AXIS
  // ========================================
  const yTicks = PlotHelpers.calculateYTicks(innerHeight);
  const yAxisGroup = g.append("g").attr("class", "y-axis");
  const yAxisCall = d3.axisLeft(yScale)
    .ticks(yTicks)
    .tickSizeOuter(0)
    .tickSizeInner(-innerWidth)
    .tickFormat(d => d === 0 ? "0" : (d < 1 ? d.toFixed(2) : d));  // small decimals; plain 0 (team fix)

  yAxisGroup.call(yAxisCall);
  yAxisGroup.selectAll(".tick text")
    .style("font-size", `${fontSizes.yAxisTick}px`);
  
  // ========================================
  // X-AXIS
  // ========================================
  const xAxisGroup = g.append("g")
    .attr("class", "x-axis")
    .attr("transform", `translate(0,${innerHeight})`);
    
  xAxisGroup.call(d3.axisBottom(xScale)
    .ticks(Math.max(5, Math.min(15, Math.floor(width / 80))))
    .tickFormat(d => {
      const index = Math.round(d) - 1;
      return index >= 0 && index < pu.length ? d3.format("d")(pu[index].yearName) : "";
    })
    .tickSizeOuter(0)
    .tickSizeInner(-innerHeight));

  xAxisGroup.selectAll(".tick text")
    .style("font-size", `${fontSizes.xAxisTick}px`);
  
  // ========================================
  // LINE
  // ========================================
  const line = d3.line()
    .defined(d => d.pu !== null)
    .x(d => xScale(d.year))
    .y(d => yScale(d.pu));
    
  // split at 2015/2016: the built-up data source changes there, so don't join them (team fix)
  [pu.filter(d => d.yearName <= 2015), pu.filter(d => d.yearName >= 2016)].forEach(segment => {
    if (segment.length === 0) return;
    g.append("path")
      .datum(segment)
      .attr("fill", "none")
      .attr("stroke", "black")
      .attr("stroke-width", Math.max(1.5, Math.min(3, width / 400)))
      .attr("d", line);
  });
  
  // ========================================
  // DOTS (INVISIBLE)
  // ========================================
  // (invisible dots for tooltips)
  g.selectAll(".dot")
    .data(pu.filter(d => d.pu !== null))
    .enter().append("circle")
    .attr("class", "dot")
    .attr("cx", d => xScale(d.year))
    .attr("cy", d => yScale(d.pu))
    .attr("r", 4)
    .attr("fill", "transparent")
    .style("cursor", "default")
    .on("mouseover", function(event, d) {
      d3.selectAll(".d3-tooltip").remove();

      const tooltip = d3.select("body").append("div")
        .attr("class", "d3-tooltip")
        .style("opacity", 0);
        
      const html = `<div>Year: ${d.yearName}</div><div>${yAxisLabelText}: ${d.pu.toLocaleString()}</div>`;
      
      const tooltipWidth = 280;
      const windowWidth = window.innerWidth;
      const mouseX = event.pageX;
      
      let leftPos = mouseX + 10;
      if (leftPos + tooltipWidth > windowWidth) {
        leftPos = mouseX - tooltipWidth - 10;
      }
      
      tooltip
        .html(html)
        .style("left", leftPos + "px")
        .style("top", (event.pageY - 35) + "px")
        .transition()
        .duration(200)
        .style("opacity", 1);
    })
    .on("mousemove", function(event) {
      const tooltip = d3.select(".d3-tooltip");
      if (!tooltip.empty()) {
        const tooltipWidth = 280;
        const windowWidth = window.innerWidth;
        const mouseX = event.pageX;
        
        let leftPos = mouseX + 10;
        if (leftPos + tooltipWidth > windowWidth) {
          leftPos = mouseX - tooltipWidth - 10;
        }
        
        tooltip
          .style("left", leftPos + "px")
          .style("top", (event.pageY - 35) + "px");
      }
    })
    .on("mouseout", function() {
      d3.select(".d3-tooltip")
        .transition()
        .duration(200)
        .style("opacity", 0)
        .remove();
    });
  
  // ========================================
  // TITLE
  // ========================================
  const heightScale = height / PlotHelpers.PLOT_BASE.HEIGHT;
  const titleY = PlotHelpers.getTitleY(height, heightScale);
  
  titleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-title")
      .attr("x", 20)
      .attr("y", titleY + (i * lineHeights.title))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.title}px`)
      .text(line);
  });
    
  // ========================================
  // SUBTITLE
  // ========================================
  const subtitleY = PlotHelpers.getSubtitleY(titleY, titleLines.length, lineHeights.title, heightScale);
  
  subtitleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-subtitle")
      .attr("x", 20)
      .attr("y", subtitleY + (i * lineHeights.subtitle))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.subtitle}px`)
      .text(line);
  });
    
  // ========================================
  // Y-AXIS LABEL
  // ========================================
  const widthScale = width / PlotHelpers.PLOT_BASE.WIDTH;
  const yAxisLabelX = -(margin.top + innerHeight/2);
  const yAxisLabelY = PlotHelpers.getYAxisLabelY(widthScale);
  
  yAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("transform", "rotate(-90)")
      .attr("y", yAxisLabelY + (i * lineHeights.axisLabel))
      .attr("x", yAxisLabelX)
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // X-AXIS LABEL
  // ========================================
  const xAxisLabelX = margin.left + innerWidth/2;
  const xAxisLabelY = PlotHelpers.getXAxisLabelY(height, captionHeight, heightScale);
  
  xAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("x", xAxisLabelX)
      .attr("y", xAxisLabelY - ((xAxisLabelLines.length - 1 - i) * lineHeights.axisLabel))
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // CAPTION
  // ========================================
  // (empty for this plot)
  if (captionText) {
    const captionY = PlotHelpers.getCaptionY(height, heightScale);
    
    captionLines.forEach((line, i) => {
      svg.append("text")
        .attr("class", "plot-caption")
        .attr("x", 20)
        .attr("y", captionY - ((captionLines.length - 1 - i) * lineHeights.caption))
        .attr("text-anchor", "start")
        .style("font-size", `${fontSizes.caption}px`)
        .text(line);
    });
  }
  
  return svg.node();
}


// ------------------------------------------------------------
// plot_cu
// ------------------------------------------------------------
function plot_cu(cu, {
  cityName = globalCity,
  countryName = globalCountry,
  width,
  height
} = {}) {
  
  // ========================================
  // DATA PREPARATION
  // ========================================
  // ensure cu is a number
  if (!cu || !cu.length) return null;  // no data -> render nothing (team fix)
  // normalize: the CSV has year (calendar) + exposed_km2; this chart reads year
  // (position 1..n), yearName (calendar year) and cu (value) (team fix)
  cu = cu.slice()
    .sort((a, b) => +(a.yearName ?? a.year) - +(b.yearName ?? b.year))
    .map((d, i) => ({ year: i + 1,
                      yearName: +(d.yearName ?? d.year),
                      cu: d.cu != null ? +d.cu : +(d.exposed_km2 ?? 0) }));
  
  // get year range for title
  const minYear = d3.min(cu, d => d.yearName);
  const maxYear = d3.max(cu, d => d.yearName);
  
  // ========================================
  // STYLING CALCULATIONS
  // ========================================
  // (use helper functions from plot-helpers.js for all styling calculations)
  const fontSizes = PlotHelpers.calculateFontSizes(width, height);
  const lineHeights = PlotHelpers.calculateLineHeights(fontSizes);
  
  // text content
  const titleText = `Built-up Area Exposed to Coastal Flooding, ${minYear}-${maxYear}`;
  const titleLocation = countryName ? `${cityName}, ${countryName}` : cityName;
  const xAxisLabelText = "Year";
  const yAxisLabelText = "Exposed Urban Built-up Area (sq km)";
  const captionText = ""; // (empty for this plot)
  
  // text wrapping
  const titleLines = PlotHelpers.wrapText(titleText, width - 40, `${fontSizes.title}px system-ui`);
  const subtitleLines = PlotHelpers.wrapText(titleLocation, width - 40, `${fontSizes.subtitle}px system-ui`);
  const xAxisLabelLines = PlotHelpers.wrapText(xAxisLabelText, width * 0.8, `${fontSizes.axisLabel}px system-ui`);
  const yAxisLabelLines = PlotHelpers.wrapText(yAxisLabelText, height * 0.6, `${fontSizes.axisLabel}px system-ui`);
  const captionLines = PlotHelpers.wrapText(captionText, width - 40, `${fontSizes.caption}px system-ui`);

  // calculate text dimensions for margins
  const titleHeight = titleLines.length * lineHeights.title;
  const subtitleHeight = subtitleLines.length * lineHeights.subtitle;
  const xAxisLabelHeight = xAxisLabelLines.length * lineHeights.axisLabel;
  const captionHeight = captionLines.length * lineHeights.caption;
  const yAxisLabelWidth = yAxisLabelLines.length * lineHeights.axisLabel;

  // calculate margins using helper
  const margin = PlotHelpers.calculateMargins(width, height, {
    titleHeight,
    subtitleHeight,
    xAxisLabelHeight,
    captionHeight,
    yAxisLabelWidth
  });
  
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  
  // ========================================
  // SCALES
  // ========================================
  const xScale = d3.scaleLinear()
    .domain([1, cu.length])
    .range([0, innerWidth]);
    
  const yScale = d3.scaleLinear()
    .domain([0, Math.max(...cu.map(d => d.cu)) * 1.2])
    .range([innerHeight, 0]);

  // ========================================
  // SVG CREATION
  // ========================================
  const svg = d3.create("svg")
    .attr("viewBox", `0 0 ${width} ${height}`)
    .attr("preserveAspectRatio", "xMidYMid meet")
    .style("width", "100%")
    .style("height", "auto")
    .style("max-width", `${width}px`);

  const g = svg.append("g")
    .attr("transform", `translate(${margin.left},${margin.top})`);
  
  // ========================================
  // Y-AXIS
  // ========================================
  const yTicks = PlotHelpers.calculateYTicks(innerHeight);
  const yAxisGroup = g.append("g").attr("class", "y-axis");
  const yAxisCall = d3.axisLeft(yScale)
    .ticks(yTicks)
    .tickSizeOuter(0)
    .tickSizeInner(-innerWidth)
    .tickFormat(d => d === 0 ? "0" : (d < 1 ? d.toFixed(2) : d));  // small decimals; plain 0 (team fix)

  yAxisGroup.call(yAxisCall);
  yAxisGroup.selectAll(".tick text")
    .style("font-size", `${fontSizes.yAxisTick}px`);
  
  // ========================================
  // X-AXIS
  // ========================================
  const xAxisGroup = g.append("g")
    .attr("class", "x-axis")
    .attr("transform", `translate(0,${innerHeight})`);
    
  xAxisGroup.call(d3.axisBottom(xScale)
    .ticks(Math.max(5, Math.min(15, Math.floor(width / 80))))
    .tickFormat(d => {
      const index = Math.round(d) - 1;
      return index >= 0 && index < cu.length ? d3.format("d")(cu[index].yearName) : "";
    })
    .tickSizeOuter(0)
    .tickSizeInner(-innerHeight));

  xAxisGroup.selectAll(".tick text")
    .style("font-size", `${fontSizes.xAxisTick}px`);
  
  // ========================================
  // LINE
  // ========================================
  const line = d3.line()
    .defined(d => d.cu !== null)
    .x(d => xScale(d.year))
    .y(d => yScale(d.cu));
    
  // split at 2015/2016: the built-up data source changes there, so don't join them (team fix)
  [cu.filter(d => d.yearName <= 2015), cu.filter(d => d.yearName >= 2016)].forEach(segment => {
    if (segment.length === 0) return;
    g.append("path")
      .datum(segment)
      .attr("fill", "none")
      .attr("stroke", "black")
      .attr("stroke-width", Math.max(1.5, Math.min(3, width / 400)))
      .attr("d", line);
  });
  
  // ========================================
  // DOTS (INVISIBLE)
  // ========================================
  // (invisible dots for tooltips)
  g.selectAll(".dot")
    .data(cu.filter(d => d.cu !== null))
    .enter().append("circle")
    .attr("class", "dot")
    .attr("cx", d => xScale(d.year))
    .attr("cy", d => yScale(d.cu))
    .attr("r", 4)
    .attr("fill", "transparent")
    .style("cursor", "default")
    .on("mouseover", function(event, d) {
      d3.selectAll(".d3-tooltip").remove();

      const tooltip = d3.select("body").append("div")
        .attr("class", "d3-tooltip")
        .style("opacity", 0);
        
      const html = `<div>Year: ${d.yearName}</div><div>${yAxisLabelText}: ${d.cu.toLocaleString()}</div>`;
      
      const tooltipWidth = 280;
      const windowWidth = window.innerWidth;
      const mouseX = event.pageX;
      
      let leftPos = mouseX + 10;
      if (leftPos + tooltipWidth > windowWidth) {
        leftPos = mouseX - tooltipWidth - 10;
      }
      
      tooltip
        .html(html)
        .style("left", leftPos + "px")
        .style("top", (event.pageY - 35) + "px")
        .transition()
        .duration(200)
        .style("opacity", 1);
    })
    .on("mousemove", function(event) {
      const tooltip = d3.select(".d3-tooltip");
      if (!tooltip.empty()) {
        const tooltipWidth = 280;
        const windowWidth = window.innerWidth;
        const mouseX = event.pageX;
        
        let leftPos = mouseX + 10;
        if (leftPos + tooltipWidth > windowWidth) {
          leftPos = mouseX - tooltipWidth - 10;
        }
        
        tooltip
          .style("left", leftPos + "px")
          .style("top", (event.pageY - 35) + "px");
      }
    })
    .on("mouseout", function() {
      d3.select(".d3-tooltip")
        .transition()
        .duration(200)
        .style("opacity", 0)
        .remove();
    });
  
  // ========================================
  // TITLE
  // ========================================
  const heightScale = height / PlotHelpers.PLOT_BASE.HEIGHT;
  const titleY = PlotHelpers.getTitleY(height, heightScale);
  
  titleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-title")
      .attr("x", 20)
      .attr("y", titleY + (i * lineHeights.title))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.title}px`)
      .text(line);
  });
    
  // ========================================
  // SUBTITLE
  // ========================================
  const subtitleY = PlotHelpers.getSubtitleY(titleY, titleLines.length, lineHeights.title, heightScale);
  
  subtitleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-subtitle")
      .attr("x", 20)
      .attr("y", subtitleY + (i * lineHeights.subtitle))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.subtitle}px`)
      .text(line);
  });
    
  // ========================================
  // Y-AXIS LABEL
  // ========================================
  const widthScale = width / PlotHelpers.PLOT_BASE.WIDTH;
  const yAxisLabelX = -(margin.top + innerHeight/2);
  const yAxisLabelY = PlotHelpers.getYAxisLabelY(widthScale);
  
  yAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("transform", "rotate(-90)")
      .attr("y", yAxisLabelY + (i * lineHeights.axisLabel))
      .attr("x", yAxisLabelX)
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // X-AXIS LABEL
  // ========================================
  const xAxisLabelX = margin.left + innerWidth/2;
  const xAxisLabelY = PlotHelpers.getXAxisLabelY(height, captionHeight, heightScale);
  
  xAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("x", xAxisLabelX)
      .attr("y", xAxisLabelY - ((xAxisLabelLines.length - 1 - i) * lineHeights.axisLabel))
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // CAPTION
  // ========================================
  // (empty for this plot)
  if (captionText) {
    const captionY = PlotHelpers.getCaptionY(height, heightScale);
    
    captionLines.forEach((line, i) => {
      svg.append("text")
        .attr("class", "plot-caption")
        .attr("x", 20)
        .attr("y", captionY - ((captionLines.length - 1 - i) * lineHeights.caption))
        .attr("text-anchor", "start")
        .style("font-size", `${fontSizes.caption}px`)
        .text(line);
    });
  }
  
  return svg.node();
}


// ------------------------------------------------------------
// plot_comb
// ------------------------------------------------------------
function plot_comb(comb, pu, fu, cu, {
  cityName = globalCity,
  countryName = globalCountry,
  width,
  height
} = {}) {
  
  // ========================================
  // DATA PREPARATION
  // ========================================
  // ensure all values are numbers
  if (!comb || !comb.length) return null;  // no data -> render nothing (team fix)
  // normalize the four CSVs (year + exposed_km2) to year (position), yearName, value.
  // Line every series up with the combined series BY CALENDAR YEAR (they can have
  // different lengths, e.g. coastal 1985-2025 vs combined 1985-2015).
  const _cal = d => +(d.yearName ?? d.year);
  comb = comb.slice().sort((a, b) => _cal(a) - _cal(b))
    .map((d, i) => ({ year: i + 1, yearName: _cal(d), comb: d.comb != null ? +d.comb : +(d.exposed_km2 ?? 0) }));
  const _pos = new Map(comb.map(d => [d.yearName, d.year]));
  const _align = (arr, key) => (arr || [])
    .filter(d => _pos.has(_cal(d)))
    .map(d => ({ year: _pos.get(_cal(d)), yearName: _cal(d), [key]: d[key] != null ? +d[key] : +(d.exposed_km2 ?? 0) }))
    .sort((a, b) => a.year - b.year);
  pu = _align(pu, "pu"); fu = _align(fu, "fu"); cu = _align(cu, "cu");
  
  // get year range for title
  const minYear = d3.min(comb, d => d.yearName);
  const maxYear = d3.max(comb, d => d.yearName);
  
  // ========================================
  // STYLING CALCULATIONS
  // ========================================
  // (use helper functions from plot-helpers.js for all styling calculations)
  const fontSizes = PlotHelpers.calculateFontSizes(width, height);
  const lineHeights = PlotHelpers.calculateLineHeights(fontSizes);
  
  // text content
  const titleText = `Built-up Area Exposed to Combined Flooding, ${minYear}-${maxYear}`;
  const titleLocation = countryName ? `${cityName}, ${countryName}` : cityName;
  const xAxisLabelText = "Year";
  const yAxisLabelText = "Exposed Urban Built-up Area (sq km)";
  const captionText = ""; // (empty for this plot)
  
  // text wrapping
  const titleLines = PlotHelpers.wrapText(titleText, width - 40, `${fontSizes.title}px system-ui`);
  const subtitleLines = PlotHelpers.wrapText(titleLocation, width - 40, `${fontSizes.subtitle}px system-ui`);
  const xAxisLabelLines = PlotHelpers.wrapText(xAxisLabelText, width * 0.8, `${fontSizes.axisLabel}px system-ui`);
  const yAxisLabelLines = PlotHelpers.wrapText(yAxisLabelText, height * 0.6, `${fontSizes.axisLabel}px system-ui`);
  const captionLines = PlotHelpers.wrapText(captionText, width - 40, `${fontSizes.caption}px system-ui`);

  // calculate text dimensions for margins
  const titleHeight = titleLines.length * lineHeights.title;
  const subtitleHeight = subtitleLines.length * lineHeights.subtitle;
  const xAxisLabelHeight = xAxisLabelLines.length * lineHeights.axisLabel;
  const captionHeight = captionLines.length * lineHeights.caption;
  const yAxisLabelWidth = yAxisLabelLines.length * lineHeights.axisLabel;

  // calculate margins using helper
  const margin = PlotHelpers.calculateMargins(width, height, {
    titleHeight,
    subtitleHeight,
    xAxisLabelHeight,
    captionHeight,
    yAxisLabelWidth
  });
  
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  
  // ========================================
  // SCALES
  // ========================================
  const xScale = d3.scaleLinear()
    .domain([1, comb.length])
    .range([0, innerWidth]);
    
  const yScale = d3.scaleLinear()
    .domain([0, Math.max(...comb.map(d => d.comb)) * 1.2])
    .range([innerHeight, 0]);

  // ========================================
  // SVG CREATION
  // ========================================
  const svg = d3.create("svg")
    .attr("viewBox", `0 0 ${width} ${height}`)
    .attr("preserveAspectRatio", "xMidYMid meet")
    .style("width", "100%")
    .style("height", "auto")
    .style("max-width", `${width}px`);

  const g = svg.append("g")
    .attr("transform", `translate(${margin.left},${margin.top})`);
  
  // ========================================
  // Y-AXIS
  // ========================================
  const yTicks = PlotHelpers.calculateYTicks(innerHeight);
  const yAxisGroup = g.append("g").attr("class", "y-axis");
  const yAxisCall = d3.axisLeft(yScale)
    .ticks(yTicks)
    .tickSizeOuter(0)
    .tickSizeInner(-innerWidth)
    .tickFormat(d => d === 0 ? "0" : (d < 1 ? d.toFixed(2) : d));  // small decimals; plain 0 (team fix)

  yAxisGroup.call(yAxisCall);
  yAxisGroup.selectAll(".tick text")
    .style("font-size", `${fontSizes.yAxisTick}px`);
  
  // ========================================
  // X-AXIS
  // ========================================
  const xAxisGroup = g.append("g")
    .attr("class", "x-axis")
    .attr("transform", `translate(0,${innerHeight})`);
    
  xAxisGroup.call(d3.axisBottom(xScale)
    .ticks(Math.max(5, Math.min(15, Math.floor(width / 80))))
    .tickFormat(d => {
      const index = Math.round(d) - 1;
      return index >= 0 && index < comb.length ? d3.format("d")(comb[index].yearName) : "";
    })
    .tickSizeOuter(0)
    .tickSizeInner(-innerHeight));

  xAxisGroup.selectAll(".tick text")
    .style("font-size", `${fontSizes.xAxisTick}px`);
  
  // ========================================
  // LINES
  // ========================================
  const dashArray = `${Math.max(2, Math.min(6, width / 200))},${Math.max(2, Math.min(6, width / 200))}`;
  const strokeWidth = Math.max(1.5, Math.min(3, width / 400));
  
  // draw combined first so the dashed lines sit on top; split each at 2015/2016
  // (built-up data source change) (team fix)
  const _seg = arr => [arr.filter(d => d.yearName <= 2015), arr.filter(d => d.yearName >= 2016)];
  const _series = [
    { data: comb, key: "comb", color: "black",   dashed: false },  // combined - black solid
    { data: cu,   key: "cu",   color: "#02b939", dashed: true  },  // coastal - green dashed
    { data: fu,   key: "fu",   color: "#f8766d", dashed: true  },  // fluvial - red dashed
    { data: pu,   key: "pu",   color: "#619cfe", dashed: true  }   // pluvial - blue dashed
  ];
  _series.forEach(sr => {
    const lineFn = d3.line()
      .defined(d => d[sr.key] !== null)
      .x(d => xScale(d.year))
      .y(d => yScale(d[sr.key]));
    _seg(sr.data).forEach(segment => {
      if (segment.length === 0) return;
      g.append("path")
        .datum(segment)
        .attr("fill", "none")
        .attr("stroke", sr.color)
        .attr("stroke-width", strokeWidth)
        .attr("stroke-dasharray", sr.dashed ? dashArray : null)
        .attr("d", lineFn);
    });
  });
  
  // ========================================
  // INTERACTION AREA (INVISIBLE)
  // ========================================
  // (invisible interaction areas for tooltips)
  g.selectAll(".interaction-area")
    .data(comb.filter(d => d.comb !== null))
    .enter().append("rect")
    .attr("class", "interaction-area")
    .attr("x", d => xScale(d.year) - 5)
    .attr("y", 0)
    .attr("width", 10)
    .attr("height", innerHeight)
    .attr("fill", "transparent")
    .style("cursor", "default")
    .on("mouseover", function(event, d) {
      d3.selectAll(".d3-tooltip").remove();
      
      // find corresponding values for this year in all datasets
      const puValue = pu.find(p => p.year === d.year)?.pu || 0;
      const fuValue = fu.find(f => f.year === d.year)?.fu || 0;
      const cuValue = cu.find(c => c.year === d.year)?.cu || 0;

      const tooltip = d3.select("body").append("div")
        .attr("class", "d3-tooltip")
        .style("opacity", 0);
        
      const html = `<div><strong>Year: ${d.yearName}</strong></div><div>━━━━━━━━━━━━</div><div>Combined: ${(+d.comb).toFixed(1)} sq km</div><div>&nbsp;</div><div>Pluvial: ${puValue.toFixed(1)} sq km</div><div>Fluvial: ${fuValue.toFixed(1)} sq km</div><div>Coastal: ${cuValue.toFixed(1)} sq km</div>`;
      
      const tooltipWidth = 220;
      const windowWidth = window.innerWidth;
      const mouseX = event.pageX;
      
      let leftPos = mouseX + 10;
      if (leftPos + tooltipWidth > windowWidth) {
        leftPos = mouseX - tooltipWidth - 10;
      }
      
      tooltip
        .html(html)
        .style("left", leftPos + "px")
        .style("top", (event.pageY - 35) + "px")
        .transition()
        .duration(200)
        .style("opacity", 1);
    })
    .on("mousemove", function(event) {
      const tooltip = d3.select(".d3-tooltip");
      if (!tooltip.empty()) {
        const tooltipWidth = 220;
        const windowWidth = window.innerWidth;
        const mouseX = event.pageX;
        
        let leftPos = mouseX + 10;
        if (leftPos + tooltipWidth > windowWidth) {
          leftPos = mouseX - tooltipWidth - 10;
        }
        
        tooltip
          .style("left", leftPos + "px")
          .style("top", (event.pageY - 35) + "px");
      }
    })
    .on("mouseout", function() {
      d3.select(".d3-tooltip")
        .transition()
        .duration(200)
        .style("opacity", 0)
        .remove();
    });
  
  // ========================================
  // LEGEND
  // ========================================
  const legendData = [
    { label: "River", color: "#f8766d", dashed: true },
    { label: "Rainwater", color: "#619cfe", dashed: true },
    { label: "Coastal", color: "#02b939", dashed: true },
    { label: "Combined", color: "black", dashed: false }   // narrative order: types, then total (team)
  ];

  PlotHelpers.addLegend(svg, legendData, width, height, 'top-right');
  
  // ========================================
  // TITLE
  // ========================================
  const heightScale = height / PlotHelpers.PLOT_BASE.HEIGHT;
  const titleY = PlotHelpers.getTitleY(height, heightScale);
  
  titleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-title")
      .attr("x", 20)
      .attr("y", titleY + (i * lineHeights.title))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.title}px`)
      .text(line);
  });
    
  // ========================================
  // SUBTITLE
  // ========================================
  const subtitleY = PlotHelpers.getSubtitleY(titleY, titleLines.length, lineHeights.title, heightScale);
  
  subtitleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-subtitle")
      .attr("x", 20)
      .attr("y", subtitleY + (i * lineHeights.subtitle))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.subtitle}px`)
      .text(line);
  });
    
  // ========================================
  // Y-AXIS LABEL
  // ========================================
  const widthScale = width / PlotHelpers.PLOT_BASE.WIDTH;
  const yAxisLabelX = -(margin.top + innerHeight/2);
  const yAxisLabelY = PlotHelpers.getYAxisLabelY(widthScale);
  
  yAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("transform", "rotate(-90)")
      .attr("y", yAxisLabelY + (i * lineHeights.axisLabel))
      .attr("x", yAxisLabelX)
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // X-AXIS LABEL
  // ========================================
  const xAxisLabelX = margin.left + innerWidth/2;
  const xAxisLabelY = PlotHelpers.getXAxisLabelY(height, captionHeight, heightScale);
  
  xAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("x", xAxisLabelX)
      .attr("y", xAxisLabelY - ((xAxisLabelLines.length - 1 - i) * lineHeights.axisLabel))
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // CAPTION
  // ========================================
  // (empty for this plot)
  if (captionText) {
    const captionY = PlotHelpers.getCaptionY(height, heightScale);
    
    captionLines.forEach((line, i) => {
      svg.append("text")
        .attr("class", "plot-caption")
        .attr("x", 20)
        .attr("y", captionY - ((captionLines.length - 1 - i) * lineHeights.caption))
        .attr("text-anchor", "start")
        .style("font-size", `${fontSizes.caption}px`)
        .text(line);
    });
  }
  
  return svg.node();
}


// ------------------------------------------------------------
// plot_e
// ------------------------------------------------------------
function plot_e(e, {
  cityName = globalCity, 
  countryName = globalCountry,
  width,
  height
} = {}) {
  
  // ========================================
  // DATA PREPARATION
  // ========================================
  // normalize columns (Bin/bin, Pixel_Count/count) and compute the percentage the
  // bars need: the analyze CSV only carries raw counts (team fix)
  const _norm = e.map(d => ({ bin: d.bin ?? d.Bin, count: +(d.count ?? d.Pixel_Count ?? 0) }));
  const _total = _norm.reduce((sum, d) => sum + d.count, 0) || 1;
  _norm.forEach(d => d.percentage = d.count / _total * 100);
  const sortedData = _norm.sort((a, b) => 
    PlotHelpers.parseElevationRange(a.bin) - PlotHelpers.parseElevationRange(b.bin)
  );

  // elevation colors: 0 = lowest, 4 = highest
  const elevationColors = {
    0: "#f9d7d4",  // (lowest elevation)
    1: "#e3b9c5",
    2: "#cd9db8",
    3: "#b682ac",
    4: "#9f65a0"   // (highest elevation)
  };

  // color mapping based on elevation order
  const elevationColorMap = {};
  sortedData.forEach((d, index) => {
    elevationColorMap[d.bin] = elevationColors[index];
  });
  const defaultColor = "#999999"; // (fallback gray if no color map match)
  
  const allElevationBins = sortedData.map(d => d.bin);
  
  // complete data with gray bars for visual completeness
  const completeData = allElevationBins.map(bin => {
    const existing = sortedData.find(d => d.bin === bin);
    return existing || { bin, count: 0, percentage: 0 };
  });

  // ========================================
  // STYLING CALCULATIONS
  // ========================================
  // (use helper functions from plot-helpers.js for all styling calculations)
  const fontSizes = PlotHelpers.calculateFontSizes(width, height);
  const lineHeights = PlotHelpers.calculateLineHeights(fontSizes);
  
  // text content
  const titleText = "Elevation";
  const titleLocation = countryName ? `${cityName}, ${countryName}` : cityName;
  const xAxisLabelText = "Elevation (MASL)";
  const yAxisLabelText = "Percentage of Area (%)";
  const captionText = ""; // (empty for this plot)
  
  // text wrapping
  const titleLines = PlotHelpers.wrapText(titleText, width - 40, `${fontSizes.title}px system-ui`);
  const subtitleLines = PlotHelpers.wrapText(titleLocation, width - 40, `${fontSizes.subtitle}px system-ui`);
  const xAxisLabelLines = PlotHelpers.wrapText(xAxisLabelText, width * 0.8, `${fontSizes.axisLabel}px system-ui`);
  const yAxisLabelLines = PlotHelpers.wrapText(yAxisLabelText, height * 0.6, `${fontSizes.axisLabel}px system-ui`);
  const captionLines = PlotHelpers.wrapText(captionText, width - 40, `${fontSizes.caption}px system-ui`);

  // calculate text dimensions for margins
  const titleHeight = titleLines.length * lineHeights.title;
  const subtitleHeight = subtitleLines.length * lineHeights.subtitle;
  const xAxisLabelHeight = xAxisLabelLines.length * lineHeights.axisLabel;
  const captionHeight = captionLines.length * lineHeights.caption;
  const yAxisLabelWidth = yAxisLabelLines.length * lineHeights.axisLabel;

  // calculate margins using helper
  const margin = PlotHelpers.calculateMargins(width, height, {
    titleHeight,
    subtitleHeight,
    xAxisLabelHeight,
    captionHeight,
    yAxisLabelWidth
  });
  
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  
  // ========================================
  // SCALES
  // ========================================
  const xScale = d3.scaleBand()
    .domain(completeData.map(d => d.bin))
    .range([0, innerWidth])
    .padding(0.1);
    
  const yScale = d3.scaleLinear()
    .domain([0, 100])
    .range([innerHeight, 0]);

  // ========================================
  // SVG CREATION
  // ========================================
  const svg = d3.create("svg")
    .attr("viewBox", `0 0 ${width} ${height}`)
    .attr("preserveAspectRatio", "xMidYMid meet")
    .style("width", "100%")
    .style("height", "auto")
    .style("max-width", `${width}px`);

  const g = svg.append("g")
    .attr("transform", `translate(${margin.left},${margin.top})`);
  
  // ========================================
  // Y-AXIS
  // ========================================
  const yTicks = PlotHelpers.calculateYTicks(innerHeight);
  const yAxisGroup = g.append("g").attr("class", "y-axis");
  const yAxisCall = d3.axisLeft(yScale)
    .ticks(yTicks)
    .tickSizeOuter(0)
    .tickSizeInner(-innerWidth)
    .tickFormat(d3.format("~s"));

  yAxisGroup.call(yAxisCall);
  yAxisGroup.selectAll(".tick text")
    .style("font-size", `${fontSizes.yAxisTick}px`);
    
  // ========================================
  // BARS
  // ========================================
  // gray background bars
  g.selectAll(".background-bar")
    .data(completeData)
    .enter().append("rect")
    .attr("class", "background-bar")
    .attr("x", d => xScale(d.bin))
    .attr("width", xScale.bandwidth())
    .attr("y", 0)
    .attr("height", innerHeight);
    
  // data bars with smart tooltips
  g.selectAll(".data-bar")
    .data(completeData.filter(d => d.percentage > 0))
    .enter().append("rect")
    .attr("class", "data-bar")
    .attr("x", d => xScale(d.bin))
    .attr("width", xScale.bandwidth())
    .attr("y", d => yScale(d.percentage))
    .attr("height", d => innerHeight - yScale(d.percentage))
    .attr("fill", d => elevationColorMap[d.bin] || defaultColor)
    .attr("fill-opacity", 1)
    .attr("stroke", d => d3.color(elevationColorMap[d.bin] || defaultColor).darker(0.5))
    .attr("stroke-width", 1)
    .style("cursor", "default")
    .on("mouseover", function(event, d) {
      d3.selectAll(".d3-tooltip").remove();

      const tooltip = d3.select("body").append("div")
        .attr("class", "d3-tooltip")
        .style("opacity", 0);
        
      const html = `<div>Elevation: ${d.bin} MASL</div><div>Percentage of Area: ${d.percentage.toFixed(1)}%</div>`;
      
      // calculate position to avoid bleeding off screen
      const tooltipWidth = 220;
      const windowWidth = window.innerWidth;
      const mouseX = event.pageX;
      
      let leftPos = mouseX + 10;
      if (leftPos + tooltipWidth > windowWidth) {
        leftPos = mouseX - tooltipWidth - 10;
      }
      
      tooltip
        .html(html)
        .style("left", leftPos + "px")
        .style("top", (event.pageY - 35) + "px")
        .transition()
        .duration(200)
        .style("opacity", 1);
    })
    .on("mousemove", function(event) {
      const tooltip = d3.select(".d3-tooltip");
      if (!tooltip.empty()) {
        const tooltipWidth = 220;
        const windowWidth = window.innerWidth;
        const mouseX = event.pageX;
        
        let leftPos = mouseX + 10;
        if (leftPos + tooltipWidth > windowWidth) {
          leftPos = mouseX - tooltipWidth - 10;
        }
        
        tooltip
          .style("left", leftPos + "px")
          .style("top", (event.pageY - 35) + "px");
      }
    })
    .on("mouseout", function() {
      d3.select(".d3-tooltip")
        .transition()
        .duration(200)
        .style("opacity", 0)
        .remove();
    });

  // ========================================
  // BAR PERCENTAGE LABELS
  // ========================================
  g.selectAll(".bar-label")
    .data(completeData)
    .enter().append("text")
    .attr("class", "plot-bar-label")
    .attr("x", d => xScale(d.bin) + xScale.bandwidth()/2)
    .attr("y", d => d.percentage > 0 ? yScale(d.percentage) - 8 : innerHeight/2)
    .attr("text-anchor", "middle")
    .attr("fill", d => d.percentage > 0 ? "black" : "#6c757d")
    .style("font-size", `${fontSizes.barLabel}px`)
    .attr("font-style", d => d.percentage > 0 ? "normal" : "italic")
    .text(d => d.percentage > 0 ? `${d.percentage.toFixed(1)}%` : "")
    .style("display", d => d.percentage > 2 || d.percentage === 0 ? "block" : "none");

  // ========================================
  // X-AXIS
  // ========================================
  const xAxisGroup = g.append("g")
    .attr("class", "x-axis")
    .attr("transform", `translate(0,${innerHeight})`);
    
  xAxisGroup.call(d3.axisBottom(xScale)
    .tickSizeOuter(0)
    .tickSizeInner(0));
 
  // x-axis tick labels with wrapping
  const barWidth = xScale.bandwidth();
  const xAxisTickSize = PlotHelpers.calculateXAxisTickSize(barWidth);
  
  xAxisGroup.selectAll(".tick text")
    .each(function(d) {
      const text = d3.select(this);
      const labelText = text.text();
      
      text.style("font-size", `${xAxisTickSize}px`);
      
      const lines = PlotHelpers.wrapBarLabel(labelText, barWidth, `${xAxisTickSize}px system-ui`);
      text.text(null);
      
      lines.forEach((line, i) => {
        text.append("tspan")
          .attr("x", 0)
          .attr("dy", i === 0 ? "1.2em" : "1.1em")
          .text(line);
      });
    });
    
  // ========================================
  // TITLE
  // ========================================
  const heightScale = height / PlotHelpers.PLOT_BASE.HEIGHT;
  const titleY = PlotHelpers.getTitleY(height, heightScale);
  
  titleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-title")
      .attr("x", 20)
      .attr("y", titleY + (i * lineHeights.title))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.title}px`)
      .text(line);
  });
    
  // ========================================
  // SUBTITLE
  // ========================================
  const subtitleY = PlotHelpers.getSubtitleY(titleY, titleLines.length, lineHeights.title, heightScale);
  
  subtitleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-subtitle")
      .attr("x", 20)
      .attr("y", subtitleY + (i * lineHeights.subtitle))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.subtitle}px`)
      .text(line);
  });
    
  // ========================================
  // Y-AXIS LABEL
  // ========================================
  const widthScale = width / PlotHelpers.PLOT_BASE.WIDTH;
  const yAxisLabelX = -(margin.top + innerHeight/2);
  const yAxisLabelY = PlotHelpers.getYAxisLabelY(widthScale);
  
  yAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("transform", "rotate(-90)")
      .attr("y", yAxisLabelY + (i * lineHeights.axisLabel))
      .attr("x", yAxisLabelX)
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // X-AXIS LABEL
  // ========================================
  const xAxisLabelX = margin.left + innerWidth/2;
  const xAxisLabelY = PlotHelpers.getXAxisLabelY(height, captionHeight, heightScale);
  
  xAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("x", xAxisLabelX)
      .attr("y", xAxisLabelY - ((xAxisLabelLines.length - 1 - i) * lineHeights.axisLabel))
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // CAPTION
  // ========================================
  // (empty for this plot)
  if (captionText) {
    const captionY = PlotHelpers.getCaptionY(height, heightScale);
    
    captionLines.forEach((line, i) => {
      svg.append("text")
        .attr("class", "plot-caption")
        .attr("x", 20)
        .attr("y", captionY - ((captionLines.length - 1 - i) * lineHeights.caption))
        .attr("text-anchor", "start")
        .style("font-size", `${fontSizes.caption}px`)
        .text(line);
    });
  }
  
  return svg.node();
}


// ------------------------------------------------------------
// plot_s
// ------------------------------------------------------------
function plot_s(s, {
  cityName = globalCity, 
  countryName = globalCountry,
  width,
  height
} = {}) {
  
  // ========================================
  // DATA PREPARATION
  // ========================================
  // normalize columns (Bin/bin, Pixel_Count/count) and compute the percentage the
  // bars need: the analyze CSV only carries raw counts (team fix)
  const _norm = s.map(d => ({ bin: d.bin ?? d.Bin, count: +(d.count ?? d.Pixel_Count ?? 0) }));
  const _total = _norm.reduce((sum, d) => sum + d.count, 0) || 1;
  _norm.forEach(d => d.percentage = d.count / _total * 100);
  const sortedData = _norm.sort((a, b) => 
    PlotHelpers.parseSlopeRange(a.bin) - PlotHelpers.parseSlopeRange(b.bin)
  );

  // slope colors
  const slopeColorMap = {
    "0-2": "#f9f9db",  // (lowest slope)
    "2-5": "#ebd5b4",
    "5-10": "#dab38f",
    "10-20": "#c88f6e",
    "20-90": "#b26b4a" 
  };
  const defaultColor = "#999999"; // (fallback gray if no color map match)
  
  const allSlopeBins = sortedData.map(d => d.bin);
  
  // complete data with gray bars for visual completeness
  const completeData = allSlopeBins.map(bin => {
    const existing = sortedData.find(d => d.bin === bin);
    return existing || { bin, count: 0, percentage: 0 };
  });

  // ========================================
  // STYLING CALCULATIONS
  // ========================================
  // (use helper functions from plot-helpers.js for all styling calculations)
  const fontSizes = PlotHelpers.calculateFontSizes(width, height);
  const lineHeights = PlotHelpers.calculateLineHeights(fontSizes);
  
  // text content
  const titleText = "Slope";
  const titleLocation = countryName ? `${cityName}, ${countryName}` : cityName;
  const xAxisLabelText = "Slope (°)";
  const yAxisLabelText = "Percentage of Area (%)";
  const captionText = ""; // (empty for this plot)
  
  // text wrapping
  const titleLines = PlotHelpers.wrapText(titleText, width - 40, `${fontSizes.title}px system-ui`);
  const subtitleLines = PlotHelpers.wrapText(titleLocation, width - 40, `${fontSizes.subtitle}px system-ui`);
  const xAxisLabelLines = PlotHelpers.wrapText(xAxisLabelText, width * 0.8, `${fontSizes.axisLabel}px system-ui`);
  const yAxisLabelLines = PlotHelpers.wrapText(yAxisLabelText, height * 0.6, `${fontSizes.axisLabel}px system-ui`);
  const captionLines = PlotHelpers.wrapText(captionText, width - 40, `${fontSizes.caption}px system-ui`);

  // calculate text dimensions for margins
  const titleHeight = titleLines.length * lineHeights.title;
  const subtitleHeight = subtitleLines.length * lineHeights.subtitle;
  const xAxisLabelHeight = xAxisLabelLines.length * lineHeights.axisLabel;
  const captionHeight = captionLines.length * lineHeights.caption;
  const yAxisLabelWidth = yAxisLabelLines.length * lineHeights.axisLabel;

  // calculate margins using helper
  const margin = PlotHelpers.calculateMargins(width, height, {
    titleHeight,
    subtitleHeight,
    xAxisLabelHeight,
    captionHeight,
    yAxisLabelWidth
  });
  
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  
  // ========================================
  // SCALES
  // ========================================
  const xScale = d3.scaleBand()
    .domain(completeData.map(d => d.bin))
    .range([0, innerWidth])
    .padding(0.1);
    
  const yScale = d3.scaleLinear()
    .domain([0, 100])
    .range([innerHeight, 0]);

  // ========================================
  // SVG CREATION
  // ========================================
  const svg = d3.create("svg")
    .attr("viewBox", `0 0 ${width} ${height}`)
    .attr("preserveAspectRatio", "xMidYMid meet")
    .style("width", "100%")
    .style("height", "auto")
    .style("max-width", `${width}px`);

  const g = svg.append("g")
    .attr("transform", `translate(${margin.left},${margin.top})`);
  
  // ========================================
  // Y-AXIS
  // ========================================
  const yTicks = PlotHelpers.calculateYTicks(innerHeight);
  const yAxisGroup = g.append("g").attr("class", "y-axis");
  const yAxisCall = d3.axisLeft(yScale)
    .ticks(yTicks)
    .tickSizeOuter(0)
    .tickSizeInner(-innerWidth)
    .tickFormat(d3.format("~s"));

  yAxisGroup.call(yAxisCall);
  yAxisGroup.selectAll(".tick text")
    .style("font-size", `${fontSizes.yAxisTick}px`);
    
  // ========================================
  // BARS
  // ========================================
  // gray background bars
  g.selectAll(".background-bar")
    .data(completeData)
    .enter().append("rect")
    .attr("class", "background-bar")
    .attr("x", d => xScale(d.bin))
    .attr("width", xScale.bandwidth())
    .attr("y", 0)
    .attr("height", innerHeight);
    
  // data bars with smart tooltips
  g.selectAll(".data-bar")
    .data(completeData.filter(d => d.percentage > 0))
    .enter().append("rect")
    .attr("class", "data-bar")
    .attr("x", d => xScale(d.bin))
    .attr("width", xScale.bandwidth())
    .attr("y", d => yScale(d.percentage))
    .attr("height", d => innerHeight - yScale(d.percentage))
    .attr("fill", d => slopeColorMap[d.bin] || defaultColor)
    .attr("fill-opacity", 1)
    .attr("stroke", d => d3.color(slopeColorMap[d.bin] || defaultColor).darker(0.5))
    .attr("stroke-width", 1)
    .style("cursor", "default")
    .on("mouseover", function(event, d) {
      d3.selectAll(".d3-tooltip").remove();

      const tooltip = d3.select("body").append("div")
        .attr("class", "d3-tooltip")
        .style("opacity", 0);
        
      const html = `<div>Slope: ${d.bin}°</div><div>Percentage of Area: ${d.percentage.toFixed(1)}%</div>`;
      
      // calculate position to avoid bleeding off screen
      const tooltipWidth = 220;
      const windowWidth = window.innerWidth;
      const mouseX = event.pageX;
      
      let leftPos = mouseX + 10;
      if (leftPos + tooltipWidth > windowWidth) {
        leftPos = mouseX - tooltipWidth - 10;
      }
      
      tooltip
        .html(html)
        .style("left", leftPos + "px")
        .style("top", (event.pageY - 35) + "px")
        .transition()
        .duration(200)
        .style("opacity", 1);
    })
    .on("mousemove", function(event) {
      const tooltip = d3.select(".d3-tooltip");
      if (!tooltip.empty()) {
        const tooltipWidth = 220;
        const windowWidth = window.innerWidth;
        const mouseX = event.pageX;
        
        let leftPos = mouseX + 10;
        if (leftPos + tooltipWidth > windowWidth) {
          leftPos = mouseX - tooltipWidth - 10;
        }
        
        tooltip
          .style("left", leftPos + "px")
          .style("top", (event.pageY - 35) + "px");
      }
    })
    .on("mouseout", function() {
      d3.select(".d3-tooltip")
        .transition()
        .duration(200)
        .style("opacity", 0)
        .remove();
    });

  // ========================================
  // BAR PERCENTAGE LABELS
  // ========================================
  g.selectAll(".bar-label")
    .data(completeData)
    .enter().append("text")
    .attr("class", "plot-bar-label")
    .attr("x", d => xScale(d.bin) + xScale.bandwidth()/2)
    .attr("y", d => d.percentage > 0 ? yScale(d.percentage) - 8 : innerHeight/2)
    .attr("text-anchor", "middle")
    .attr("fill", d => d.percentage > 0 ? "black" : "#6c757d")
    .style("font-size", `${fontSizes.barLabel}px`)
    .attr("font-style", d => d.percentage > 0 ? "normal" : "italic")
    .text(d => d.percentage > 0 ? `${d.percentage.toFixed(1)}%` : "")
    .style("display", d => d.percentage > 2 || d.percentage === 0 ? "block" : "none");

  // ========================================
  // X-AXIS
  // ========================================
  const xAxisGroup = g.append("g")
    .attr("class", "x-axis")
    .attr("transform", `translate(0,${innerHeight})`);
    
  xAxisGroup.call(d3.axisBottom(xScale)
    .tickSizeOuter(0)
    .tickSizeInner(0));
 
  // x-axis tick labels with wrapping
  const barWidth = xScale.bandwidth();
  const xAxisTickSize = PlotHelpers.calculateXAxisTickSize(barWidth);
  
  xAxisGroup.selectAll(".tick text")
    .each(function(d) {
      const text = d3.select(this);
      const labelText = text.text();
      
      text.style("font-size", `${xAxisTickSize}px`);
      
      const lines = PlotHelpers.wrapBarLabel(labelText, barWidth, `${xAxisTickSize}px system-ui`);
      text.text(null);
      
      lines.forEach((line, i) => {
        text.append("tspan")
          .attr("x", 0)
          .attr("dy", i === 0 ? "1.2em" : "1.1em")
          .text(line);
      });
    });
    
  // ========================================
  // TITLE
  // ========================================
  const heightScale = height / PlotHelpers.PLOT_BASE.HEIGHT;
  const titleY = PlotHelpers.getTitleY(height, heightScale);
  
  titleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-title")
      .attr("x", 20)
      .attr("y", titleY + (i * lineHeights.title))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.title}px`)
      .text(line);
  });
    
  // ========================================
  // SUBTITLE
  // ========================================
  const subtitleY = PlotHelpers.getSubtitleY(titleY, titleLines.length, lineHeights.title, heightScale);
  
  subtitleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-subtitle")
      .attr("x", 20)
      .attr("y", subtitleY + (i * lineHeights.subtitle))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.subtitle}px`)
      .text(line);
  });
    
  // ========================================
  // Y-AXIS LABEL
  // ========================================
  const widthScale = width / PlotHelpers.PLOT_BASE.WIDTH;
  const yAxisLabelX = -(margin.top + innerHeight/2);
  const yAxisLabelY = PlotHelpers.getYAxisLabelY(widthScale);
  
  yAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("transform", "rotate(-90)")
      .attr("y", yAxisLabelY + (i * lineHeights.axisLabel))
      .attr("x", yAxisLabelX)
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // X-AXIS LABEL
  // ========================================
  const xAxisLabelX = margin.left + innerWidth/2;
  const xAxisLabelY = PlotHelpers.getXAxisLabelY(height, captionHeight, heightScale);
  
  xAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("x", xAxisLabelX)
      .attr("y", xAxisLabelY - ((xAxisLabelLines.length - 1 - i) * lineHeights.axisLabel))
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // CAPTION
  // ========================================
  // (empty for this plot)
  if (captionText) {
    const captionY = PlotHelpers.getCaptionY(height, heightScale);
    
    captionLines.forEach((line, i) => {
      svg.append("text")
        .attr("class", "plot-caption")
        .attr("x", 20)
        .attr("y", captionY - ((captionLines.length - 1 - i) * lineHeights.caption))
        .attr("text-anchor", "start")
        .style("font-size", `${fontSizes.caption}px`)
        .text(line);
    });
  }
  
  return svg.node();
}


// ------------------------------------------------------------
// plot_ls_area
// ------------------------------------------------------------
function plot_ls_area(ls_area, {
  cityName = globalCity, 
  countryName = globalCountry,
  width,
  height
} = {}) {
  
  // ========================================
  // DATA PREPARATION
  // ========================================
  const sortedData = ls_area.slice().sort((a, b) => 
    PlotHelpers.parseLsAreaRange(a.bin) - PlotHelpers.parseLsAreaRange(b.bin)
  );

  // color mapping for landslide susceptibility
  const lsAreaColorMap = {
    "1": "#f6efe5",
    "2": "#f1cda8",
    "3": "#e9ac81",
    "4": "#dc8b6d",
    "5": "#b27365"
  };
  const defaultColor = "#999999"; // (fallback gray if no color map match)

  // map from bins to susceptibility values
  const binToSusceptibilityMap = {
    "Very low": "1",
    "Low": "2", 
    "Medium": "3", 
    "High": "4", 
    "Very high": "5"
  };
  
  const allLsAreaBins = sortedData.map(d => d.bin);
  
  // complete data with gray bars for visual completeness
  const completeData = allLsAreaBins.map(bin => {
    const existing = sortedData.find(d => d.bin === bin);
    return existing || { bin, count: 0, percentage: 0 };
  });

  // ========================================
  // STYLING CALCULATIONS
  // ========================================
  // (use helper functions from plot-helpers.js for all styling calculations)
  const fontSizes = PlotHelpers.calculateFontSizes(width, height);
  const lineHeights = PlotHelpers.calculateLineHeights(fontSizes);
  
  // text content
  const titleText = "Landslide Susceptibility";
  const titleLocation = countryName ? `${cityName}, ${countryName}` : cityName;
  const xAxisLabelText = "Landslide Susceptibility";
  const yAxisLabelText = "Percentage of Area (%)";
  const captionText = "Data: NASA, 'Landslide Susceptibility Map'";
  
  // text wrapping
  const titleLines = PlotHelpers.wrapText(titleText, width - 40, `${fontSizes.title}px system-ui`);
  const subtitleLines = PlotHelpers.wrapText(titleLocation, width - 40, `${fontSizes.subtitle}px system-ui`);
  const xAxisLabelLines = PlotHelpers.wrapText(xAxisLabelText, width * 0.8, `${fontSizes.axisLabel}px system-ui`);
  const yAxisLabelLines = PlotHelpers.wrapText(yAxisLabelText, height * 0.6, `${fontSizes.axisLabel}px system-ui`);
  const captionLines = PlotHelpers.wrapText(captionText, width - 40, `${fontSizes.caption}px system-ui`);

  // calculate text dimensions for margins
  const titleHeight = titleLines.length * lineHeights.title;
  const subtitleHeight = subtitleLines.length * lineHeights.subtitle;
  const xAxisLabelHeight = xAxisLabelLines.length * lineHeights.axisLabel;
  const captionHeight = captionLines.length * lineHeights.caption;
  const yAxisLabelWidth = yAxisLabelLines.length * lineHeights.axisLabel;

  // calculate margins using helper
  const margin = PlotHelpers.calculateMargins(width, height, {
    titleHeight,
    subtitleHeight,
    xAxisLabelHeight,
    captionHeight,
    yAxisLabelWidth
  });
  
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  
  // ========================================
  // SCALES
  // ========================================
  const xScale = d3.scaleBand()
    .domain(completeData.map(d => d.bin))
    .range([0, innerWidth])
    .padding(0.1);
    
  const yScale = d3.scaleLinear()
    .domain([0, 100])
    .range([innerHeight, 0]);

  // ========================================
  // SVG CREATION
  // ========================================
  const svg = d3.create("svg")
    .attr("viewBox", `0 0 ${width} ${height}`)
    .attr("preserveAspectRatio", "xMidYMid meet")
    .style("width", "100%")
    .style("height", "auto")
    .style("max-width", `${width}px`);

  const g = svg.append("g")
    .attr("transform", `translate(${margin.left},${margin.top})`);
  
  // ========================================
  // Y-AXIS
  // ========================================
  const yTicks = PlotHelpers.calculateYTicks(innerHeight);
  const yAxisGroup = g.append("g").attr("class", "y-axis");
  const yAxisCall = d3.axisLeft(yScale)
    .ticks(yTicks)
    .tickSizeOuter(0)
    .tickSizeInner(-innerWidth)
    .tickFormat(d3.format("~s"));

  yAxisGroup.call(yAxisCall);
  yAxisGroup.selectAll(".tick text")
    .style("font-size", `${fontSizes.yAxisTick}px`);
    
  // ========================================
  // BARS
  // ========================================
  // gray background bars
  g.selectAll(".background-bar")
    .data(completeData)
    .enter().append("rect")
    .attr("class", "background-bar")
    .attr("x", d => xScale(d.bin))
    .attr("width", xScale.bandwidth())
    .attr("y", 0)
    .attr("height", innerHeight);
    
  // data bars with smart tooltips
  g.selectAll(".data-bar")
    .data(completeData.filter(d => d.percentage > 0))
    .enter().append("rect")
    .attr("class", "data-bar")
    .attr("x", d => xScale(d.bin))
    .attr("width", xScale.bandwidth())
    .attr("y", d => yScale(d.percentage))
    .attr("height", d => innerHeight - yScale(d.percentage))
    .attr("fill", d => lsAreaColorMap[d.susceptibility] || defaultColor)
    .attr("fill-opacity", 1)
    .attr("stroke", d => d3.color(lsAreaColorMap[d.susceptibility] || defaultColor).darker(0.3))
    .attr("stroke-width", 1)
    .style("cursor", "default")
    .on("mouseover", function(event, d) {
      d3.selectAll(".d3-tooltip").remove();

      const tooltip = d3.select("body").append("div")
        .attr("class", "d3-tooltip")
        .style("opacity", 0);
        
      const html = `<div>Landslide Susceptibility: ${d.susceptibility}</div><div>Percentage of Area: ${d.percentage.toFixed(1)}%</div>`;
      
      // calculate position to avoid bleeding off screen
      const tooltipWidth = 220;
      const windowWidth = window.innerWidth;
      const mouseX = event.pageX;
      
      let leftPos = mouseX + 10;
      if (leftPos + tooltipWidth > windowWidth) {
        leftPos = mouseX - tooltipWidth - 10;
      }
      
      tooltip
        .html(html)
        .style("left", leftPos + "px")
        .style("top", (event.pageY - 35) + "px")
        .transition()
        .duration(200)
        .style("opacity", 1);
    })
    .on("mousemove", function(event) {
      const tooltip = d3.select(".d3-tooltip");
      if (!tooltip.empty()) {
        const tooltipWidth = 220;
        const windowWidth = window.innerWidth;
        const mouseX = event.pageX;
        
        let leftPos = mouseX + 10;
        if (leftPos + tooltipWidth > windowWidth) {
          leftPos = mouseX - tooltipWidth - 10;
        }
        
        tooltip
          .style("left", leftPos + "px")
          .style("top", (event.pageY - 35) + "px");
      }
    })
    .on("mouseout", function() {
      d3.select(".d3-tooltip")
        .transition()
        .duration(200)
        .style("opacity", 0)
        .remove();
    });

  // ========================================
  // BAR PERCENTAGE LABELS
  // ========================================
  g.selectAll(".bar-label")
    .data(completeData)
    .enter().append("text")
    .attr("class", "plot-bar-label")
    .attr("x", d => xScale(d.bin) + xScale.bandwidth()/2)
    .attr("y", d => d.percentage > 0 ? yScale(d.percentage) - 8 : innerHeight/2)
    .attr("text-anchor", "middle")
    .attr("fill", d => d.percentage > 0 ? "black" : "#6c757d")
    .style("font-size", `${fontSizes.barLabel}px`)
    .attr("font-style", d => d.percentage > 0 ? "normal" : "italic")
    .text(d => d.percentage > 0 ? `${d.percentage.toFixed(1)}%` : "")
    .style("display", d => d.percentage > 2 || d.percentage === 0 ? "block" : "none");

  // ========================================
  // X-AXIS
  // ========================================
  const xAxisGroup = g.append("g")
    .attr("class", "x-axis")
    .attr("transform", `translate(0,${innerHeight})`);
    
  xAxisGroup.call(d3.axisBottom(xScale)
    .tickSizeOuter(0)
    .tickSizeInner(0));
 
  // x-axis tick labels with wrapping
  const barWidth = xScale.bandwidth();
  const xAxisTickSize = PlotHelpers.calculateXAxisTickSize(barWidth);
  
  xAxisGroup.selectAll(".tick text")
    .each(function(d) {
      const text = d3.select(this);
      const labelText = text.text();
      
      text.style("font-size", `${xAxisTickSize}px`);
      
      const lines = PlotHelpers.wrapBarLabel(labelText, barWidth, `${xAxisTickSize}px system-ui`);
      text.text(null);
      
      lines.forEach((line, i) => {
        text.append("tspan")
          .attr("x", 0)
          .attr("dy", i === 0 ? "1.2em" : "1.1em")
          .text(line);
      });
    });
    
  // ========================================
  // TITLE
  // ========================================
  const heightScale = height / PlotHelpers.PLOT_BASE.HEIGHT;
  const titleY = PlotHelpers.getTitleY(height, heightScale);
  
  titleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-title")
      .attr("x", 20)
      .attr("y", titleY + (i * lineHeights.title))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.title}px`)
      .text(line);
  });
    
  // ========================================
  // SUBTITLE
  // ========================================
  const subtitleY = PlotHelpers.getSubtitleY(titleY, titleLines.length, lineHeights.title, heightScale);
  
  subtitleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-subtitle")
      .attr("x", 20)
      .attr("y", subtitleY + (i * lineHeights.subtitle))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.subtitle}px`)
      .text(line);
  });
    
  // ========================================
  // Y-AXIS LABEL
  // ========================================
  const widthScale = width / PlotHelpers.PLOT_BASE.WIDTH;
  const yAxisLabelX = -(margin.top + innerHeight/2);
  const yAxisLabelY = PlotHelpers.getYAxisLabelY(widthScale);
  
  yAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("transform", "rotate(-90)")
      .attr("y", yAxisLabelY + (i * lineHeights.axisLabel))
      .attr("x", yAxisLabelX)
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // X-AXIS LABEL
  // ========================================
  const xAxisLabelX = margin.left + innerWidth/2;
  const xAxisLabelY = PlotHelpers.getXAxisLabelY(height, captionHeight, heightScale);
  
  xAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("x", xAxisLabelX)
      .attr("y", xAxisLabelY - ((xAxisLabelLines.length - 1 - i) * lineHeights.axisLabel))
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // CAPTION
  // ========================================
  const captionY = PlotHelpers.getCaptionY(height, heightScale);
  
  captionLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-caption")
      .attr("x", 20)
      .attr("y", captionY - ((captionLines.length - 1 - i) * lineHeights.caption))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.caption}px`)
      .text(line);
  });
  
  return svg.node();
}


// ------------------------------------------------------------
// plot_l_area
// ------------------------------------------------------------
function plot_l_area(l_area, {
  cityName = globalCity, 
  countryName = globalCountry,
  width,
  height
} = {}) {
  
  // ========================================
  // DATA PREPARATION
  // ========================================
  const sortedData = l_area.slice().sort((a, b) => 
    PlotHelpers.parseLAreaRange(a.bin) - PlotHelpers.parseLAreaRange(b.bin)
  );

  // color mapping for liquefaction susceptibility
  const lAreaColorMap = {
    "1": "#f6efe5",
    "2": "#f1cda8",
    "3": "#e9ac81",
    "4": "#dc8b6d",
    "5": "#b27365"
  };
  const defaultColor = "#999999"; // (fallback gray if no color map match)

  // map from bins to susceptibility values
  const binToSusceptibilityMap = {
    "Very low": "1",
    "Low": "2", 
    "Medium": "3", 
    "High": "4", 
    "Very high": "5"
  };
  
  const allLAreaBins = sortedData.map(d => d.bin);
  
  // complete data with gray bars for visual completeness
  const completeData = allLAreaBins.map(bin => {
    const existing = sortedData.find(d => d.bin === bin);
    return existing || { bin, count: 0, percentage: 0 };
  });

  // ========================================
  // STYLING CALCULATIONS
  // ========================================
  // (use helper functions from plot-helpers.js for all styling calculations)
  const fontSizes = PlotHelpers.calculateFontSizes(width, height);
  const lineHeights = PlotHelpers.calculateLineHeights(fontSizes);
  
  // text content
  const titleText = "Liquefaction Susceptibility";
  const titleLocation = countryName ? `${cityName}, ${countryName}` : cityName;
  const xAxisLabelText = "Liquefaction Susceptibility";
  const yAxisLabelText = "Percentage of Area (%)";
  const captionText = "test test test"; // (empty for this plot)
  
  // text wrapping
  const titleLines = PlotHelpers.wrapText(titleText, width - 40, `${fontSizes.title}px system-ui`);
  const subtitleLines = PlotHelpers.wrapText(titleLocation, width - 40, `${fontSizes.subtitle}px system-ui`);
  const xAxisLabelLines = PlotHelpers.wrapText(xAxisLabelText, width * 0.8, `${fontSizes.axisLabel}px system-ui`);
  const yAxisLabelLines = PlotHelpers.wrapText(yAxisLabelText, height * 0.6, `${fontSizes.axisLabel}px system-ui`);
  const captionLines = PlotHelpers.wrapText(captionText, width - 40, `${fontSizes.caption}px system-ui`);

  // calculate text dimensions for margins
  const titleHeight = titleLines.length * lineHeights.title;
  const subtitleHeight = subtitleLines.length * lineHeights.subtitle;
  const xAxisLabelHeight = xAxisLabelLines.length * lineHeights.axisLabel;
  const captionHeight = captionLines.length * lineHeights.caption;
  const yAxisLabelWidth = yAxisLabelLines.length * lineHeights.axisLabel;

  // calculate margins using helper
  const margin = PlotHelpers.calculateMargins(width, height, {
    titleHeight,
    subtitleHeight,
    xAxisLabelHeight,
    captionHeight,
    yAxisLabelWidth
  });
  
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  
  // ========================================
  // SCALES
  // ========================================
  const xScale = d3.scaleBand()
    .domain(completeData.map(d => d.bin))
    .range([0, innerWidth])
    .padding(0.1);
    
  const yScale = d3.scaleLinear()
    .domain([0, 100])
    .range([innerHeight, 0]);

  // ========================================
  // SVG CREATION
  // ========================================
  const svg = d3.create("svg")
    .attr("viewBox", `0 0 ${width} ${height}`)
    .attr("preserveAspectRatio", "xMidYMid meet")
    .style("width", "100%")
    .style("height", "auto")
    .style("max-width", `${width}px`);

  const g = svg.append("g")
    .attr("transform", `translate(${margin.left},${margin.top})`);
  
  // ========================================
  // Y-AXIS
  // ========================================
  const yTicks = PlotHelpers.calculateYTicks(innerHeight);
  const yAxisGroup = g.append("g").attr("class", "y-axis");
  const yAxisCall = d3.axisLeft(yScale)
    .ticks(yTicks)
    .tickSizeOuter(0)
    .tickSizeInner(-innerWidth)
    .tickFormat(d3.format("~s"));

  yAxisGroup.call(yAxisCall);
  yAxisGroup.selectAll(".tick text")
    .style("font-size", `${fontSizes.yAxisTick}px`);
    
  // ========================================
  // BARS
  // ========================================
  // gray background bars
  g.selectAll(".background-bar")
    .data(completeData)
    .enter().append("rect")
    .attr("class", "background-bar")
    .attr("x", d => xScale(d.bin))
    .attr("width", xScale.bandwidth())
    .attr("y", 0)
    .attr("height", innerHeight);
    
  // data bars with smart tooltips
  g.selectAll(".data-bar")
    .data(completeData.filter(d => d.percentage > 0))
    .enter().append("rect")
    .attr("class", "data-bar")
    .attr("x", d => xScale(d.bin))
    .attr("width", xScale.bandwidth())
    .attr("y", d => yScale(d.percentage))
    .attr("height", d => innerHeight - yScale(d.percentage))
    .attr("fill", d => lAreaColorMap[d.susceptibility] || defaultColor)
    .attr("fill-opacity", 1)
    .attr("stroke", d => d3.color(lAreaColorMap[d.susceptibility] || defaultColor).darker(0.3))
    .attr("stroke-width", 1)
    .style("cursor", "default")
    .on("mouseover", function(event, d) {
      d3.selectAll(".d3-tooltip").remove();

      const tooltip = d3.select("body").append("div")
        .attr("class", "d3-tooltip")
        .style("opacity", 0);
        
      const html = `<div>Liquefaction Susceptibility: ${d.susceptibility}</div><div>Percentage of Area: ${d.percentage.toFixed(1)}%</div>`;
      
      // calculate position to avoid bleeding off screen
      const tooltipWidth = 220;
      const windowWidth = window.innerWidth;
      const mouseX = event.pageX;
      
      let leftPos = mouseX + 10;
      if (leftPos + tooltipWidth > windowWidth) {
        leftPos = mouseX - tooltipWidth - 10;
      }
      
      tooltip
        .html(html)
        .style("left", leftPos + "px")
        .style("top", (event.pageY - 35) + "px")
        .transition()
        .duration(200)
        .style("opacity", 1);
    })
    .on("mousemove", function(event) {
      const tooltip = d3.select(".d3-tooltip");
      if (!tooltip.empty()) {
        const tooltipWidth = 220;
        const windowWidth = window.innerWidth;
        const mouseX = event.pageX;
        
        let leftPos = mouseX + 10;
        if (leftPos + tooltipWidth > windowWidth) {
          leftPos = mouseX - tooltipWidth - 10;
        }
        
        tooltip
          .style("left", leftPos + "px")
          .style("top", (event.pageY - 35) + "px");
      }
    })
    .on("mouseout", function() {
      d3.select(".d3-tooltip")
        .transition()
        .duration(200)
        .style("opacity", 0)
        .remove();
    });

  // ========================================
  // BAR PERCENTAGE LABELS
  // ========================================
  g.selectAll(".bar-label")
    .data(completeData)
    .enter().append("text")
    .attr("class", "plot-bar-label")
    .attr("x", d => xScale(d.bin) + xScale.bandwidth()/2)
    .attr("y", d => d.percentage > 0 ? yScale(d.percentage) - 8 : innerHeight/2)
    .attr("text-anchor", "middle")
    .attr("fill", d => d.percentage > 0 ? "black" : "#6c757d")
    .style("font-size", `${fontSizes.barLabel}px`)
    .attr("font-style", d => d.percentage > 0 ? "normal" : "italic")
    .text(d => d.percentage > 0 ? `${d.percentage.toFixed(1)}%` : "")
    .style("display", d => d.percentage > 2 || d.percentage === 0 ? "block" : "none");

  // ========================================
  // X-AXIS
  // ========================================
  const xAxisGroup = g.append("g")
    .attr("class", "x-axis")
    .attr("transform", `translate(0,${innerHeight})`);
    
  xAxisGroup.call(d3.axisBottom(xScale)
    .tickSizeOuter(0)
    .tickSizeInner(0));
 
  // x-axis tick labels with wrapping
  const barWidth = xScale.bandwidth();
  const xAxisTickSize = PlotHelpers.calculateXAxisTickSize(barWidth);
  
  xAxisGroup.selectAll(".tick text")
    .each(function(d) {
      const text = d3.select(this);
      const labelText = text.text();
      
      text.style("font-size", `${xAxisTickSize}px`);
      
      const lines = PlotHelpers.wrapBarLabel(labelText, barWidth, `${xAxisTickSize}px system-ui`);
      text.text(null);
      
      lines.forEach((line, i) => {
        text.append("tspan")
          .attr("x", 0)
          .attr("dy", i === 0 ? "1.2em" : "1.1em")
          .text(line);
      });
    });
    
  // ========================================
  // TITLE
  // ========================================
  const heightScale = height / PlotHelpers.PLOT_BASE.HEIGHT;
  const titleY = PlotHelpers.getTitleY(height, heightScale);
  
  titleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-title")
      .attr("x", 20)
      .attr("y", titleY + (i * lineHeights.title))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.title}px`)
      .text(line);
  });
    
  // ========================================
  // SUBTITLE
  // ========================================
  const subtitleY = PlotHelpers.getSubtitleY(titleY, titleLines.length, lineHeights.title, heightScale);
  
  subtitleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-subtitle")
      .attr("x", 20)
      .attr("y", subtitleY + (i * lineHeights.subtitle))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.subtitle}px`)
      .text(line);
  });
    
  // ========================================
  // Y-AXIS LABEL
  // ========================================
  const widthScale = width / PlotHelpers.PLOT_BASE.WIDTH;
  const yAxisLabelX = -(margin.top + innerHeight/2);
  const yAxisLabelY = PlotHelpers.getYAxisLabelY(widthScale);
  
  yAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("transform", "rotate(-90)")
      .attr("y", yAxisLabelY + (i * lineHeights.axisLabel))
      .attr("x", yAxisLabelX)
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // X-AXIS LABEL
  // ========================================
  const xAxisLabelX = margin.left + innerWidth/2;
  const xAxisLabelY = PlotHelpers.getXAxisLabelY(height, captionHeight, heightScale);
  
  xAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("x", xAxisLabelX)
      .attr("y", xAxisLabelY - ((xAxisLabelLines.length - 1 - i) * lineHeights.axisLabel))
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // CAPTION
  // ========================================
  // (empty for this plot)
  if (captionText) {
    const captionY = PlotHelpers.getCaptionY(height, heightScale);
    
    captionLines.forEach((line, i) => {
      svg.append("text")
        .attr("class", "plot-caption")
        .attr("x", 20)
        .attr("y", captionY - ((captionLines.length - 1 - i) * lineHeights.caption))
        .attr("text-anchor", "start")
        .style("font-size", `${fontSizes.caption}px`)
        .text(line);
    });
  }
  
  return svg.node();
}


// ------------------------------------------------------------
// plot_fwi
// ------------------------------------------------------------
function plot_fwi(fwi, {
  cityName = globalCity,
  countryName = globalCountry,
  width,
  height
} = {}) {
  
  // ========================================
  // DATA PREPARATION
  // ========================================
  // ensure fwi is a number
  fwi.forEach(d => {
    d.fwi = +(d.fwi ?? d.pctile_95);   // data column is pctile_95 (95th percentile FWI per week)
    // derive month name from week number when the data has none (fwi_weekly_95 has
    // only week + pctile_95): month of the week's start date (week 1 = Jan 1)
    if (d.monthName == null && d.week != null) {
      const weekStart = new Date(Date.UTC(2021, 0, 1 + (d.week - 1) * 7));
      d.monthName = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][weekStart.getUTCMonth()];
    }
  });
  
  // EFFIS FWI risk category thresholds
  const riskCategories = [
    { name: "Very Low", min: 0, max: 5.2, color: "#4CAF50", opacity: 0.40 },
    { name: "Low", min: 5.2, max: 11.2, color: "#8BC34A", opacity: 0.40 },
    { name: "Moderate", min: 11.2, max: 21.3, color: "#FFC107", opacity: 0.40 },
    { name: "High", min: 21.3, max: 38.0, color: "#FF9800", opacity: 0.40 },
    { name: "Very High", min: 38.0, max: 50, color: "#F44336", opacity: 0.40 },
    { name: "Extreme", min: 50, max: Infinity, color: "#8B0000", opacity: 0.40 }
  ];
  
  // determine which risk categories are relevant based on data range
  const maxFWI = Math.max(...fwi.map(d => d.fwi));
  const yDomain = [0, maxFWI * 1.1];
  
  // filter categories that intersect with the visible range
  const visibleCategories = riskCategories.filter(cat => 
    cat.min < yDomain[1] && cat.max > yDomain[0]
  );
  
  // ========================================
  // STYLING CALCULATIONS
  // ========================================
  // (use helper functions from plot-helpers.js for all styling calculations)
  const fontSizes = PlotHelpers.calculateFontSizes(width, height);
  const lineHeights = PlotHelpers.calculateLineHeights(fontSizes);
  
  // text content
  const titleText = "Fire Weather Index (FWI), January - December";
  const titleLocation = countryName ? `${cityName}, ${countryName}` : cityName;
  const xAxisLabelText = "Month";
  const yAxisLabelText = "95th Percentile FWI";
  const captionText = "Data: NASA Global Fire Weather Database (GFWED) | Risk Classification: EFFIS/Copernicus Emergency Management Service | Note: Thresholds represent international standard; regional variation may apply";
  
  // text wrapping
  const titleLines = PlotHelpers.wrapText(titleText, width - 40, `${fontSizes.title}px system-ui`);
  const subtitleLines = PlotHelpers.wrapText(titleLocation, width - 40, `${fontSizes.subtitle}px system-ui`);
  const xAxisLabelLines = PlotHelpers.wrapText(xAxisLabelText, width * 0.8, `${fontSizes.axisLabel}px system-ui`);
  const yAxisLabelLines = PlotHelpers.wrapText(yAxisLabelText, height * 0.6, `${fontSizes.axisLabel}px system-ui`);
  const captionLines = PlotHelpers.wrapText(captionText, width - 40, `${fontSizes.caption}px system-ui`);

  // calculate text dimensions for margins
  const titleHeight = titleLines.length * lineHeights.title;
  const subtitleHeight = subtitleLines.length * lineHeights.subtitle;
  const xAxisLabelHeight = xAxisLabelLines.length * lineHeights.axisLabel;
  const captionHeight = captionLines.length * lineHeights.caption;
  const yAxisLabelWidth = yAxisLabelLines.length * lineHeights.axisLabel;

  // calculate margins using helper
  const margin = PlotHelpers.calculateMargins(width, height, {
    titleHeight,
    subtitleHeight,
    xAxisLabelHeight,
    captionHeight,
    yAxisLabelWidth
  });
  
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  
  // ========================================
  // SCALES
  // ========================================
  const xScale = d3.scaleLinear()
    .domain([1, fwi.length])
    .range([0, innerWidth]);
    
  const yScale = d3.scaleLinear()
    .domain(yDomain)
    .range([innerHeight, 0]);

  // ========================================
  // SVG CREATION
  // ========================================
  const svg = d3.create("svg")
    .attr("viewBox", `0 0 ${width} ${height}`)
    .attr("preserveAspectRatio", "xMidYMid meet")
    .style("width", "100%")
    .style("height", "auto")
    .style("max-width", `${width}px`);

  const g = svg.append("g")
    .attr("transform", `translate(${margin.left},${margin.top})`);
  
  // ========================================
  // RISK BANDS
  // ========================================
  // (i.e., background)
  visibleCategories.forEach(cat => {
    g.append("rect")
      .attr("x", xScale(1))
      .attr("y", yScale(Math.min(cat.max, yDomain[1])))
      .attr("width", xScale(fwi.length) - xScale(1))
      .attr("height", yScale(Math.max(cat.min, yDomain[0])) - yScale(Math.min(cat.max, yDomain[1])))
      .attr("fill", cat.color)
      .attr("fill-opacity", cat.opacity)
      .attr("stroke", cat.color)
      .attr("stroke-opacity", 0.3)
      .attr("stroke-width", 0.5);
  });
  
  // ========================================
  // RISK LABELS
  // ========================================
  visibleCategories
    .filter(cat => {
      const bandHeight = Math.min(cat.max, yDomain[1]) - Math.max(cat.min, yDomain[0]);
      const pixelHeight = (bandHeight / yDomain[1]) * innerHeight;
      return pixelHeight > 25;
    })
    .forEach(cat => {
      const yPos = (yScale(Math.max(cat.min, yDomain[0])) + yScale(Math.min(cat.max, yDomain[1]))) / 2;
      g.append("text")
        .attr("x", innerWidth - 5)
        .attr("y", yPos)
        .attr("text-anchor", "end")
        .attr("dominant-baseline", "middle")
        .attr("fill", cat.color === "#FFC107" ? "#B8860B" : cat.color)
        .attr("font-size", `${Math.max(9, Math.min(12, width / 60))}px`)
        .attr("font-weight", "bold")
        .attr("font-family", "system-ui")
        .text(cat.name);
    });
  
  // ========================================
  // Y-AXIS
  // ========================================
  const yTicks = PlotHelpers.calculateYTicks(innerHeight);
  const yAxisGroup = g.append("g").attr("class", "y-axis");
  const yAxisCall = d3.axisLeft(yScale)
    .ticks(yTicks)
    .tickSizeOuter(0)
    .tickSizeInner(0); // (no grid lines)

  yAxisGroup.call(yAxisCall);
  yAxisGroup.selectAll(".tick text")
    .style("font-size", `${fontSizes.yAxisTick}px`);
  
  // ========================================
  // X-AXIS
  // ========================================
  // get all month boundary weeks (first week of each month)
  const allMonthTicks = d3.range(1, 53).filter(week => {
    const currentMonth = fwi[week-1]?.monthName;
    const prevMonth = week > 1 ? fwi[week-2]?.monthName : null;
    return currentMonth !== prevMonth;
  });
  
  // calculate available space per month
  const totalMonths = allMonthTicks.length;
  const availableSpacePerMonth = innerWidth / totalMonths;
  
  // determine tick interval (show every nth month)
  let tickInterval;
  if (availableSpacePerMonth < 60) {
    tickInterval = 3; // (show every 3rd month (Jan, Apr, Jul, Oct))
  } else if (availableSpacePerMonth < 80) {
    tickInterval = 2; // (show every 2nd month)
  } else {
    tickInterval = 1; // (show all months)
  }
  
  // filter month ticks based on interval
  const filteredMonthTicks = allMonthTicks.filter((tick, index) => index % tickInterval === 0);
  
  const xAxisGroup = g.append("g")
    .attr("class", "x-axis")
    .attr("transform", `translate(0,${innerHeight})`);
    
  xAxisGroup.call(d3.axisBottom(xScale)
    .tickValues(filteredMonthTicks)
    .tickFormat(d => {
      const index = Math.round(d) - 1;
      if (index >= 0 && index < fwi.length) {
        return fwi[index].monthName;
      }
      return "";
    })
    .tickSizeOuter(0)
    .tickSizeInner(0)); // (no grid lines)

  xAxisGroup.selectAll(".tick text")
    .style("font-size", `${fontSizes.xAxisTick}px`);
  
  // ========================================
  // LINE
  // ========================================
  const line = d3.line()
    .x(d => xScale(d.week))
    .y(d => yScale(d.fwi));
    
  g.append("path")
    .datum(fwi)
    .attr("fill", "none")
    .attr("stroke", "black")
    .attr("stroke-width", Math.max(1.5, Math.min(3, width / 400)))
    .attr("d", line);
  
  // ========================================
  // DOTS (INVISIBLE)
  // ========================================
  // (invisible dots for tooltips)
  g.selectAll(".dot")
    .data(fwi)
    .enter().append("circle")
    .attr("cx", d => xScale(d.week))
    .attr("cy", d => yScale(d.fwi))
    .attr("r", 3)
    .attr("fill", "transparent")
    .style("cursor", "default")
    .on("mouseover", function(event, d) {
      d3.selectAll(".d3-tooltip").remove();
      
      // determine risk category
      const fwiValue = d.fwi;
      const riskCategory = riskCategories.find(cat => 
        fwiValue >= cat.min && fwiValue < cat.max
      ) || riskCategories[riskCategories.length - 1];

      const tooltip = d3.select("body").append("div")
        .attr("class", "d3-tooltip")
        .style("opacity", 0);
        
      const html = `<div>Month: ${d.monthName}</div><div>FWI: ${fwiValue.toFixed(2)}</div><div>Risk Level: ${riskCategory.name}</div><div>&nbsp;</div><div style="font-style: italic;">Only 5% of ${d.monthName} days exceeded this level</div>`;
      
      const tooltipWidth = 280;
      const windowWidth = window.innerWidth;
      const mouseX = event.pageX;
      
      let leftPos = mouseX + 10;
      if (leftPos + tooltipWidth > windowWidth) {
        leftPos = mouseX - tooltipWidth - 10;
      }
      
      tooltip
        .html(html)
        .style("left", leftPos + "px")
        .style("top", (event.pageY - 35) + "px")
        .transition()
        .duration(200)
        .style("opacity", 1);
    })
    .on("mousemove", function(event) {
      const tooltip = d3.select(".d3-tooltip");
      if (!tooltip.empty()) {
        const tooltipWidth = 280;
        const windowWidth = window.innerWidth;
        const mouseX = event.pageX;
        
        let leftPos = mouseX + 10;
        if (leftPos + tooltipWidth > windowWidth) {
          leftPos = mouseX - tooltipWidth - 10;
        }
        
        tooltip
          .style("left", leftPos + "px")
          .style("top", (event.pageY - 35) + "px");
      }
    })
    .on("mouseout", function() {
      d3.select(".d3-tooltip")
        .transition()
        .duration(200)
        .style("opacity", 0)
        .remove();
    });
  
  // ========================================
  // TITLE
  // ========================================
  const heightScale = height / PlotHelpers.PLOT_BASE.HEIGHT;
  const titleY = PlotHelpers.getTitleY(height, heightScale);
  
  titleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-title")
      .attr("x", 20)
      .attr("y", titleY + (i * lineHeights.title))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.title}px`)
      .text(line);
  });
    
  // ========================================
  // SUBTITLE
  // ========================================
  const subtitleY = PlotHelpers.getSubtitleY(titleY, titleLines.length, lineHeights.title, heightScale);
  
  subtitleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-subtitle")
      .attr("x", 20)
      .attr("y", subtitleY + (i * lineHeights.subtitle))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.subtitle}px`)
      .text(line);
  });
    
  // ========================================
  // Y-AXIS LABEL
  // ========================================
  const widthScale = width / PlotHelpers.PLOT_BASE.WIDTH;
  const yAxisLabelX = -(margin.top + innerHeight/2);
  const yAxisLabelY = PlotHelpers.getYAxisLabelY(widthScale);
  
  yAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("transform", "rotate(-90)")
      .attr("y", yAxisLabelY + (i * lineHeights.axisLabel))
      .attr("x", yAxisLabelX)
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // X-AXIS LABEL
  // ========================================
  const xAxisLabelX = margin.left + innerWidth/2;
  const xAxisLabelY = PlotHelpers.getXAxisLabelY(height, captionHeight, heightScale);
  
  xAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("x", xAxisLabelX)
      .attr("y", xAxisLabelY - ((xAxisLabelLines.length - 1 - i) * lineHeights.axisLabel))
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // CAPTION
  // ========================================
  const captionY = PlotHelpers.getCaptionY(height, heightScale);
  
  captionLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-caption")
      .attr("x", 20)
      .attr("y", captionY - ((captionLines.length - 1 - i) * lineHeights.caption))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.caption}px`)
      .text(line);
  });
  
  return svg.node();
}


// ------------------------------------------------------------
// plot_fwi_d
// ------------------------------------------------------------
function plot_fwi_d(fwi, {
  cityName = globalCity,
  countryName = globalCountry,
  width,
  height,
  showPercentages = true
} = {}) {
  
  // ========================================
  // DATA PREPARATION
  // ========================================
  if (!fwi || !fwi.length) return null;  // no data -> render nothing
  // weekly FWI tables (fwi_weekly_95) have only week + pctile_95, no danger level:
  // derive it from the value using the same thresholds as plot_fwi (EFFIS classes)
  fwi = fwi.map(d => {
    if (d.danger != null) return d;
    const v = +(d.fwi ?? d.pctile_95);
    const danger = v >= 50 ? "Extreme" : v >= 38 ? "Very high" : v >= 21.3 ? "High"
                 : v >= 11.2 ? "Moderate" : v >= 5.2 ? "Low" : "Very low";   // same labels as the danger column
    return { ...d, danger };
  });
  // count occurrences of each danger level
  const dangerCounts = d3.rollup(fwi, v => v.length, d => d.danger);
  
  // define all possible danger levels in order
  const allDangerLevels = [
    "Extreme Risk", "Very High Risk", "High Risk", "Moderate Risk", "Low Risk", "Very Low Risk"
  ];
  
  // danger mapping
  const dangerMapping = {
    "Extreme Risk": "Extreme",
    "Very High Risk": "Very high",
    "High Risk": "High",
    "Moderate Risk": "Moderate",
    "Low Risk": "Low",
    "Very Low Risk": "Very low"
  };
  
  // data array with counts and percentages
  const distributionData = allDangerLevels.map(level => ({
    danger: level,
    count: dangerCounts.get(dangerMapping[level]) || 0,
    percentage: ((dangerCounts.get(dangerMapping[level]) || 0) / fwi.length * 100)
  }));
  
  // color mapping for danger levels
  const colorMap = {
    "Extreme Risk": "#8B0000",
    "Very High Risk": "#F44336",
    "High Risk": "#FF9800",
    "Moderate Risk": "#FFC107",
    "Low Risk": "#8BC34A",
    "Very Low Risk": "#4CAF50"
  };
  
  // ========================================
  // STYLING CALCULATIONS
  // ========================================
  // (use helper functions from plot-helpers.js for all styling calculations)
  const fontSizes = PlotHelpers.calculateFontSizes(width, height);
  const lineHeights = PlotHelpers.calculateLineHeights(fontSizes);
  const dynamicScale = PlotHelpers.calculateDynamicScale(width);
  const showValueLabels = PlotHelpers.shouldShowBarLabels(width);
  const labelFontSize = PlotHelpers.calculateBarChartLabelFontSize(dynamicScale);
  
  // text content
  const titleText = "Fire Weather Index (FWI) Danger Level Distribution";
  const titleLocation = countryName ? `${cityName}, ${countryName} (${fwi.length}-week period)` : `${cityName} (${fwi.length}-week period)`;
  const xAxisLabelText = "Weeks";
  const yAxisLabelText = "Danger Level";
  const captionText = "Data: NASA Global Fire Weather Database (GFWED) | Risk Classification: EFFIS/Copernicus Emergency Management Service | Note: Thresholds represent international standard; regional variation may apply";
  
  // text wrapping
  const titleLines = PlotHelpers.wrapText(titleText, width - 40, `${fontSizes.title}px system-ui`);
  const subtitleLines = PlotHelpers.wrapText(titleLocation, width - 40, `${fontSizes.subtitle}px system-ui`);
  const xAxisLabelLines = PlotHelpers.wrapText(xAxisLabelText, width * 0.8, `${fontSizes.axisLabel}px system-ui`);
  const yAxisLabelLines = PlotHelpers.wrapText(yAxisLabelText, height * 0.6, `${fontSizes.axisLabel}px system-ui`);
  const captionLines = PlotHelpers.wrapText(captionText, width - 40, `${fontSizes.caption}px system-ui`);

  // calculate text dimensions for margins
  const titleHeight = titleLines.length * lineHeights.title;
  const subtitleHeight = subtitleLines.length * lineHeights.subtitle;
  const xAxisLabelHeight = xAxisLabelLines.length * lineHeights.axisLabel;
  const captionHeight = captionLines.length * lineHeights.caption;
  const yAxisLabelWidth = yAxisLabelLines.length * lineHeights.axisLabel;

  // calculate margins using helpers
  const baseMargin = PlotHelpers.calculateMargins(width, height, {
    titleHeight,
    subtitleHeight,
    xAxisLabelHeight,
    captionHeight,
    yAxisLabelWidth
  });
  
  const margin = PlotHelpers.calculateBarChartMargins(baseMargin, dynamicScale, showValueLabels);
  
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  
  // ========================================
  // SCALES
  // ========================================
  // dynamic domain: use actual max weeks in the data (usually 52, sometimes 53)
  const domainMax = PlotHelpers.calculateTimePeriodDomain(fwi, 'week');
  
  const xScale = d3.scaleLinear()
    .domain([0, domainMax])
    .range([0, innerWidth]);
  
  const yScale = d3.scaleBand()
    .domain(allDangerLevels)
    .range([0, innerHeight])
    .padding(0.2);

  // ========================================
  // SVG CREATION
  // ========================================
  const svg = d3.create("svg")
    .attr("viewBox", `0 0 ${width} ${height}`)
    .attr("preserveAspectRatio", "xMidYMid meet")
    .style("width", "100%")
    .style("height", "auto")
    .style("max-width", `${width}px`);

  const g = svg.append("g")
    .attr("transform", `translate(${margin.left},${margin.top})`);
  
  // ========================================
  // GRID LINES
  // ========================================
  const xAxisGrid = d3.axisBottom(xScale)
    .ticks(Math.max(4, Math.min(10, Math.floor(innerWidth / 80))))
    .tickSize(innerHeight)
    .tickFormat("");
  
  g.append("g")
    .attr("class", "grid")
    .call(xAxisGrid)
    .call(g => g.select(".domain").remove())
    .call(g => g.selectAll(".tick line")
      .attr("stroke", "#f0f0f0")
      .attr("stroke-opacity", 1)
      .attr("stroke-width", 1));
  
  // ========================================
  // BACKGROUND "DUMMY" BARS
  // ========================================
  g.selectAll(".dummy-bar")
    .data(distributionData)
    .enter().append("rect")
    .attr("class", "dummy-bar")
    .attr("x", 0)
    .attr("y", d => yScale(d.danger))
    .attr("width", xScale(domainMax))
    .attr("height", yScale.bandwidth())
    .attr("fill", "#f8f9fa")
    .attr("fill-opacity", 0.3)
    .attr("stroke", "#dee2e6")
    .attr("stroke-width", Math.max(0.5, 1 * dynamicScale));
  
  // ========================================
  // DATA BARS
  // ========================================
  g.selectAll(".data-bar")
    .data(distributionData.filter(d => d.count > 0))
    .enter().append("rect")
    .attr("class", "data-bar")
    .attr("x", 0)
    .attr("y", d => yScale(d.danger))
    .attr("width", d => xScale(d.count))
    .attr("height", yScale.bandwidth())
    .attr("fill", d => colorMap[d.danger])
    .attr("fill-opacity", 0.40)
    .attr("stroke", "white")
    .attr("stroke-opacity", 0.3)
    .attr("stroke-width", Math.max(0.5, 1 * dynamicScale));
  
  // ========================================
  // VALUE LABELS
  // ========================================
  // (outside bars - only if wide enough)
  if (showValueLabels) {
    g.selectAll(".label")
      .data(distributionData)
      .enter().append("text")
      .attr("class", "label")
      .attr("x", xScale(domainMax) + 10)
      .attr("y", d => yScale(d.danger) + yScale.bandwidth() / 2)
      .attr("text-anchor", "start")
      .attr("dominant-baseline", "middle")
      .attr("fill", d => d.count > 0 ? "black" : "#6c757d")
      .attr("font-size", `${Math.max(9, Math.min(13, 11 * dynamicScale))}px`)
      .attr("font-family", "system-ui")
      .attr("font-style", d => d.count > 0 ? "normal" : "italic")
      .text(d => d.count > 0 ?
        (showPercentages ? `${d.count} weeks (${d.percentage.toFixed(1)}%)` : `${d.count} weeks`) :
        "0 weeks (0.0%)");
  }
  
  // ========================================
  // Y-AXIS
  // ========================================
  const yAxisGroup = g.append("g");
  yAxisGroup.call(d3.axisLeft(yScale)
    .tickSize(0)
    .tickPadding(10));
  yAxisGroup.select(".domain").remove();
  
  // calculate label box dimensions
  const labelBox = PlotHelpers.calculateYAxisLabelBox(margin.left, yScale.bandwidth());
  
  // replace text with wrapped text using foreignObject
  yAxisGroup.selectAll(".tick text").remove();
  yAxisGroup.selectAll(".tick")
    .append("foreignObject")
    .attr("width", labelBox.width)
    .attr("height", labelBox.height)
    .attr("x", labelBox.x)
    .attr("y", labelBox.y)
    .append("xhtml:div")
    .style("width", labelBox.width + "px")
    .style("height", labelBox.height + "px")
    .style("display", "flex")
    .style("align-items", "center")
    .style("justify-content", "flex-end")
    .style("font-size", `${labelFontSize}px`)
    .style("font-family", "system-ui")
    .style("text-align", "right")
    .style("line-height", "1.1")
    .style("word-wrap", "break-word")
    .style("overflow-wrap", "break-word")
    .style("hyphens", "auto")
    .html(d => d);
  
  // ========================================
  // X-AXIS
  // ========================================
  const xAxisGroup = g.append("g")
    .attr("transform", `translate(0,${innerHeight})`);
  xAxisGroup.call(d3.axisBottom(xScale)
    .ticks(Math.max(4, Math.min(10, Math.floor(innerWidth / 80))))
    .tickSize(Math.max(3, 6 * dynamicScale))
    .tickSizeOuter(0));
  xAxisGroup.select(".domain").attr("stroke", "currentColor");
  xAxisGroup.selectAll(".tick text")
    .attr("font-size", `${labelFontSize}px`)
    .attr("font-family", "system-ui")
    .attr("dy", "0.5em");
  
  // ========================================
  // TITLE
  // ========================================
  const heightScale = height / PlotHelpers.PLOT_BASE.HEIGHT;
  const titleY = PlotHelpers.getTitleY(height, heightScale);
  
  titleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-title")
      .attr("x", 20)
      .attr("y", titleY + (i * lineHeights.title))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.title}px`)
      .text(line);
  });
    
  // ========================================
  // SUBTITLE
  // ========================================
  const subtitleY = PlotHelpers.getSubtitleY(titleY, titleLines.length, lineHeights.title, heightScale);
  
  subtitleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-subtitle")
      .attr("x", 20)
      .attr("y", subtitleY + (i * lineHeights.subtitle))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.subtitle}px`)
      .text(line);
  });
    
  // ========================================
  // Y-AXIS LABEL
  // ========================================
  const widthScale = width / PlotHelpers.PLOT_BASE.WIDTH;
  const yAxisLabelX = -(margin.top + innerHeight/2);
  const yAxisLabelY = PlotHelpers.getYAxisLabelY(widthScale);
  
  yAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("transform", "rotate(-90)")
      .attr("y", yAxisLabelY + (i * lineHeights.axisLabel))
      .attr("x", yAxisLabelX)
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // X-AXIS LABEL
  // ========================================
  const xAxisLabelX = margin.left + innerWidth/2;
  const xAxisLabelY = PlotHelpers.getXAxisLabelY(height, captionHeight, heightScale);
  
  xAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("x", xAxisLabelX)
      .attr("y", xAxisLabelY - ((xAxisLabelLines.length - 1 - i) * lineHeights.axisLabel))
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // CAPTION
  // ========================================
  const captionY = PlotHelpers.getCaptionY(height, heightScale);
  
  captionLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-caption")
      .attr("x", 20)
      .attr("y", captionY - ((captionLines.length - 1 - i) * lineHeights.caption))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.caption}px`)
      .text(line);
  });
  
  return svg.node();
}


// ------------------------------------------------------------
// plot_uba_tracker - WSF Evolution Time Series
// ------------------------------------------------------------
function plot_uba_tracker(uba_tracker, {
  cityName = globalCity,
  countryName = globalCountry,
  width,
  height
} = {}) {
  
  // ========================================
  // DATA PREPARATION
  // ========================================
  // normalize: wsf_tracker.csv has year, month, cumulative_sq_km (readings ~twice a
  // year). Sort, map to the fields this chart reads, and build "Jun 2016" labels.
  const _mon = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  uba_tracker = uba_tracker.slice()
    .sort((a, b) => (+a.year - +b.year) || (+a.month - +b.month))
    .map((d, i) => ({ year: +d.year, month: +d.month,
                      uba: d.uba ?? (d.cumulative_sq_km != null ? +d.cumulative_sq_km : null),
                      yearMonth: d.yearMonth ?? i + 1,
                      monthYearName: d.monthYearName ?? `${_mon[+d.month - 1]} ${d.year}` }));

  // get month year range
  const minYear = d3.min(uba_tracker, d => d.year);
  const maxYear = d3.max(uba_tracker, d => d.year);

  // ========================================
  // STYLING CALCULATIONS
  // ========================================
  // (use helper functions from plot-helpers.js for all styling calculations)
  const fontSizes = PlotHelpers.calculateFontSizes(width, height);
  const lineHeights = PlotHelpers.calculateLineHeights(fontSizes);
  
  // text content
  const titleText = `Urban Built-up Area, ${minYear}-${maxYear}`;
  const titleLocation = cityName;
  const xAxisLabelText = "Year";
  const yAxisLabelText = "Urban Built-up Area (sq km)";
  const captionText = ""; // (empty for this plot)
  
  // text wrapping
  const titleLines = PlotHelpers.wrapText(titleText, width - 40, `${fontSizes.title}px system-ui`);
  const subtitleLines = PlotHelpers.wrapText(titleLocation, width - 40, `${fontSizes.subtitle}px system-ui`);
  const xAxisLabelLines = PlotHelpers.wrapText(xAxisLabelText, width * 0.8, `${fontSizes.axisLabel}px system-ui`);
  const yAxisLabelLines = PlotHelpers.wrapText(yAxisLabelText, height * 0.6, `${fontSizes.axisLabel}px system-ui`);
  const captionLines = PlotHelpers.wrapText(captionText, width - 40, `${fontSizes.caption}px system-ui`);

  // calculate text dimensions for margins
  const titleHeight = titleLines.length * lineHeights.title;
  const subtitleHeight = subtitleLines.length * lineHeights.subtitle;
  const xAxisLabelHeight = xAxisLabelLines.length * lineHeights.axisLabel;
  const captionHeight = captionLines.length * lineHeights.caption;
  const yAxisLabelWidth = yAxisLabelLines.length * lineHeights.axisLabel;

  // calculate margins using helper
  const margin = PlotHelpers.calculateMargins(width, height, {
    titleHeight,
    subtitleHeight,
    xAxisLabelHeight,
    captionHeight,
    yAxisLabelWidth
  });
  
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  
  // ========================================
  // SCALES
  // ========================================
  // (linear scales for line charts)
  const xScale = d3.scaleLinear()
    .domain([1, uba_tracker.length])
    .range([0, innerWidth]);
    
  const yScale = d3.scaleLinear()
    .domain([0, Math.max(...uba_tracker.map(d => d.uba)) * 1.1])
    .range([innerHeight, 0]);

  // ========================================
  // SVG CREATION
  // ========================================
  const svg = d3.create("svg")
    .attr("viewBox", `0 0 ${width} ${height}`)
    .attr("preserveAspectRatio", "xMidYMid meet")
    .style("width", "100%")
    .style("height", "auto")
    .style("max-width", `${width}px`);

  const g = svg.append("g")
    .attr("transform", `translate(${margin.left},${margin.top})`);
  
  // ========================================
  // Y-AXIS
  // ========================================
  const yTicks = PlotHelpers.calculateYTicks(innerHeight);
  const yAxisGroup = g.append("g").attr("class", "y-axis");
  const yAxisCall = d3.axisLeft(yScale)
    .ticks(yTicks)
    .tickSizeOuter(0)
    .tickSizeInner(-innerWidth)
    .tickFormat(d3.format("~s"));

  yAxisGroup.call(yAxisCall);
  yAxisGroup.selectAll(".tick text")
    .style("font-size", `${fontSizes.yAxisTick}px`);
  
  // ========================================
  // X-AXIS
  // ========================================
  // calculate tick positions for every "July" (month = 7)
  // one tick per year, at the reading closest to July (= July for monthly data,
  // June for the twice-yearly tracker data)
  const _closestToJuly = new Map();
  uba_tracker.forEach((d, i) => {
    const best = _closestToJuly.get(d.year);
    if (best === undefined || Math.abs(d.month - 7) < Math.abs(uba_tracker[best].month - 7)) _closestToJuly.set(d.year, i);
  });
  const allJulyIndices = [..._closestToJuly.values()].sort((a, b) => a - b);

  // calculate how many "July" labels can fit
  const maxTickCount = PlotHelpers.calculateXAxisTickCount(innerWidth);

  // if there are too many "July" labels, use the intelligent tick count
  let tickIndices;
  if (allJulyIndices.length <= maxTickCount) {
    // show all "July" labels (if they fit)
    tickIndices = allJulyIndices;
  } else {
    // show every nth "July" label so that they fit in maxTickCount
    const step = Math.ceil(allJulyIndices.length / maxTickCount);
    tickIndices = allJulyIndices.filter((_, i) => i % step === 0);
  }
  
  const xAxisGroup = g.append("g")
    .attr("class", "x-axis")
    .attr("transform", `translate(0,${innerHeight})`);
    
  xAxisGroup.call(d3.axisBottom(xScale)
    .tickValues(tickIndices.map(i => i + 1)) // +1 because yearMonth starts at 1
    .tickFormat(d => {
      const index = Math.round(d) - 1;
      if (index >= 0 && index < uba_tracker.length) {
        return uba_tracker[index].monthYearName;
      }
      return "";
    })
    .tickSizeOuter(0)
    .tickSizeInner(-innerHeight));

  // x-axis tick labels with wrapping
  const tickSpacing = innerWidth / tickIndices.length;
  xAxisGroup.selectAll(".tick text")
    .each(function() {
      const text = d3.select(this);
      const labelText = text.text();
      
      text.style("font-size", `${fontSizes.xAxisTick}px`);
      
      const lines = PlotHelpers.wrapLineChartLabel(labelText, tickSpacing, `${fontSizes.xAxisTick}px system-ui`);
      text.text(null);
      
      lines.forEach((line, i) => {
        text.append("tspan")
          .attr("x", 0)
          .attr("dy", i === 0 ? "1.2em" : "1.1em")
          .text(line);
      });
    });
  
  // ========================================
  // LINE
  // ========================================
  const line = d3.line()
    .defined(d => d.uba !== null) // (skip null values)
    .x(d => xScale(d.yearMonth))
    .y(d => yScale(d.uba));
    
  g.append("path")
    .datum(uba_tracker)
    .attr("fill", "none")
    .attr("stroke", "black")
    .attr("stroke-width", Math.max(1.5, Math.min(3, width / 400)))
    .attr("d", line);
  
  // ========================================
  // DOTS
  // ========================================
  g.selectAll(".dot")
    .data(uba_tracker.filter(d => d.uba !== null)) // (skip null values)
    .enter().append("circle")
    .attr("class", "dot")
    .attr("cx", d => xScale(d.yearMonth))
    .attr("cy", d => yScale(d.uba))
    .attr("r", Math.max(2, Math.min(3, width / 200)))
    .attr("fill", "black")
    .style("cursor", "default")
    .on("mouseover", function(event, d) {
      d3.selectAll(".d3-tooltip").remove();

      const tooltip = d3.select("body").append("div")
        .attr("class", "d3-tooltip")
        .style("opacity", 0);
        
      const html = `<div><strong>${d.monthYearName}</strong></div><div>Urban Built-up Area: ${d.uba.toFixed(2)} sq km</div>`;
      
      const tooltipWidth = 220;
      const windowWidth = window.innerWidth;
      const mouseX = event.pageX;
      
      let leftPos = mouseX + 10;
      if (leftPos + tooltipWidth > windowWidth) {
        leftPos = mouseX - tooltipWidth - 10;
      }
      
      tooltip
        .html(html)
        .style("left", leftPos + "px")
        .style("top", (event.pageY - 35) + "px")
        .transition()
        .duration(200)
        .style("opacity", 1);
    })
    .on("mousemove", function(event) {
      const tooltip = d3.select(".d3-tooltip");
      if (!tooltip.empty()) {
        const tooltipWidth = 220;
        const windowWidth = window.innerWidth;
        const mouseX = event.pageX;
        
        let leftPos = mouseX + 10;
        if (leftPos + tooltipWidth > windowWidth) {
          leftPos = mouseX - tooltipWidth - 10;
        }
        
        tooltip
          .style("left", leftPos + "px")
          .style("top", (event.pageY - 35) + "px");
      }
    })
    .on("mouseout", function() {
      d3.select(".d3-tooltip")
        .transition()
        .duration(200)
        .style("opacity", 0)
        .remove();
    });
  
  // ========================================
  // TITLE
  // ========================================
  const heightScale = height / PlotHelpers.PLOT_BASE.HEIGHT;
  const titleY = PlotHelpers.getTitleY(height, heightScale);
  
  titleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-title")
      .attr("x", 20)
      .attr("y", titleY + (i * lineHeights.title))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.title}px`)
      .text(line);
  });
    
  // ========================================
  // SUBTITLE
  // ========================================
  const subtitleY = PlotHelpers.getSubtitleY(titleY, titleLines.length, lineHeights.title, heightScale);
  
  subtitleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-subtitle")
      .attr("x", 20)
      .attr("y", subtitleY + (i * lineHeights.subtitle))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.subtitle}px`)
      .text(line);
  });
    
  // ========================================
  // Y-AXIS LABEL
  // ========================================
  const widthScale = width / PlotHelpers.PLOT_BASE.WIDTH;
  const yAxisLabelX = -(margin.top + innerHeight/2);
  const yAxisLabelY = PlotHelpers.getYAxisLabelY(widthScale);
  
  yAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("transform", "rotate(-90)")
      .attr("y", yAxisLabelY + (i * lineHeights.axisLabel))
      .attr("x", yAxisLabelX)
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // X-AXIS LABEL
  // ========================================
  const xAxisLabelX = margin.left + innerWidth/2;
  const xAxisLabelY = PlotHelpers.getXAxisLabelY(height, captionHeight, heightScale);
  
  xAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("x", xAxisLabelX)
      .attr("y", xAxisLabelY - ((xAxisLabelLines.length - 1 - i) * lineHeights.axisLabel))
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // CAPTION
  // ========================================
  // (empty for this plot)
  if (captionText) {
    const captionY = PlotHelpers.getCaptionY(height, heightScale);
    
    captionLines.forEach((line, i) => {
      svg.append("text")
        .attr("class", "plot-caption")
        .attr("x", 20)
        .attr("y", captionY - ((captionLines.length - 1 - i) * lineHeights.caption))
        .attr("text-anchor", "start")
        .style("font-size", `${fontSizes.caption}px`)
        .text(line);
    });
  }
  
  return svg.node();
}


// plot_ee - Earthquake Events
// ------------------------------------------------------------
function plot_ee(ee, {
  cityName = globalCity,
  countryName = globalCountry,
  width,
  height
} = {}) {
  
  // ========================================
  // DATA PREPARATION
  // ========================================
  if (!ee || !ee.length) return null;  // no data -> render nothing
  // newer earthquake CSVs carry one multi-line `text` column instead of line1-3:
  // split it so the labels below still work
  ee = ee.map(d => {
    if (d.line1 == null && d.text != null) {
      const [l1 = "", l2 = "", l3 = ""] = String(d.text).split("\n");
      return { ...d, line1: l1, line2: l2, line3: l3 };
    }
    return d;
  });
  // (no data preparation needed for this plot)
  
  // ========================================
  // STYLING CALCULATIONS
  // ========================================
  // (use helper functions from plot-helpers.js for all styling calculations)
  const fontSizes = PlotHelpers.calculateFontSizes(width, height);
  const lineHeights = PlotHelpers.calculateLineHeights(fontSizes);
  
  // text content
  const titleText = "Significant Earthquakes within 500 km since 1900";
  const titleLocation = countryName ? `${cityName}, ${countryName}` : cityName;
  const xAxisLabelText = `Distance from ${cityName} (km)`;
  const yAxisLabelText = "Year";
  const captionText = ""; // (empty for this plot)
  
  // text wrapping
  const titleLines = PlotHelpers.wrapText(titleText, width - 40, `${fontSizes.title}px system-ui`);
  const subtitleLines = PlotHelpers.wrapText(titleLocation, width - 40, `${fontSizes.subtitle}px system-ui`);
  const xAxisLabelLines = PlotHelpers.wrapText(xAxisLabelText, width * 0.8, `${fontSizes.axisLabel}px system-ui`);
  const yAxisLabelLines = PlotHelpers.wrapText(yAxisLabelText, height * 0.6, `${fontSizes.axisLabel}px system-ui`);
  const captionLines = PlotHelpers.wrapText(captionText, width - 40, `${fontSizes.caption}px system-ui`);

  // calculate text dimensions for margins
  const titleHeight = titleLines.length * lineHeights.title;
  const subtitleHeight = subtitleLines.length * lineHeights.subtitle;
  const xAxisLabelHeight = xAxisLabelLines.length * lineHeights.axisLabel;
  const captionHeight = captionLines.length * lineHeights.caption;
  const yAxisLabelWidth = yAxisLabelLines.length * lineHeights.axisLabel;

  // calculate margins using helper
  const margin = PlotHelpers.calculateMargins(width, height, {
    titleHeight,
    subtitleHeight,
    xAxisLabelHeight,
    captionHeight,
    yAxisLabelWidth
  });
  
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  
  // ========================================
  // SCALES
  // ========================================
  const xScale = d3.scaleLinear()
    .domain([0, 500])
    .range([0, innerWidth]);
    
  const yScale = d3.scaleLinear()
    .domain([1900, 2026])
    .range([innerHeight, 0]);
  
  // bubble radius scale (based on magnitude)
  const radiusRange = PlotHelpers.calculateBubbleRadiusRange(width);
  const magnitudes = ee.map(d => d.eqMagnitude).filter(d => d != null);
  const rScale = d3.scaleSqrt()
    .domain([Math.min(...magnitudes), Math.max(...magnitudes)])
    .range([
      Math.max(2, Math.min(5, width / 200)),
      Math.max(12, Math.min(25, width / 40))
    ]);

  // ========================================
  // SVG CREATION
  // ========================================
  const svg = d3.create("svg")
    .attr("viewBox", `0 0 ${width} ${height}`)
    .attr("preserveAspectRatio", "xMidYMid meet")
    .style("width", "100%")
    .style("height", "auto")
    .style("max-width", `${width}px`);

  const g = svg.append("g")
    .attr("transform", `translate(${margin.left},${margin.top})`);
  
  // ========================================
  // Y-AXIS
  // ========================================
  const yearTicks = PlotHelpers.calculateYearTicks(1900, 2025, width);
  const yAxisGroup = g.append("g").attr("class", "y-axis");
  const yAxisCall = d3.axisLeft(yScale)
    .tickValues(yearTicks.values)
    .tickFormat(d3.format("d"))
    .tickSizeOuter(0)
    .tickSizeInner(-innerWidth);

  yAxisGroup.call(yAxisCall);
  yAxisGroup.selectAll(".tick text")
    .style("font-size", `${fontSizes.yAxisTick}px`);
  
  // ========================================
  // X-AXIS
  // ========================================
  const xAxisGroup = g.append("g")
    .attr("class", "x-axis")
    .attr("transform", `translate(0,${innerHeight})`);
    
  xAxisGroup.call(d3.axisBottom(xScale)
    .ticks(Math.max(4, Math.min(10, Math.floor(width / 80))))
    .tickSizeOuter(0)
    .tickSizeInner(-innerHeight));

  xAxisGroup.selectAll(".tick text")
    .style("font-size", `${fontSizes.xAxisTick}px`);
  
  // ========================================
  // BUBBLES
  // ========================================
  g.selectAll(".dot")
    .data(ee)
    .enter().append("circle")
    .attr("class", "dot")
    .attr("cx", d => xScale(d.distance))
    .attr("cy", d => yScale(d.begin_year))
    .attr("r", d => rScale(d.eqMagnitude))
    .attr("fill", "grey")
    .attr("opacity", 0.5)
    .attr("stroke", "black")
    .attr("stroke-width", Math.max(0.5, Math.min(1.5, width / 500)))
    .style("cursor", "default")
    .on("mouseover", function(event, d) {
      d3.selectAll(".d3-tooltip").remove();

      const tooltip = d3.select("body").append("div")
        .attr("class", "d3-tooltip")
        .style("opacity", 0);
        
      const html = `
        <div><strong>${d.line1}</strong></div>
        <div style="margin-top: 8px;">${d.line2}</div>
        <div style="margin-top: 4px;">${d.line3}</div>
      `;
      
      const tooltipWidth = 280;
      const windowWidth = window.innerWidth;
      const mouseX = event.pageX;
      
      let leftPos = mouseX + 10;
      if (leftPos + tooltipWidth > windowWidth) {
        leftPos = mouseX - tooltipWidth - 10;
      }
      
      tooltip
        .html(html)
        .style("left", leftPos + "px")
        .style("top", (event.pageY - 35) + "px")
        .transition()
        .duration(200)
        .style("opacity", 1);
    })
    .on("mousemove", function(event) {
      const tooltip = d3.select(".d3-tooltip");
      if (!tooltip.empty()) {
        const tooltipWidth = 280;
        const windowWidth = window.innerWidth;
        const mouseX = event.pageX;
        
        let leftPos = mouseX + 10;
        if (leftPos + tooltipWidth > windowWidth) {
          leftPos = mouseX - tooltipWidth - 10;
        }
        
        tooltip
          .style("left", leftPos + "px")
          .style("top", (event.pageY - 35) + "px");
      }
    })
    .on("mouseout", function() {
      d3.select(".d3-tooltip")
        .transition()
        .duration(200)
        .style("opacity", 0)
        .remove();
    });
  
  // ========================================
  // TITLE
  // ========================================
  const heightScale = height / PlotHelpers.PLOT_BASE.HEIGHT;
  const titleY = PlotHelpers.getTitleY(height, heightScale);
  
  titleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-title")
      .attr("x", 20)
      .attr("y", titleY + (i * lineHeights.title))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.title}px`)
      .text(line);
  });
    
  // ========================================
  // SUBTITLE
  // ========================================
  const subtitleY = PlotHelpers.getSubtitleY(titleY, titleLines.length, lineHeights.title, heightScale);
  
  subtitleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-subtitle")
      .attr("x", 20)
      .attr("y", subtitleY + (i * lineHeights.subtitle))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.subtitle}px`)
      .text(line);
  });
    
  // ========================================
  // Y-AXIS LABEL
  // ========================================
  const widthScale = width / PlotHelpers.PLOT_BASE.WIDTH;
  const yAxisLabelX = -(margin.top + innerHeight/2);
  const yAxisLabelY = PlotHelpers.getYAxisLabelY(widthScale);
  
  yAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("transform", "rotate(-90)")
      .attr("y", yAxisLabelY + (i * lineHeights.axisLabel))
      .attr("x", yAxisLabelX)
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // X-AXIS LABEL
  // ========================================
  const xAxisLabelX = margin.left + innerWidth/2;
  const xAxisLabelY = PlotHelpers.getXAxisLabelY(height, captionHeight, heightScale);
  
  xAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("x", xAxisLabelX)
      .attr("y", xAxisLabelY - ((xAxisLabelLines.length - 1 - i) * lineHeights.axisLabel))
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // CAPTION
  // ========================================
  // (empty for this plot)
  if (captionText) {
    const captionY = PlotHelpers.getCaptionY(height, heightScale);
    
    captionLines.forEach((line, i) => {
      svg.append("text")
        .attr("class", "plot-caption")
        .attr("x", 20)
        .attr("y", captionY - ((captionLines.length - 1 - i) * lineHeights.caption))
        .attr("text-anchor", "start")
        .style("font-size", `${fontSizes.caption}px`)
        .text(line);
    });
  }
  
  return svg.node();
}


// ------------------------------------------------------------
// Exports
// ------------------------------------------------------------

// ------------------------------------------------------------
// Caroline's additional plots (cyclone events, deforestation)
// ------------------------------------------------------------
function plot_ce(ce, {
  cityName = globalCity,
  countryName = globalCountry,
  width,
  height
} = {}) {

  // ========================================
  // DATA PREPARATION
  // ========================================
  const sortedData = ce
    .slice()
    .sort((a, b) => a.year - b.year || a.month_start - b.month_start);

  const minYear = d3.min(sortedData, d => d.year);
  const maxYear = d3.max(sortedData, d => d.year);

  sortedData.forEach(d => {
    d._date = d.BEGAN ? new Date(d.BEGAN) : new Date(d.year, d.month_start - 1, 15);
  });

  // ========================================
  // STYLING CALCULATIONS
  // ========================================
  // (use helper functions from plot-helpers.js for all styling calculations)
  const fontSizes = PlotHelpers.calculateFontSizes(width, height);
  const lineHeights = PlotHelpers.calculateLineHeights(fontSizes);

  // text content
  const titleText = `Cyclone Events, ${minYear}–${maxYear}`;
  const titleLocation = countryName ? `${cityName}, ${countryName}` : cityName;
  const xAxisLabelText = "Year";
  const captionText = ""; // (empty for this plot)

  // text wrapping
  const titleLines = PlotHelpers.wrapText(titleText, width - 40, `${fontSizes.title}px system-ui`);
  const subtitleLines = PlotHelpers.wrapText(titleLocation, width - 40, `${fontSizes.subtitle}px system-ui`);
  const xAxisLabelLines = PlotHelpers.wrapText(xAxisLabelText, width * 0.8, `${fontSizes.axisLabel}px system-ui`);
  const captionLines = PlotHelpers.wrapText(captionText, width - 40, `${fontSizes.caption}px system-ui`);

  // calculate margins using helper
  const titleHeight = titleLines.length * lineHeights.title;
  const subtitleHeight = subtitleLines.length * lineHeights.subtitle;
  const xAxisLabelHeight = xAxisLabelLines.length * lineHeights.axisLabel;
  const captionHeight = captionLines.length * lineHeights.caption;

  const margin = PlotHelpers.calculateMargins(width, height, {
    titleHeight,
    subtitleHeight,
    xAxisLabelHeight,
    captionHeight,
    yAxisLabelWidth: 0
  });

  margin.left = Math.max(30, width * 0.04);

  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;

  // ========================================
  // SCALES
  // ========================================
  const domainStart = new Date(minYear - 1, 0, 1);
  const domainEnd = new Date(maxYear + 1, 11, 31);

  const xScale = d3.scaleTime()
    .domain([domainStart, domainEnd])
    .range([0, innerWidth]);

  const centerY = innerHeight / 2;

  // ========================================
  // SVG CREATION
  // ========================================
  const svg = d3.create("svg")
    .attr("viewBox", `0 0 ${width} ${height}`)
    .attr("preserveAspectRatio", "xMidYMid meet")
    .style("width", "100%")
    .style("height", "auto")
    .style("max-width", `${width}px`);

  const g = svg.append("g")
    .attr("transform", `translate(${margin.left},${margin.top})`);

  // ========================================
  // year tick calculation
  // ========================================
  const { interval, ticks: yearTicks } = PlotHelpers.calculateTimelineYearTicks(innerWidth, minYear, maxYear);

  // ========================================
  // GRID LINES
  // ========================================
  g.selectAll(".grid-line")
    .data(yearTicks)
    .enter().append("line")
    .attr("class", "grid-line")
    .attr("x1", d => xScale(d))
    .attr("x2", d => xScale(d))
    .attr("y1", 0)
    .attr("y2", innerHeight)
    .attr("stroke", "#f0f0f0")
    .attr("stroke-width", 1);

  // ========================================
  // CENTRAL TIMELINE AXIS LINE
  // ========================================
  g.append("line")
    .attr("x1", 0)
    .attr("x2", innerWidth)
    .attr("y1", centerY)
    .attr("y2", centerY)
    .attr("stroke", "currentColor")
    .attr("stroke-width", 1.5)
    .attr("stroke-opacity", 0.4);

  // tick marks along timeline
  yearTicks.forEach(tick => {
    g.append("line")
      .attr("x1", xScale(tick))
      .attr("x2", xScale(tick))
      .attr("y1", centerY - 4)
      .attr("y2", centerY + 4)
      .attr("stroke", "currentColor")
      .attr("stroke-width", 1)
      .attr("stroke-opacity", 0.5);
  });

  // ========================================
  // EVENT MARKERS
  // ========================================
  const stemLength = PlotHelpers.calculateTimelineStemLength(innerHeight);
  const dotRadius = PlotHelpers.calculateTimelineDotRadius(width);

  sortedData.forEach((d, i) => {
    const x = xScale(d._date);
    const above = i % 2 === 0;
    const yEnd = above ? centerY - stemLength : centerY + stemLength;

    // stem line
    g.append("line")
      .attr("x1", x)
      .attr("x2", x)
      .attr("y1", centerY)
      .attr("y2", yEnd)
      .attr("stroke", "black")
      .attr("stroke-width", 1.5)
      .attr("stroke-opacity", 0.7);

    // event dot with tooltip
    g.append("circle")
      .attr("cx", x)
      .attr("cy", yEnd)
      .attr("r", dotRadius)
      .attr("fill", "black")
      .attr("stroke", d3.color("black").darker(0.5))
      .attr("stroke-width", Math.max(0.5, Math.min(1.5, width / 500)))
      .style("cursor", "default")
      .on("mouseover", function(event) {
        d3.selectAll(".d3-tooltip").remove();

        const tooltip = d3.select("body").append("div")
          .attr("class", "d3-tooltip")
          .style("opacity", 0);

        const displayName = d.NAME === "NOT_NAMED" ? "Unnamed Storm" : d.NAME;

        const html = `
          <div><strong>${displayName}</strong></div>
          <div style="margin-top: 8px;">${d.month_start_name} ${d.year}</div>
          <div style="margin-top: 4px;">${d.max_scale}</div>
        `;

        const tooltipWidth = 280;
        const windowWidth = window.innerWidth;
        const mouseX = event.pageX;

        let leftPos = mouseX + 10;
        if (leftPos + tooltipWidth > windowWidth) {
          leftPos = mouseX - tooltipWidth - 10;
        }

        tooltip
          .html(html)
          .style("left", leftPos + "px")
          .style("top", (event.pageY - 35) + "px")
          .transition()
          .duration(200)
          .style("opacity", 1);

        d3.select(this)
          .transition().duration(150)
          .attr("r", dotRadius * 1.5)
          .attr("stroke-width", 2);
      })
      .on("mousemove", function(event) {
        const tooltip = d3.select(".d3-tooltip");
        if (!tooltip.empty()) {
          const tooltipWidth = 280;
          const windowWidth = window.innerWidth;
          const mouseX = event.pageX;

          let leftPos = mouseX + 10;
          if (leftPos + tooltipWidth > windowWidth) {
            leftPos = mouseX - tooltipWidth - 10;
          }

          tooltip
            .style("left", leftPos + "px")
            .style("top", (event.pageY - 35) + "px");
        }
      })
      .on("mouseout", function() {
        d3.select(".d3-tooltip")
          .transition()
          .duration(200)
          .style("opacity", 0)
          .remove();

        d3.select(this)
          .transition().duration(150)
          .attr("r", dotRadius)
          .attr("stroke-width", Math.max(0.5, Math.min(1.5, width / 500)));
      });
  });

  // ========================================
  // X-AXIS
  // ========================================
  const xAxisGroup = g.append("g")
    .attr("class", "x-axis")
    .attr("transform", `translate(0,${innerHeight})`);

  xAxisGroup.call(d3.axisBottom(xScale)
    .tickValues(yearTicks)
    .tickFormat(d3.timeFormat("%Y"))
    .tickSizeOuter(0)
    .tickSizeInner(0));

  xAxisGroup.selectAll(".tick text")
    .style("font-size", `${fontSizes.xAxisTick}px`)
    .attr("dy", "0.5em");

  xAxisGroup.selectAll(".tick line")
    .attr("stroke", "#6c757d")
    .attr("stroke-opacity", 0.5);

  xAxisGroup.select(".domain")
    .attr("stroke", "#6c757d")
    .attr("stroke-opacity", 0.5);

  // ========================================
  // TITLE
  // ========================================
  const heightScale = height / PlotHelpers.PLOT_BASE.HEIGHT;
  const titleY = PlotHelpers.getTitleY(height, heightScale);

  titleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-title")
      .attr("x", 20)
      .attr("y", titleY + (i * lineHeights.title))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.title}px`)
      .text(line);
  });

  // ========================================
  // SUBTITLE
  // ========================================
  const subtitleY = PlotHelpers.getSubtitleY(titleY, titleLines.length, lineHeights.title, heightScale);

  subtitleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-subtitle")
      .attr("x", 20)
      .attr("y", subtitleY + (i * lineHeights.subtitle))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.subtitle}px`)
      .text(line);
  });

  // ========================================
  // X-AXIS LABEL
  // ========================================
  const xAxisLabelX = margin.left + innerWidth / 2;
  const xAxisLabelY = PlotHelpers.getXAxisLabelY(height, captionHeight, heightScale);

  xAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("x", xAxisLabelX)
      .attr("y", xAxisLabelY - ((xAxisLabelLines.length - 1 - i) * lineHeights.axisLabel))
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });

  // ========================================
  // CAPTION
  // ========================================
  const captionY = PlotHelpers.getCaptionY(height, heightScale);

  captionLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-caption")
      .attr("x", 20)
      .attr("y", captionY - ((captionLines.length - 1 - i) * lineHeights.caption))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.caption}px`)
      .text(line);
  });

  return svg.node();
}

function plot_deforestation_area1(deforestation_area, {
  cityName = globalCity,
  countryName = globalCountry,
  width,
  height,
  pixelSizeHectares = 0.095605  // backend export: 30.92m x 30.92m pixel = 0.095605 ha; see gee_fun.py line 323, 335), so this conversion factor is correct: https://github.com/rosemaryturtle/city-scan-automation/blob/main/backend/gee_fun.py

  // note: pixel size calculation:
  // Hansen Global Forest Change dataset in GEE has a native pixel resolution of 30.92 meters, even though it is commonly cited as 30 meters: https://developers.google.com/earth-engine/datasets/catalog/UMD_hansen_global_forest_change_2024_v1_12
} = {}) {
  
  // ========================================
  // DATA PREPARATION
  // ========================================
  // convert pixels to hectares and add to data
  const dataWithHectares = deforestation_area.map(d => ({
    ...d,
    forest_remaining_ha: d.forest_remaining * pixelSizeHectares
  }));
  
  // year range
  const minYear = d3.min(dataWithHectares, d => d.year);
  const maxYear = d3.max(dataWithHectares, d => d.year);
  
  // ========================================
  // STYLING CALCULATIONS
  // ========================================
  // (use helper functions from plot-helpers.js for all styling calculations)
  const fontSizes = PlotHelpers.calculateFontSizes(width, height);
  const lineHeights = PlotHelpers.calculateLineHeights(fontSizes);
  
  // text content
  const titleText = `Forest Remaining Over Time, ${minYear}-${maxYear}`;
  const titleLocation = countryName ? `${cityName}, ${countryName}` : cityName;
  const xAxisLabelText = "Year";
  const yAxisLabelText = "Forest Area Remaining (hectares)";
  const captionText = ""; // (empty for this plot)
  
  // text wrapping
  const titleLines = PlotHelpers.wrapText(titleText, width - 40, `${fontSizes.title}px system-ui`);
  const subtitleLines = PlotHelpers.wrapText(titleLocation, width - 40, `${fontSizes.subtitle}px system-ui`);
  const xAxisLabelLines = PlotHelpers.wrapText(xAxisLabelText, width * 0.8, `${fontSizes.axisLabel}px system-ui`);
  const yAxisLabelLines = PlotHelpers.wrapText(yAxisLabelText, height * 0.6, `${fontSizes.axisLabel}px system-ui`);
  const captionLines = PlotHelpers.wrapText(captionText, width - 40, `${fontSizes.caption}px system-ui`);

  // calculate text dimensions for margins
  const titleHeight = titleLines.length * lineHeights.title;
  const subtitleHeight = subtitleLines.length * lineHeights.subtitle;
  const xAxisLabelHeight = xAxisLabelLines.length * lineHeights.axisLabel;
  const captionHeight = captionLines.length * lineHeights.caption;
  const yAxisLabelWidth = yAxisLabelLines.length * lineHeights.axisLabel;

  // calculate margins using helper
  const margin = PlotHelpers.calculateMargins(width, height, {
    titleHeight,
    subtitleHeight,
    xAxisLabelHeight,
    captionHeight,
    yAxisLabelWidth
  });
  
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  
  // ========================================
  // SCALES
  // ========================================
  const xScale = d3.scaleLinear()
    .domain(d3.extent(dataWithHectares, d => d.year))
    .range([0, innerWidth]);
  
  // calculate y domain with padding using helper
  const yExtent = d3.extent(dataWithHectares, d => d.forest_remaining_ha);
  const yDomain = PlotHelpers.addDomainPadding(yExtent, 0.002, 0.005);
  
  const yScale = d3.scaleLinear()
    .domain(yDomain)
    .range([innerHeight, 0]);
  
  // ========================================
  // SVG CREATION
  // ========================================
  const svg = d3.create("svg")
    .attr("viewBox", `0 0 ${width} ${height}`)
    .attr("preserveAspectRatio", "xMidYMid meet")
    .style("width", "100%")
    .style("height", "auto")
    .style("max-width", `${width}px`);

  const g = svg.append("g")
    .attr("transform", `translate(${margin.left},${margin.top})`);
  
// ========================================
// Y-AXIS
// ========================================
const yTicks = PlotHelpers.calculateYTicks(innerHeight);
const yAxisGroup = g.append("g").attr("class", "y-axis");
const yAxisCall = d3.axisLeft(yScale)
  .ticks(yTicks)
  .tickFormat(d3.format("~s"))
  .tickSizeOuter(0)
  .tickSizeInner(-innerWidth);

yAxisGroup.call(yAxisCall);
yAxisGroup.select(".domain").remove();
yAxisGroup.selectAll(".tick line")
  .attr("stroke", "#f0f0f0")
  .attr("stroke-width", 1);
yAxisGroup.selectAll(".tick text")
  .style("font-size", `${fontSizes.yAxisTick}px`);

// ========================================
// X-AXIS
// ========================================
const xAxisGroup = g.append("g")
.attr("class", "x-axis")
.attr("transform", `translate(0,${innerHeight})`);

xAxisGroup.call(d3.axisBottom(xScale)
.tickFormat(d3.format("d"))
.tickSizeOuter(0)
.tickSizeInner(0));

xAxisGroup.select(".domain")
.attr("stroke", "currentColor")
.attr("stroke-width", 1);

// calculate spacing between potential tick positions
const yearRange = maxYear - minYear;
const tickSpacing = innerWidth / yearRange;

// determine tick interval based on available space
let tickInterval;
if (tickSpacing < 60) {
tickInterval = 3; // (show every 3rd year)
} else if (tickSpacing < 80) {
tickInterval = 2; // (show every 2nd year)
} else {
tickInterval = 1; // (show every year)
}

// filter and style tick labels
xAxisGroup.selectAll(".tick text")
.each(function(d, i) {
  const text = d3.select(this);
  const year = parseInt(d);
  
// hide ticks that don't match the interval (based on year value, not index)
if ((year - minYear) % tickInterval !== 0 && year !== maxYear) {
  text.remove();
  return;
} else {
  text.style("font-size", `${fontSizes.xAxisTick}px`);
  }
  
  text.style("font-size", `${fontSizes.xAxisTick}px`);
});
  
// ========================================
// LINE
// ========================================
const lineStrokeWidth = PlotHelpers.calculateLineStrokeWidth(width);
  
const line = d3.line()
  .defined(d => d.forest_remaining_ha !== null && !isNaN(d.forest_remaining_ha))
  .x(d => xScale(d.year))
  .y(d => yScale(d.forest_remaining_ha));
    
g.append("path")
  .datum(dataWithHectares)
  .attr("fill", "none")
  .attr("stroke", "black")
  .attr("stroke-width", lineStrokeWidth)
  .attr("d", line);
  
// ========================================
// DOTS
// ========================================
const dotRadius = PlotHelpers.calculateLineDotRadius(width);
  
  g.selectAll(".dot")
    .data(dataWithHectares.filter(d => d.forest_remaining_ha !== null && !isNaN(d.forest_remaining_ha)))
    .enter().append("circle")
    .attr("class", "dot")
    .attr("cx", d => xScale(d.year))
    .attr("cy", d => yScale(d.forest_remaining_ha))
    .attr("r", dotRadius)
    .attr("fill", "black")
    .style("cursor", "default")
    .on("mouseover", function(event, d) {
      d3.selectAll(".d3-tooltip").remove();

      const tooltip = d3.select("body").append("div")
        .attr("class", "d3-tooltip")
        .style("opacity", 0);
        
      const tooltipContent = `
        <div>Year: ${d.year}</div>
        <div>${yAxisLabelText}: ${d.forest_remaining_ha.toLocaleString('en-US', {maximumFractionDigits: 0})} ha</div>
      `;
      
      const tooltipWidth = 280;
      const windowWidth = window.innerWidth;
      const mouseX = event.pageX;
      
      let leftPos = mouseX + 10;
      if (leftPos + tooltipWidth > windowWidth) {
        leftPos = mouseX - tooltipWidth - 10;
      }
      
      tooltip
        .html(tooltipContent)
        .style("left", leftPos + "px")
        .style("top", (event.pageY - 35) + "px")
        .transition()
        .duration(200)
        .style("opacity", 1);
    })
    .on("mousemove", function(event) {
      const tooltip = d3.select(".d3-tooltip");
      if (!tooltip.empty()) {
        const tooltipWidth = 280;
        const windowWidth = window.innerWidth;
        const mouseX = event.pageX;
        
        let leftPos = mouseX + 10;
        if (leftPos + tooltipWidth > windowWidth) {
          leftPos = mouseX - tooltipWidth - 10;
        }
        
        tooltip
          .style("left", leftPos + "px")
          .style("top", (event.pageY - 35) + "px");
      }
    })
    .on("mouseout", function() {
      d3.select(".d3-tooltip")
        .transition()
        .duration(200)
        .style("opacity", 0)
        .remove();
    });
  
  // ========================================
  // TITLE
  // ========================================
  const heightScale = height / PlotHelpers.PLOT_BASE.HEIGHT;
  const titleY = PlotHelpers.getTitleY(height, heightScale);
  
  titleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-title")
      .attr("x", 20)
      .attr("y", titleY + (i * lineHeights.title))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.title}px`)
      .text(line);
  });
    
  // ========================================
  // SUBTITLE
  // ========================================
  const subtitleY = PlotHelpers.getSubtitleY(titleY, titleLines.length, lineHeights.title, heightScale);
  
  subtitleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-subtitle")
      .attr("x", 20)
      .attr("y", subtitleY + (i * lineHeights.subtitle))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.subtitle}px`)
      .text(line);
  });
    
  // ========================================
  // Y-AXIS LABEL
  // ========================================
  const widthScale = width / PlotHelpers.PLOT_BASE.WIDTH;
  const yAxisLabelX = -(margin.top + innerHeight/2);
  const yAxisLabelY = PlotHelpers.getYAxisLabelY(widthScale);
  
  yAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("transform", "rotate(-90)")
      .attr("y", yAxisLabelY + (i * lineHeights.axisLabel))
      .attr("x", yAxisLabelX)
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // X-AXIS LABEL
  // ========================================
  const xAxisLabelX = margin.left + innerWidth/2;
  const xAxisLabelY = PlotHelpers.getXAxisLabelY(height, captionHeight, heightScale);
  
  xAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("x", xAxisLabelX)
      .attr("y", xAxisLabelY - ((xAxisLabelLines.length - 1 - i) * lineHeights.axisLabel))
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });


  // ========================================
  // CAPTION
  // ========================================
  // (empty for this plot)
  if (captionText) {
    const captionY = PlotHelpers.getCaptionY(height, heightScale);
    
    captionLines.forEach((line, i) => {
      svg.append("text")
        .attr("class", "plot-caption")
        .attr("x", 20)
        .attr("y", captionY - ((captionLines.length - 1 - i) * lineHeights.caption))
        .attr("text-anchor", "start")
        .style("font-size", `${fontSizes.caption}px`)
        .text(line);
    });
  }
  return svg.node();
}

function plot_deforestation_area2(deforestation_area, {
  cityName = globalCity,
  countryName = globalCountry,
  width,
  height,
  pixelSizeHectares = 0.095605  // backend export: 30.92m x 30.92m pixel = 0.095605 ha; see gee_fun.py line 323, 335), so this conversion factor is correct: https://github.com/rosemaryturtle/city-scan-automation/blob/main/backend/gee_fun.py

  // note: pixel size calculation:
  // Hansen Global Forest Change dataset in GEE has a native pixel resolution of 30.92 meters, even though it is commonly cited as 30 meters: https://developers.google.com/earth-engine/datasets/catalog/UMD_hansen_global_forest_change_2024_v1_12
} = {}) {
  
  // ========================================
  // DATA PREPARATION
  // ========================================
  // convert pixels to hectares and add to data
  const dataWithHectares = deforestation_area.map(d => ({
    ...d,
    cumulative_deforested_ha: d.cumulative_deforested * pixelSizeHectares
  }));
  
  // year range
  const minYear = d3.min(dataWithHectares, d => d.year);
  const maxYear = d3.max(dataWithHectares, d => d.year);
  
  // ========================================
  // STYLING CALCULATIONS
  // ========================================
  // (use helper functions from plot-helpers.js for all styling calculations)
  const fontSizes = PlotHelpers.calculateFontSizes(width, height);
  const lineHeights = PlotHelpers.calculateLineHeights(fontSizes);
  
  // text content
  const titleText = `Forest Loss Over Time, ${minYear}-${maxYear}`;
  const titleLocation = countryName ? `${cityName}, ${countryName}` : cityName;
  const xAxisLabelText = "Year";
  const yAxisLabelText = "Cumulative Forest Loss (hectares)";
  const captionText = ""; // (empty for this plot)
  
  // text wrapping
  const titleLines = PlotHelpers.wrapText(titleText, width - 40, `${fontSizes.title}px system-ui`);
  const subtitleLines = PlotHelpers.wrapText(titleLocation, width - 40, `${fontSizes.subtitle}px system-ui`);
  const xAxisLabelLines = PlotHelpers.wrapText(xAxisLabelText, width * 0.8, `${fontSizes.axisLabel}px system-ui`);
  const yAxisLabelLines = PlotHelpers.wrapText(yAxisLabelText, height * 0.6, `${fontSizes.axisLabel}px system-ui`);
  const captionLines = PlotHelpers.wrapText(captionText, width - 40, `${fontSizes.caption}px system-ui`);

  // calculate text dimensions for margins
  const titleHeight = titleLines.length * lineHeights.title;
  const subtitleHeight = subtitleLines.length * lineHeights.subtitle;
  const xAxisLabelHeight = xAxisLabelLines.length * lineHeights.axisLabel;
  const captionHeight = captionLines.length * lineHeights.caption;
  const yAxisLabelWidth = yAxisLabelLines.length * lineHeights.axisLabel;

  // calculate margins using helper
  const margin = PlotHelpers.calculateMargins(width, height, {
    titleHeight,
    subtitleHeight,
    xAxisLabelHeight,
    captionHeight,
    yAxisLabelWidth
  });
  
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  
  // ========================================
  // SCALES
  // ========================================
  const xScale = d3.scaleLinear()
    .domain(d3.extent(dataWithHectares, d => d.year))
    .range([0, innerWidth]);
  
  // (y domain starts at 0 for cumulative data)
  const yScale = d3.scaleLinear()
    .domain([0, d3.max(dataWithHectares, d => d.cumulative_deforested_ha) * 1.1])
    .range([innerHeight, 0]);
  
  // ========================================
  // SVG CREATION
  // ========================================
  const svg = d3.create("svg")
    .attr("viewBox", `0 0 ${width} ${height}`)
    .attr("preserveAspectRatio", "xMidYMid meet")
    .style("width", "100%")
    .style("height", "auto")
    .style("max-width", `${width}px`);

  const g = svg.append("g")
    .attr("transform", `translate(${margin.left},${margin.top})`);
  
  // ========================================
  // Y-AXIS
  // ========================================
  const yTicks = PlotHelpers.calculateYTicks(innerHeight);
  const yAxisGroup = g.append("g").attr("class", "y-axis");
  const yAxisCall = d3.axisLeft(yScale)
    .ticks(yTicks)
    .tickFormat(d3.format("~s"))
    .tickSizeOuter(0)
    .tickSizeInner(-innerWidth);

  yAxisGroup.call(yAxisCall);
  yAxisGroup.select(".domain").remove();
  yAxisGroup.selectAll(".tick line")
    .attr("stroke", "#f0f0f0")
    .attr("stroke-width", 1);
  yAxisGroup.selectAll(".tick text")
    .style("font-size", `${fontSizes.yAxisTick}px`);
  
  // ========================================
  // X-AXIS
  // ========================================
  const xAxisGroup = g.append("g")
    .attr("class", "x-axis")
    .attr("transform", `translate(0,${innerHeight})`);

    xAxisGroup.call(d3.axisBottom(xScale)
    .tickFormat(d3.format("d"))
    .tickSizeOuter(0)
    .tickSizeInner(0));

    xAxisGroup.select(".domain")
    .attr("stroke", "currentColor")
    .attr("stroke-width", 1);

    // calculate spacing between potential tick positions
    const yearRange = maxYear - minYear;
    const tickSpacing = innerWidth / yearRange;

    // determine tick interval based on available space
    let tickInterval;
    if (tickSpacing < 60) {
    tickInterval = 3; // (show every 3rd year)
    } else if (tickSpacing < 80) {
    tickInterval = 2; // (show every 2nd year)
    } else {
    tickInterval = 1; // show every year
    }

    // filter and style tick labels
    xAxisGroup.selectAll(".tick text")
    .each(function(d, i) {
      const text = d3.select(this);
      const year = parseInt(d);
      
      // hide ticks that don't match the interval (based on year value, not index)
      if ((year - minYear) % tickInterval !== 0 && year !== maxYear) {
        text.remove();
        return;
      }
      
      text.style("font-size", `${fontSizes.xAxisTick}px`);
    });
  
  // ========================================
  // LINE
  // ========================================
  const lineStrokeWidth = PlotHelpers.calculateLineStrokeWidth(width);
  
  const line = d3.line()
    .defined(d => d.cumulative_deforested_ha !== null && !isNaN(d.cumulative_deforested_ha))
    .x(d => xScale(d.year))
    .y(d => yScale(d.cumulative_deforested_ha));
    
  g.append("path")
    .datum(dataWithHectares)
    .attr("fill", "none")
    .attr("stroke", "black")
    .attr("stroke-width", lineStrokeWidth)
    .attr("d", line);
  
  // ========================================
  // DOTS
  // ========================================
  const dotRadius = PlotHelpers.calculateLineDotRadius(width);
  
  g.selectAll(".dot")
    .data(dataWithHectares.filter(d => d.cumulative_deforested_ha !== null && !isNaN(d.cumulative_deforested_ha)))
    .enter().append("circle")
    .attr("class", "dot")
    .attr("cx", d => xScale(d.year))
    .attr("cy", d => yScale(d.cumulative_deforested_ha))
    .attr("r", dotRadius)
    .attr("fill", "black")
    .style("cursor", "default")
    .on("mouseover", function(event, d) {
      d3.selectAll(".d3-tooltip").remove();

      const tooltip = d3.select("body").append("div")
        .attr("class", "d3-tooltip")
        .style("opacity", 0);
        
      const tooltipContent = `
        <div>Year: ${d.year}</div>
        <div>${yAxisLabelText}: ${d.cumulative_deforested_ha.toLocaleString('en-US', {maximumFractionDigits: 0})} ha</div>
      `;
      
      const tooltipWidth = 280;
      const windowWidth = window.innerWidth;
      const mouseX = event.pageX;
      
      let leftPos = mouseX + 10;
      if (leftPos + tooltipWidth > windowWidth) {
        leftPos = mouseX - tooltipWidth - 10;
      }
      
      tooltip
        .html(tooltipContent)
        .style("left", leftPos + "px")
        .style("top", (event.pageY - 35) + "px")
        .transition()
        .duration(200)
        .style("opacity", 1);
    })
    .on("mousemove", function(event) {
      const tooltip = d3.select(".d3-tooltip");
      if (!tooltip.empty()) {
        const tooltipWidth = 280;
        const windowWidth = window.innerWidth;
        const mouseX = event.pageX;
        
        let leftPos = mouseX + 10;
        if (leftPos + tooltipWidth > windowWidth) {
          leftPos = mouseX - tooltipWidth - 10;
        }
        
        tooltip
          .style("left", leftPos + "px")
          .style("top", (event.pageY - 35) + "px");
      }
    })
    .on("mouseout", function() {
      d3.select(".d3-tooltip")
        .transition()
        .duration(200)
        .style("opacity", 0)
        .remove();
    });
  
  // ========================================
  // TITLE
  // ========================================
  const heightScale = height / PlotHelpers.PLOT_BASE.HEIGHT;
  const titleY = PlotHelpers.getTitleY(height, heightScale);
  
  titleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-title")
      .attr("x", 20)
      .attr("y", titleY + (i * lineHeights.title))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.title}px`)
      .text(line);
  });
    
  // ========================================
  // SUBTITLE
  // ========================================
  const subtitleY = PlotHelpers.getSubtitleY(titleY, titleLines.length, lineHeights.title, heightScale);
  
  subtitleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-subtitle")
      .attr("x", 20)
      .attr("y", subtitleY + (i * lineHeights.subtitle))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.subtitle}px`)
      .text(line);
  });
    
  // ========================================
  // Y-AXIS LABEL
  // ========================================
  const widthScale = width / PlotHelpers.PLOT_BASE.WIDTH;
  const yAxisLabelX = -(margin.top + innerHeight/2);
  const yAxisLabelY = PlotHelpers.getYAxisLabelY(widthScale);
  
  yAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("transform", "rotate(-90)")
      .attr("y", yAxisLabelY + (i * lineHeights.axisLabel))
      .attr("x", yAxisLabelX)
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // X-AXIS LABEL
  // ========================================
  const xAxisLabelX = margin.left + innerWidth/2;
  const xAxisLabelY = PlotHelpers.getXAxisLabelY(height, captionHeight, heightScale);
  
  xAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("x", xAxisLabelX)
      .attr("y", xAxisLabelY - ((xAxisLabelLines.length - 1 - i) * lineHeights.axisLabel))
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
   });

   // ========================================
   // CAPTION
   // ========================================
   // (empty for this plot)
   if (captionText) {
    const captionY = PlotHelpers.getCaptionY(height, heightScale);
    
    captionLines.forEach((line, i) => {
      svg.append("text")
        .attr("class", "plot-caption")  
        .attr("x", 20)
        .attr("y", captionY - ((captionLines.length - 1 - i) * lineHeights.caption))
        .attr("text-anchor", "start")
        .style("font-size", `${fontSizes.caption}px`)
        .text(line);
    });
  }
  
  return svg.node();
}

function plot_deforestation_area3(deforestation_area, {
  cityName = globalCity,
  countryName = globalCountry,
  width,
  height,
  pixelSizeHectares = 0.095605  // backend export: 30.92m x 30.92m pixel = 0.095605 ha; see gee_fun.py line 323, 335), so this conversion factor is correct: https://github.com/rosemaryturtle/city-scan-automation/blob/main/backend/gee_fun.py

  // note: pixel size calculation:
  // Hansen Global Forest Change dataset in GEE has a native pixel resolution of 30.92 meters, even though it is commonly cited as 30 meters: https://developers.google.com/earth-engine/datasets/catalog/UMD_hansen_global_forest_change_2024_v1_12
} = {}) {
  
  // ========================================
  // DATA PREPARATION
  // ========================================
  // sort data by year
  const sortedData = deforestation_area.slice().sort((a, b) => a.year - b.year);
  
  // convert pixels to hectares for annual deforestation
  const dataWithHectares = sortedData.map(d => ({
    ...d,
    deforested_this_year_ha: d.deforested_this_year * pixelSizeHectares
  }));

  // year range from data
  const minYear = d3.min(dataWithHectares, d => d.year);
  const maxYear = d3.max(dataWithHectares, d => d.year);
  
  // single color for all bars
  const barColor = "#e47673";
  
  // ========================================
  // STYLING CALCULATIONS
  // ========================================
  // (use helper functions from plot-helpers.js for all styling calculations)
  const fontSizes = PlotHelpers.calculateFontSizes(width, height);
  const lineHeights = PlotHelpers.calculateLineHeights(fontSizes);
  
  // text content
  const titleText = `Annual Deforestation, ${minYear}-${maxYear}`;
  const titleLocation = countryName ? `${cityName}, ${countryName}` : cityName;
  const xAxisLabelText = "Year";
  const yAxisLabelText = "Annual Forest Loss (hectares)";
  const captionText = ""; // (empty for this plot)
  
  // text wrapping
  const titleLines = PlotHelpers.wrapText(titleText, width - 40, `${fontSizes.title}px system-ui`);
  const subtitleLines = PlotHelpers.wrapText(titleLocation, width - 40, `${fontSizes.subtitle}px system-ui`);
  const xAxisLabelLines = PlotHelpers.wrapText(xAxisLabelText, width * 0.8, `${fontSizes.axisLabel}px system-ui`);
  const yAxisLabelLines = PlotHelpers.wrapText(yAxisLabelText, height * 0.6, `${fontSizes.axisLabel}px system-ui`);
  const captionLines = PlotHelpers.wrapText(captionText, width - 40, `${fontSizes.caption}px system-ui`);

  // calculate text dimensions for margins
  const titleHeight = titleLines.length * lineHeights.title;
  const subtitleHeight = subtitleLines.length * lineHeights.subtitle;
  const xAxisLabelHeight = xAxisLabelLines.length * lineHeights.axisLabel;
  const captionHeight = captionLines.length * lineHeights.caption;
  const yAxisLabelWidth = yAxisLabelLines.length * lineHeights.axisLabel;

  // calculate margins using helper
  const margin = PlotHelpers.calculateMargins(width, height, {
    titleHeight,
    subtitleHeight,
    xAxisLabelHeight,
    captionHeight,
    yAxisLabelWidth
  });
  
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  
  // ========================================
  // SCALES
  // ========================================
  const xScale = d3.scaleBand()
    .domain(dataWithHectares.map(d => d.year))
    .range([0, innerWidth])
    .padding(0.15);
    
  // dynamic y-scale based on data
  const maxValue = d3.max(dataWithHectares, d => d.deforested_this_year_ha);
  const yScale = d3.scaleLinear()
    .domain([0, maxValue * 1.1])
    .range([innerHeight, 0]);
  
  // ========================================
  // SVG CREATION
  // ========================================
  const svg = d3.create("svg")
    .attr("viewBox", `0 0 ${width} ${height}`)
    .attr("preserveAspectRatio", "xMidYMid meet")
    .style("width", "100%")
    .style("height", "auto")
    .style("max-width", `${width}px`);

  const g = svg.append("g")
    .attr("transform", `translate(${margin.left},${margin.top})`);
  
  // ========================================
  // Y-AXIS
  // ========================================
  const yTicks = PlotHelpers.calculateYTicks(innerHeight);
  const yAxisGroup = g.append("g").attr("class", "y-axis");
  const yAxisCall = d3.axisLeft(yScale)
    .ticks(yTicks)
    .tickFormat(d3.format("~s"))
    .tickSizeOuter(0)
    .tickSizeInner(-innerWidth);

  yAxisGroup.call(yAxisCall);
  yAxisGroup.select(".domain").remove();
  yAxisGroup.selectAll(".tick line")
    .attr("stroke", "#f0f0f0")
    .attr("stroke-width", 1);
  yAxisGroup.selectAll(".tick text")
    .style("font-size", `${fontSizes.yAxisTick}px`);
  
  // ========================================
  // DATA BARS
  // ========================================
  g.selectAll(".data-bar")
    .data(dataWithHectares.filter(d => d.deforested_this_year_ha > 0))
    .enter().append("rect")
    .attr("class", "data-bar")
    .attr("x", d => xScale(d.year))
    .attr("width", xScale.bandwidth())
    .attr("y", d => yScale(d.deforested_this_year_ha))
    .attr("height", d => innerHeight - yScale(d.deforested_this_year_ha))
    .attr("fill", barColor)
    .attr("fill-opacity", 1)
    .attr("stroke", d3.color(barColor).darker(0.5))
    .attr("stroke-width", 1)
    .style("cursor", "default")
    .on("mouseover", function(event, d) {
      d3.selectAll(".d3-tooltip").remove();

      const tooltip = d3.select("body").append("div")
        .attr("class", "d3-tooltip")
        .style("opacity", 0);
        
      const tooltipContent = `
        <div>Year: ${d.year}</div>
        <div>Forest Lost: ${d.deforested_this_year_ha.toLocaleString('en-US', {maximumFractionDigits: 1})} ha</div>
      `;
      
      const tooltipWidth = 280;
      const windowWidth = window.innerWidth;
      const mouseX = event.pageX;
      
      let leftPos = mouseX + 10;
      if (leftPos + tooltipWidth > windowWidth) {
        leftPos = mouseX - tooltipWidth - 10;
      }
      
      tooltip
        .html(tooltipContent)
        .style("left", leftPos + "px")
        .style("top", (event.pageY - 35) + "px")
        .transition()
        .duration(200)
        .style("opacity", 1);
    })
    .on("mousemove", function(event) {
      const tooltip = d3.select(".d3-tooltip");
      if (!tooltip.empty()) {
        const tooltipWidth = 280;
        const windowWidth = window.innerWidth;
        const mouseX = event.pageX;
        
        let leftPos = mouseX + 10;
        if (leftPos + tooltipWidth > windowWidth) {
          leftPos = mouseX - tooltipWidth - 10;
        }
        
        tooltip
          .style("left", leftPos + "px")
          .style("top", (event.pageY - 35) + "px");
      }
    })
    .on("mouseout", function() {
      d3.select(".d3-tooltip")
        .transition()
        .duration(200)
        .style("opacity", 0)
        .remove();
    });
  
  // ========================================
  // X-AXIS
  // ========================================
  const xAxisGroup = g.append("g")
    .attr("class", "x-axis")
    .attr("transform", `translate(0,${innerHeight})`);
    
  xAxisGroup.call(d3.axisBottom(xScale)
    .tickSizeOuter(0)
    .tickSizeInner(0));
    
  xAxisGroup.select(".domain")
    .attr("stroke", "currentColor")
    .attr("stroke-width", 1);

  // calculate how many ticks to show based on available width
  const barWidth = xScale.bandwidth();
  const availableSpacePerTick = barWidth + (xScale.step() - barWidth);
  
  // determine tick interval (show every nth year)
  let tickInterval;
  if (availableSpacePerTick < 40) {
    tickInterval = 5; // (show every 5th year)
  } else if (availableSpacePerTick < 60) {
    tickInterval = 3; // (show every 3rd year)
  } else if (availableSpacePerTick < 80) {
    tickInterval = 2; // (show every 2nd year)
  } else {
    tickInterval = 1; // (show every year)
  }

  // calculate rotation angle
  const rotation = PlotHelpers.calculateXAxisLabelRotation(barWidth * tickInterval);
  const labelProps = PlotHelpers.calculateRotatedLabelProperties(rotation);

  // filter and style tick labels
  xAxisGroup.selectAll(".tick text")
    .each(function(d, i) {
      const text = d3.select(this);
      
      // hide ticks that don't match the interval
      if (i % tickInterval !== 0) {
        text.remove();
        return;
      }
      
      text.style("font-size", `${fontSizes.xAxisTick}px`)
        .style("text-anchor", labelProps.textAnchor)
        .attr("dx", labelProps.dx)
        .attr("dy", labelProps.dy);
      
      if (rotation !== 0) {
        text.attr("transform", `rotate(${rotation})`);
      }
    });
  
  // ========================================
  // TITLE
  // ========================================
  const heightScale = height / PlotHelpers.PLOT_BASE.HEIGHT;
  const titleY = PlotHelpers.getTitleY(height, heightScale);
  
  titleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-title")
      .attr("x", 20)
      .attr("y", titleY + (i * lineHeights.title))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.title}px`)
      .text(line);
  });
    
  // ========================================
  // SUBTITLE
  // ========================================
  const subtitleY = PlotHelpers.getSubtitleY(titleY, titleLines.length, lineHeights.title, heightScale);
  
  subtitleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-subtitle")
      .attr("x", 20)
      .attr("y", subtitleY + (i * lineHeights.subtitle))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.subtitle}px`)
      .text(line);
  });
    
  // ========================================
  // Y-AXIS LABEL
  // ========================================
  const widthScale = width / PlotHelpers.PLOT_BASE.WIDTH;
  const yAxisLabelX = -(margin.top + innerHeight/2);
  const yAxisLabelY = PlotHelpers.getYAxisLabelY(widthScale);
  
  yAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("transform", "rotate(-90)")
      .attr("y", yAxisLabelY + (i * lineHeights.axisLabel))
      .attr("x", yAxisLabelX)
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // X-AXIS LABEL
  // ========================================
  const xAxisLabelX = margin.left + innerWidth/2;
  const xAxisLabelY = PlotHelpers.getXAxisLabelY(height, captionHeight, heightScale);
  
  xAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("x", xAxisLabelX)
      .attr("y", xAxisLabelY - ((xAxisLabelLines.length - 1 - i) * lineHeights.axisLabel))
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });


  // ========================================
  // CAPTION
  // ========================================
  // (empty for this plot)
  if (captionText) {
    const captionY = PlotHelpers.getCaptionY(height, heightScale);
    
    captionLines.forEach((line, i) => {
      svg.append("text")
        .attr("class", "plot-caption")
        .attr("x", 20)
        .attr("y", captionY - ((captionLines.length - 1 - i) * lineHeights.caption))
        .attr("text-anchor", "start")
        .style("font-size", `${fontSizes.caption}px`)
        .text(line);
    });
  }
  return svg.node();
}

function plot_deforestation_area4(deforestation_area, {
  cityName = globalCity,
  countryName = globalCountry,
  width,
  height
} = {}) {
  
  // ========================================
  // DATA PREPARATION
  // ========================================
  // sort data by year
  const sortedData = deforestation_area.slice().sort((a, b) => a.year - b.year);

  // calculate total cumulative deforestation (last/final entry)
  const totalDeforestation = sortedData[sortedData.length - 1].cumulative_deforested;
  
  // add percentage of total deforestation to each data point
  const dataWithPercentages = sortedData.map(d => ({
    ...d,
    percent_of_total_deforestation: (d.deforested_this_year / totalDeforestation) * 100
  }));

  // year range from data
  const minYear = d3.min(dataWithPercentages, d => d.year);
  const maxYear = d3.max(dataWithPercentages, d => d.year);
  
  // single color for all bars
  const barColor = "#e47673";
  
  // ========================================
  // STYLING CALCULATIONS
  // ========================================
  // (use helper functions from plot-helpers.js for all styling calculations)
  const fontSizes = PlotHelpers.calculateFontSizes(width, height);
  const lineHeights = PlotHelpers.calculateLineHeights(fontSizes);
  
  // text content
  const titleText = `Annual Deforestation as Percentage of Total Deforestation, ${minYear}-${maxYear}`;
  const titleLocation = countryName ? `${cityName}, ${countryName}` : cityName;
  const xAxisLabelText = "Year";
  const yAxisLabelText = "Percent of Total Deforestation (%)";
  const captionText = ""; // (empty for this plot)
  
  // text wrapping
  const titleLines = PlotHelpers.wrapText(titleText, width - 40, `${fontSizes.title}px system-ui`);
  const subtitleLines = PlotHelpers.wrapText(titleLocation, width - 40, `${fontSizes.subtitle}px system-ui`);
  const xAxisLabelLines = PlotHelpers.wrapText(xAxisLabelText, width * 0.8, `${fontSizes.axisLabel}px system-ui`);
  const yAxisLabelLines = PlotHelpers.wrapText(yAxisLabelText, height * 0.6, `${fontSizes.axisLabel}px system-ui`);
  const captionLines = PlotHelpers.wrapText(captionText, width - 40, `${fontSizes.caption}px system-ui`);

  // calculate text dimensions for margins
  const titleHeight = titleLines.length * lineHeights.title;
  const subtitleHeight = subtitleLines.length * lineHeights.subtitle;
  const xAxisLabelHeight = xAxisLabelLines.length * lineHeights.axisLabel;
  const captionHeight = captionLines.length * lineHeights.caption;
  const yAxisLabelWidth = yAxisLabelLines.length * lineHeights.axisLabel;

  // calculate margins using helper
  const margin = PlotHelpers.calculateMargins(width, height, {
    titleHeight,
    subtitleHeight,
    xAxisLabelHeight,
    captionHeight,
    yAxisLabelWidth
  });
  
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  
  // ========================================
  // SCALES
  // ========================================
  const xScale = d3.scaleBand()
    .domain(dataWithPercentages.map(d => d.year))
    .range([0, innerWidth])
    .padding(0.15);
    
  // dynamic y-scale based on percentage of total
  const maxValue = d3.max(dataWithPercentages, d => d.percent_of_total_deforestation);
  const yScale = d3.scaleLinear()
    .domain([0, maxValue * 1.1])
    .range([innerHeight, 0]);
  
  // ========================================
  // SVG CREATION
  // ========================================
  const svg = d3.create("svg")
    .attr("viewBox", `0 0 ${width} ${height}`)
    .attr("preserveAspectRatio", "xMidYMid meet")
    .style("width", "100%")
    .style("height", "auto")
    .style("max-width", `${width}px`);

  const g = svg.append("g")
    .attr("transform", `translate(${margin.left},${margin.top})`);
  
  // ========================================
  // Y-AXIS
  // ========================================
  const yTicks = PlotHelpers.calculateYTicks(innerHeight);
  const yAxisGroup = g.append("g").attr("class", "y-axis");
  const yAxisCall = d3.axisLeft(yScale)
    .ticks(yTicks)
    .tickFormat(d => d.toFixed(0) + "%")
    .tickSizeOuter(0)
    .tickSizeInner(-innerWidth);

  yAxisGroup.call(yAxisCall);
  yAxisGroup.select(".domain").remove();
  yAxisGroup.selectAll(".tick line")
    .attr("stroke", "#f0f0f0")
    .attr("stroke-width", 1);
  yAxisGroup.selectAll(".tick text")
    .style("font-size", `${fontSizes.yAxisTick}px`);
  
  // ========================================
  // DATA BARS
  // ========================================
  g.selectAll(".data-bar")
    .data(dataWithPercentages.filter(d => d.percent_of_total_deforestation > 0))
    .enter().append("rect")
    .attr("class", "data-bar")
    .attr("x", d => xScale(d.year))
    .attr("width", xScale.bandwidth())
    .attr("y", d => yScale(d.percent_of_total_deforestation))
    .attr("height", d => innerHeight - yScale(d.percent_of_total_deforestation))
    .attr("fill", barColor)
    .attr("fill-opacity", 1)
    .attr("stroke", d3.color(barColor).darker(0.5))
    .attr("stroke-width", 1)
    .style("cursor", "default")
    .on("mouseover", function(event, d) {
      d3.selectAll(".d3-tooltip").remove();

      const tooltip = d3.select("body").append("div")
        .attr("class", "d3-tooltip")
        .style("opacity", 0);
        
      const tooltipContent = `
        <div>Year: ${d.year}</div>
        <div>Percent of Total Deforestation: ${d.percent_of_total_deforestation.toFixed(2)}%</div>
      `;
      
      const tooltipWidth = 280;
      const windowWidth = window.innerWidth;
      const mouseX = event.pageX;
      
      let leftPos = mouseX + 10;
      if (leftPos + tooltipWidth > windowWidth) {
        leftPos = mouseX - tooltipWidth - 10;
      }
      
      tooltip
        .html(tooltipContent)
        .style("left", leftPos + "px")
        .style("top", (event.pageY - 35) + "px")
        .transition()
        .duration(200)
        .style("opacity", 1);
    })
    .on("mousemove", function(event) {
      const tooltip = d3.select(".d3-tooltip");
      if (!tooltip.empty()) {
        const tooltipWidth = 280;
        const windowWidth = window.innerWidth;
        const mouseX = event.pageX;
        
        let leftPos = mouseX + 10;
        if (leftPos + tooltipWidth > windowWidth) {
          leftPos = mouseX - tooltipWidth - 10;
        }
        
        tooltip
          .style("left", leftPos + "px")
          .style("top", (event.pageY - 35) + "px");
      }
    })
    .on("mouseout", function() {
      d3.select(".d3-tooltip")
        .transition()
        .duration(200)
        .style("opacity", 0)
        .remove();
    });
  
  // ========================================
  // X-AXIS
  // ========================================
  const xAxisGroup = g.append("g")
    .attr("class", "x-axis")
    .attr("transform", `translate(0,${innerHeight})`);
    
  xAxisGroup.call(d3.axisBottom(xScale)
    .tickSizeOuter(0)
    .tickSizeInner(0));
    
  xAxisGroup.select(".domain")
    .attr("stroke", "currentColor")
    .attr("stroke-width", 1);

  // calculate how many ticks to show based on available width
  const barWidth = xScale.bandwidth();
  const availableSpacePerTick = barWidth + (xScale.step() - barWidth);
  
  // determine tick interval (show every nth year)
  let tickInterval;
  if (availableSpacePerTick < 40) {
    tickInterval = 5; // (show every 5th year)
  } else if (availableSpacePerTick < 60) {
    tickInterval = 3; // (show every 3rd year)
  } else if (availableSpacePerTick < 80) {
    tickInterval = 2; // (show every 2nd year)
  } else {
    tickInterval = 1; // (show every year)
  }

  // calculate rotation angle
  const rotation = PlotHelpers.calculateXAxisLabelRotation(barWidth * tickInterval);
  const labelProps = PlotHelpers.calculateRotatedLabelProperties(rotation);

  // filter and style tick labels
  xAxisGroup.selectAll(".tick text")
    .each(function(d, i) {
      const text = d3.select(this);
      
      // hide ticks that don't match the interval
      if (i % tickInterval !== 0) {
        text.remove();
        return;
      }
      
      text.style("font-size", `${fontSizes.xAxisTick}px`)
        .style("text-anchor", labelProps.textAnchor)
        .attr("dx", labelProps.dx)
        .attr("dy", labelProps.dy);
      
      if (rotation !== 0) {
        text.attr("transform", `rotate(${rotation})`);
      }
    });
  
  // ========================================
  // TITLE
  // ========================================
  const heightScale = height / PlotHelpers.PLOT_BASE.HEIGHT;
  const titleY = PlotHelpers.getTitleY(height, heightScale);
  
  titleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-title")
      .attr("x", 20)
      .attr("y", titleY + (i * lineHeights.title))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.title}px`)
      .text(line);
  });
    
  // ========================================
  // SUBTITLE
  // ========================================
  const subtitleY = PlotHelpers.getSubtitleY(titleY, titleLines.length, lineHeights.title, heightScale);
  
  subtitleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-subtitle")
      .attr("x", 20)
      .attr("y", subtitleY + (i * lineHeights.subtitle))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.subtitle}px`)
      .text(line);
  });
    
  // ========================================
  // Y-AXIS LABEL
  // ========================================
  const widthScale = width / PlotHelpers.PLOT_BASE.WIDTH;
  const yAxisLabelX = -(margin.top + innerHeight/2);
  const yAxisLabelY = PlotHelpers.getYAxisLabelY(widthScale);
  
  yAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("transform", "rotate(-90)")
      .attr("y", yAxisLabelY + (i * lineHeights.axisLabel))
      .attr("x", yAxisLabelX)
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });
    
  // ========================================
  // X-AXIS LABEL
  // ========================================
  const xAxisLabelX = margin.left + innerWidth/2;
  const xAxisLabelY = PlotHelpers.getXAxisLabelY(height, captionHeight, heightScale);
  
  xAxisLabelLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-axis-label")
      .attr("x", xAxisLabelX)
      .attr("y", xAxisLabelY - ((xAxisLabelLines.length - 1 - i) * lineHeights.axisLabel))
      .attr("text-anchor", "middle")
      .style("font-size", `${fontSizes.axisLabel}px`)
      .text(line);
  });


  // ========================================
  // CAPTION
  // ========================================
  // (empty for this plot)
  if (captionText) {
    const captionY = PlotHelpers.getCaptionY(height, heightScale);
    
    captionLines.forEach((line, i) => {
      svg.append("text")
        .attr("class", "plot-caption")
        .attr("x", 20)
        .attr("y", captionY - ((captionLines.length - 1 - i) * lineHeights.caption))
        .attr("text-anchor", "start")
        .style("font-size", `${fontSizes.caption}px`)
        .text(line);
    });
  }
  return svg.node();
}

function plot_deforestation_area5(deforestation_area, {
  cityName = globalCity,
  countryName = globalCountry,
  width,
  height
} = {}) {
  
  // ========================================
  // DATA PREPARATION
  // ========================================
  // create time period bins
  const bins = PlotHelpers.createTimePeriodBins(
    deforestation_area, 
    5, 
    (binData, sortedData, startYear, minYear) => {
      // aggregation function for deforestation data
      const lastYearInBin = binData[binData.length - 1];
      
      return {
        percent_forest_remaining: lastYearInBin.percent_forest_remaining,
        percent_forest_lost_cumulative: lastYearInBin.percent_forest_lost,
        percent_forest_lost_this_period: lastYearInBin.percent_forest_lost - 
          (binData[0].year === minYear ? 0 : sortedData.find(d => d.year === startYear - 1).percent_forest_lost)
      };
    }
  );
  
  const minYear = bins[0].startYear;
  const maxYear = bins[bins.length - 1].endYear;
  
  // color scale (for visual cohesion with deforestation map)
  const colors = {
    remaining: "#4CAF50",     // green - remaining forest
    lostPrevious: "#BDBDBD",  // gray - lost forest in previous periods
    lostThisPeriod: "#e47673" // red - lost forest in this period
  };
  
  // ========================================
  // DIMENSION CALCULATIONS
  // ========================================
  const numMultiples = bins.length;
  
  // calculate reasonable grid size based on available width
  // (allow more space for grids by reducing reserved space)
  const maxGridWidth = Math.min(140, (width - 60) / numMultiples);
  
  // calculate grid dimensions
  const gridDimensions = PlotHelpers.calculateBubbleGridDimensions(maxGridWidth, 10, 20);
  const { bubbleSize, bubbleSpacing, gridWidth, gridHeight } = gridDimensions;
  
  // account for bubble overhang
  const overhangDimensions = PlotHelpers.calculateBubbleGridOverhang(gridWidth, bubbleSize);
  const { effectiveGridWidth, paddingOffset } = overhangDimensions;
  
  // calculate layout (tight spacing between panels)
  const layoutDimensions = PlotHelpers.calculateSmallMultiplesDimensions(
    width, 
    numMultiples, 
    effectiveGridWidth,
    Math.max(5, gridWidth * 0.05)
  );
  const { panelSpacing, startX } = layoutDimensions;
  
  // add padding on left side for first bubble
  const adjustedStartX = startX + paddingOffset;
  
  const totalWidth = width;
  const calculatedHeight = gridHeight + 270; // (extra space for wrapped labels)
  
  // ========================================
  // STYLING CALCULATIONS
  // ========================================
  const fontSizes = PlotHelpers.calculateFontSizes(width, calculatedHeight);
  const lineHeights = PlotHelpers.calculateLineHeights(fontSizes);
  const panelFontSizes = PlotHelpers.calculateSmallMultiplesFontSizes(width, numMultiples);
  
  // text content
  const titleText = `Year-by-Year Forest Composition, ${minYear}-${maxYear}`;
  const titleLocation = countryName ? `${cityName}, ${countryName}` : cityName;
  const captionText = ""; // (empty for this plot)
  
  // text wrapping
  const titleLines = PlotHelpers.wrapText(titleText, width - 40, `${fontSizes.title}px system-ui`);
  const subtitleLines = PlotHelpers.wrapText(titleLocation, width - 40, `${fontSizes.subtitle}px system-ui`);
  const captionLines = PlotHelpers.wrapText(captionText, width - 40, `${fontSizes.caption}px system-ui`);
  
  // calculate text dimensions
  const captionHeight = captionText ? captionLines.length * lineHeights.caption : 0;

  // ========================================
  // SVG CREATION
  // ========================================
  const svg = d3.create("svg")
    .attr("viewBox", `0 0 ${totalWidth} ${calculatedHeight}`)
    .attr("preserveAspectRatio", "xMidYMid meet")
    .style("width", "100%")
    .style("height", "auto")
    .style("max-width", `${totalWidth}px`);
  
  // ========================================
  // TITLE
  // ========================================
  const heightScale = calculatedHeight / PlotHelpers.PLOT_BASE.HEIGHT;
  const titleY = PlotHelpers.getTitleY(calculatedHeight, heightScale);
  
  titleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-title")
      .attr("x", 20)
      .attr("y", titleY + (i * lineHeights.title))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.title}px`)
      .text(line);
  });
  
  // ========================================
  // SUBTITLE
  // ========================================
  const subtitleY = PlotHelpers.getSubtitleY(titleY, titleLines.length, lineHeights.title, heightScale);
  
  subtitleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-subtitle")
      .attr("x", 20)
      .attr("y", subtitleY + (i * lineHeights.subtitle))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.subtitle}px`)
      .text(line);
  });
  
  // ========================================
  // CREATE EACH SMALL MULTIPLE
  // ========================================
  const yOffset = 90;
  
  bins.forEach((bin, binIndex) => {
    // calculate panel x offset (use effectiveGridWidth for spacing)
    const xOffset = PlotHelpers.calculatePanelXOffset(binIndex, effectiveGridWidth, panelSpacing, adjustedStartX);
    
    // calculate panel label position (use gridWidth for centering)
    const panelPosition = PlotHelpers.calculatePanelLabelPosition(xOffset, gridWidth);
    const { centerX } = panelPosition;
    
    // generate bubble grid data
    const bubbleGridData = PlotHelpers.generateBubbleGridData(100, 10);
    
    // calculate how many bubbles for each category
    const remainingBubbles = Math.round(bin.percent_forest_remaining);
    const lostThisPeriodBubbles = Math.round(bin.percent_forest_lost_this_period);
    const lostPreviousBubbles = 100 - remainingBubbles - lostThisPeriodBubbles;
    
    // assign types to bubbles
    let remainingCount = 0;
    let lostPreviousCount = 0;
    let lostThisPeriodCount = 0;
    
    const bubbleData = bubbleGridData.map(bubble => {
      let type, color, opacity, stroke;
      
      // remaining forest bubbles (green)
      if (remainingCount < remainingBubbles) {
        type = "remaining";
        color = colors.remaining;
        opacity = 0.9;
        stroke = colors.remaining;
        remainingCount++;
      }
      // lost forest in previous periods bubbles (gray)
      else if (lostPreviousCount < lostPreviousBubbles) {
        type = "lostPrevious";
        color = colors.lostPrevious;
        opacity = 0.3;
        stroke = "#999";
        lostPreviousCount++;
      }
      // lost forest in this period bubbles (red)
      else {
        type = "lostThisPeriod";
        color = colors.lostThisPeriod;
        opacity = 0.9;
        stroke = d3.color(colors.lostThisPeriod).darker(0.3);
        lostThisPeriodCount++;
      }
      
      // calculate position
      const position = PlotHelpers.calculateBubblePosition(
        bubble.row, 
        bubble.col, 
        bubbleSpacing, 
        xOffset, 
        yOffset
      );
      
      return {
        ...bubble,
        ...position,
        type,
        color,
        opacity,
        stroke,
        binIndex
      };
    });
    
    // draw bubbles for this small multiple
    svg.selectAll(`.bubble-${binIndex}`)
      .data(bubbleData)
      .enter().append("circle")
      .attr("class", `bubble-${binIndex}`)
      .attr("cx", d => d.cx)
      .attr("cy", d => d.cy)
      .attr("r", bubbleSize / 2)
      .attr("fill", d => d.color)
      .attr("stroke", d => d.stroke)
      .attr("stroke-width", 0.5)
      .attr("opacity", d => d.opacity);
    
    // year label above each small multiple
    svg.append("text")
      .attr("x", centerX)
      .attr("y", yOffset - 10)
      .attr("text-anchor", "middle")
      .attr("fill", "currentColor")
      .style("font-size", `${panelFontSizes.panelLabel}px`)
      .style("font-weight", "bold")
      .text(bin.label);
    
    // calculate stats positions
    const statsPositions = PlotHelpers.calculatePanelStatsPositions(gridHeight, yOffset);
    
    // stats below each small multiple - forest remaining
    svg.append("text")
      .attr("x", centerX)
      .attr("y", statsPositions.stat1Value)
      .attr("text-anchor", "middle")
      .attr("fill", colors.remaining)
      .style("font-size", `${panelFontSizes.panelValue}px`)
      .style("font-weight", "bold")
      .text(`${bin.percent_forest_remaining.toFixed(1)}%`);
    
    // wrap "forest" label text
    const forestLabelLines = PlotHelpers.wrapShortLabel("Forest", gridWidth, `${panelFontSizes.panelDescription}px system-ui`);
    forestLabelLines.forEach((line, i) => {
      svg.append("text")
        .attr("x", centerX)
        .attr("y", statsPositions.stat1Label + (i * panelFontSizes.panelDescription * 1.2))
        .attr("text-anchor", "middle")
        .attr("fill", "currentColor")
        .style("font-size", `${panelFontSizes.panelDescription}px`)
        .text(line);
    });
    
    // stats - deforested
    svg.append("text")
      .attr("x", centerX)
      .attr("y", statsPositions.stat2Value)
      .attr("text-anchor", "middle")
      .attr("fill", colors.lostThisPeriod)
      .style("font-size", `${panelFontSizes.panelValue}px`)
      .text(`${bin.percent_forest_lost_cumulative.toFixed(1)}%`);
    
    // wrap "deforested" label text
    const deforestedLabelLines = PlotHelpers.wrapShortLabel("Deforested", gridWidth, `${panelFontSizes.panelDescription}px system-ui`);
    deforestedLabelLines.forEach((line, i) => {
      svg.append("text")
        .attr("x", centerX)
        .attr("y", statsPositions.stat2Label + (i * panelFontSizes.panelDescription * 1.2))
        .attr("text-anchor", "middle")
        .attr("fill", "currentColor")
        .style("font-size", `${panelFontSizes.panelDescription}px`)
        .text(line);
    });
  });
  
  // ========================================
  // LEGEND
  // ========================================
  const legendY = calculatedHeight - (captionHeight > 0 ? captionHeight + 50 : 40);
  const legendItems = [
    {
      label: "Forest Remaining",
      color: colors.remaining,
      shape: "circle",
      opacity: 0.9
    },
    {
      label: "Deforested",
      color: colors.lostThisPeriod,
      shape: "circle",
      opacity: 0.9
    }
  ];
  
  PlotHelpers.addBubbleGridLegend(svg, legendItems, width, legendY, panelFontSizes.panelDescription);

  // ========================================
  // CAPTION
  // ========================================
  // (empty for this plot)
  if (captionText) {
    const captionY = PlotHelpers.getCaptionY(calculatedHeight, heightScale);
    
    captionLines.forEach((line, i) => {
      svg.append("text")
        .attr("class", "plot-caption")
        .attr("x", 20)
        .attr("y", captionY - ((captionLines.length - 1 - i) * lineHeights.caption))
        .attr("text-anchor", "start")
        .style("font-size", `${fontSizes.caption}px`)
        .text(line);
    });
  }
  return svg.node();
}

function plot_deforestation_area6(deforestation_area, {
  cityName = globalCity,
  countryName = globalCountry,
  width,
  height
} = {}) {
  
  // ========================================
  // DATA PREPARATION
  // ========================================
  // sort data by year
  const sortedData = deforestation_area.slice().sort((a, b) => a.year - b.year);
  
  const minYear = Math.min(...sortedData.map(d => d.year));
  const maxYear = Math.max(...sortedData.map(d => d.year));
  
  // get total deforestation at end
  const totalDeforestation = sortedData[sortedData.length - 1].cumulative_deforested;
  const finalForestLostPercent = sortedData[sortedData.length - 1].percent_forest_lost;
  
  // create time period bins
  const bins = PlotHelpers.createTimePeriodBins(
    deforestation_area,
    5,
    (binData, sortedData, startYear, minYear) => {
      // aggregation function for deforestation data
      const lastYearInBin = binData[binData.length - 1];
      
      // calculate percent of total deforestation has occurred by end of this period
      const percentOfTotalDeforestation = (lastYearInBin.cumulative_deforested / totalDeforestation) * 100;
      
      return {
        percentOfTotalDeforestation,
        cumulativePixels: lastYearInBin.cumulative_deforested,
        percentForestLost: lastYearInBin.percent_forest_lost
      };
    }
  );
  
  // color scale (for visual cohesion with deforestation map)
  const colorScale = d3.scaleLinear()
    .domain([minYear, maxYear])
    .range(["#f3f14d", "#e47673"])
    .interpolate(d3.interpolateRgb);
  
  // ========================================
  // DIMENSION CALCULATIONS
  // ========================================
  const numMultiples = bins.length;
  
  // calculate reasonable grid size based on available width
  const maxGridWidth = Math.min(140, (width - 60) / numMultiples);
  
  // calculate grid dimensions
  const gridDimensions = PlotHelpers.calculateBubbleGridDimensions(maxGridWidth, 10, 20);
  const { bubbleSize, bubbleSpacing, gridWidth, gridHeight } = gridDimensions;
  
  // account for bubble overhang
  const overhangDimensions = PlotHelpers.calculateBubbleGridOverhang(gridWidth, bubbleSize);
  const { effectiveGridWidth, paddingOffset } = overhangDimensions;
  
  // calculate layout with proper spacing between panels
  const layoutDimensions = PlotHelpers.calculateSmallMultiplesDimensions(
    width,
    numMultiples,
    effectiveGridWidth,
    Math.max(5, gridWidth * 0.05)
  );
  const { panelSpacing, startX } = layoutDimensions;
  
  // add padding on left side for first bubble
  const adjustedStartX = startX + paddingOffset;
  
  const totalWidth = width;
  const calculatedHeight = gridHeight + 330; // (extra space for wrapped labels)
  
  // ========================================
  // STYLING CALCULATIONS
  // ========================================
  // (use helper functions from plot-helpers.js for all styling calculations)
  const fontSizes = PlotHelpers.calculateFontSizes(width, calculatedHeight);
  const lineHeights = PlotHelpers.calculateLineHeights(fontSizes);
  const panelFontSizes = PlotHelpers.calculateSmallMultiplesFontSizes(width, numMultiples);
  
  // text content
  const titleText = `Progression of Deforestation Over Time, ${minYear}-${maxYear}`;
  const titleLocation = countryName ? `${cityName}, ${countryName}` : cityName;
  const descriptionText = `100 bubbles = 100% of total deforestation (${totalDeforestation} pixels = ${finalForestLostPercent.toFixed(2)}% of original forest)`;
  const captionText = ""; // (empty for this plot)
  
  // text wrapping
  const titleLines = PlotHelpers.wrapText(titleText, width - 40, `${fontSizes.title}px system-ui`);
  const subtitleLines = PlotHelpers.wrapText(titleLocation, width - 40, `${fontSizes.subtitle}px system-ui`);
  const descriptionLines = PlotHelpers.wrapText(descriptionText, width - 40, `${fontSizes.caption}px system-ui`);
  const captionLines = PlotHelpers.wrapText(captionText, width - 40, `${fontSizes.caption}px system-ui`);

  // calculate text dimensions
  const captionHeight = captionText ? captionLines.length * lineHeights.caption : 0;

  // ========================================
  // SVG CREATION
  // ========================================
  const svg = d3.create("svg")
    .attr("viewBox", `0 0 ${totalWidth} ${calculatedHeight}`)
    .attr("preserveAspectRatio", "xMidYMid meet")
    .style("width", "100%")
    .style("height", "auto")
    .style("max-width", `${totalWidth}px`);
  
  // ========================================
  // TITLE
  // ========================================
  const heightScale = calculatedHeight / PlotHelpers.PLOT_BASE.HEIGHT;
  const titleY = PlotHelpers.getTitleY(calculatedHeight, heightScale);
  
  titleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-title")
      .attr("x", 20)
      .attr("y", titleY + (i * lineHeights.title))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.title}px`)
      .text(line);
  });
  
  // ========================================
  // SUBTITLE
  // ========================================
  const subtitleY = PlotHelpers.getSubtitleY(titleY, titleLines.length, lineHeights.title, heightScale);
  
  subtitleLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-subtitle")
      .attr("x", 20)
      .attr("y", subtitleY + (i * lineHeights.subtitle))
      .attr("text-anchor", "start")
      .style("font-size", `${fontSizes.subtitle}px`)
      .text(line);
  });
  
  // ========================================
  // DESCRIPTION
  // ========================================
  const descriptionY = subtitleY + (subtitleLines.length * lineHeights.subtitle) + (5 * heightScale);
  
  descriptionLines.forEach((line, i) => {
    svg.append("text")
      .attr("class", "plot-description")
      .attr("x", 20)
      .attr("y", descriptionY + (i * lineHeights.caption))
      .attr("text-anchor", "start")
      .attr("fill", "#666")
      .style("font-size", `${fontSizes.caption}px`)
      .text(line);
  });
  
  // ========================================
  // CREATE EACH SMALL MULTIPLE
  // ========================================
  const yOffset = descriptionY + (descriptionLines.length * lineHeights.caption) + 20;
  
  bins.forEach((bin, binIndex) => {
    // calculate panel x offset
    const xOffset = PlotHelpers.calculatePanelXOffset(binIndex, effectiveGridWidth, panelSpacing, adjustedStartX);
    
    // calculate panel label position
    const panelPosition = PlotHelpers.calculatePanelLabelPosition(xOffset, gridWidth);
    const { centerX } = panelPosition;
    
    // (number of bubbles = percentage of total deforestation reached)
    const numBubbles = Math.round(bin.percentOfTotalDeforestation);
    
    // color based on year
    const binColor = colorScale(bin.startYear);
    
    // generate bubble grid data
    const bubbleGridData = PlotHelpers.generateBubbleGridData(100, 10);
    
    const bubbleData = bubbleGridData.map(bubble => {
      const filled = bubble.id < numBubbles;
      
      // calculate position
      const position = PlotHelpers.calculateBubblePosition(
        bubble.row,
        bubble.col,
        bubbleSpacing,
        xOffset,
        yOffset
      );
      
      return {
        ...bubble,
        ...position,
        filled,
        binColor
      };
    });
    
    // draw bubbles for this small multiple
    svg.selectAll(`.bubble-${binIndex}`)
      .data(bubbleData)
      .enter().append("circle")
      .attr("class", `bubble-${binIndex}`)
      .attr("cx", d => d.cx)
      .attr("cy", d => d.cy)
      .attr("r", bubbleSize / 2)
      .attr("fill", d => d.filled ? d.binColor : "currentColor")
      .attr("stroke", d => d.filled ? d3.color(d.binColor).darker(0.3) : "#dee2e6")
      .attr("stroke-width", 0.5)
      .attr("opacity", d => d.filled ? 0.9 : 0.1);
    
    // year label above each small multiple
    svg.append("text")
      .attr("x", centerX)
      .attr("y", yOffset - 10)
      .attr("text-anchor", "middle")
      .attr("fill", "currentColor")
      .style("font-size", `${panelFontSizes.panelLabel}px`)
      .style("font-weight", "bold")
      .text(bin.label);
    
// calculate stats positions
const statsPositions = PlotHelpers.calculatePanelStatsPositions(gridHeight, yOffset, 15);

// percentage of total deforestation
svg.append("text")
  .attr("x", centerX)
  .attr("y", statsPositions.stat1Value)
  .attr("text-anchor", "middle")
  .attr("fill", binColor)
  .style("font-size", `${panelFontSizes.panelValue}px`)
  .style("font-weight", "bold")
  .text(`${bin.percentOfTotalDeforestation.toFixed(0)}%`);

// "of total" label (use smaller font at narrow widths)
const ofTotalFontSize = Math.max(6, panelFontSizes.panelDescription * 0.9);
const ofTotalLines = PlotHelpers.wrapShortLabel("of total", gridWidth, `${ofTotalFontSize}px system-ui`);
let currentY = statsPositions.stat1Label;
ofTotalLines.forEach((line, i) => {
  svg.append("text")
    .attr("x", centerX)
    .attr("y", currentY)
    .attr("text-anchor", "middle")
    .attr("fill", "currentColor")
    .style("font-size", `${ofTotalFontSize}px`)
    .text(line);
  currentY += ofTotalFontSize * 1.2;
});

// cumulative forest loss percentage (smaller, gray text) - wrap each part
const smallerFontSize = Math.max(5, panelFontSizes.panelDescription * 0.75);

// first line: "(x.xx% of"
const line1Text = `(${bin.percentForestLost.toFixed(2)}% of`;
const line1Wrapped = PlotHelpers.wrapShortLabel(line1Text, gridWidth, `${smallerFontSize}px system-ui`);

line1Wrapped.forEach((line, i) => {
  svg.append("text")
    .attr("x", centerX)
    .attr("y", statsPositions.stat2Value + (i * smallerFontSize * 1.2))
    .attr("text-anchor", "middle")
    .attr("fill", "#666")
    .style("font-size", `${smallerFontSize}px`)
    .text(line);
});

// second line: "original forest)"
const line2Wrapped = PlotHelpers.wrapShortLabel("original forest)", gridWidth, `${smallerFontSize}px system-ui`);
let line2Y = statsPositions.stat2Value + (line1Wrapped.length * smallerFontSize * 1.2);

line2Wrapped.forEach((line, i) => {
  svg.append("text")
    .attr("x", centerX)
    .attr("y", line2Y + (i * smallerFontSize * 1.2))
    .attr("text-anchor", "middle")
    .attr("fill", "#666")
    .style("font-size", `${smallerFontSize}px`)
    .text(line);
});
  });
  
  // ========================================
  // LEGEND
  // ========================================
  // (at bottom)
  const legendY = calculatedHeight - (captionHeight > 0 ? captionHeight + 60 : 50);
  const legendText = "Each filled bubble represents 1% of the total deforestation that occurred from 2001-2023";
  const legendLines = PlotHelpers.wrapText(legendText, width - 40, `${fontSizes.caption}px system-ui`);
  
  legendLines.forEach((line, i) => {
    svg.append("text")
      .attr("x", width / 2)
      .attr("y", legendY + (i * lineHeights.caption))
      .attr("text-anchor", "middle")
      .attr("fill", "currentColor")
      .style("font-size", `${fontSizes.caption}px`)
      .text(line);
  });

  // ========================================
  // CAPTION
  // ========================================
  // (empty for this plot)
  if (captionText) {
    const captionY = PlotHelpers.getCaptionY(calculatedHeight, heightScale);
    
    captionLines.forEach((line, i) => {
      svg.append("text")
        .attr("class", "plot-caption")
        .attr("x", 20)
        .attr("y", captionY - ((captionLines.length - 1 - i) * lineHeights.caption))
        .attr("text-anchor", "start")
        .style("font-size", `${fontSizes.caption}px`)
        .text(line);
    });
  }
  
  return svg.node();
}

export {
  // Helper functions
  calculateAgeDependencyRatios,
  // Plot functions
  plot_pga,
  plot_pgp,
  plot_pas,
  plot_pas_pyramid,
  plot_age,
  plot_dependency,
  plot_rwi_area,
  plot_uba_area,
  plot_ubaa,
  plot_ubap,
  plot_uba_tracker,
  plot_lc,
  plot_uddm,
  plot_pv_area,
  plot_pv_alt,
  plot_pv_d,
  plot_pv,
  plot_aq,
  plot_summer_area,
  plot_ndvi_area,
  plot_fe,
  plot_fu,
  plot_pu,
  plot_cu,
  plot_comb,
  plot_e,
  plot_s,
  plot_ls_area,
  plot_l_area,
  plot_fwi,
  plot_fwi_d,
  plot_flood_prob,
  plot_ee,
  plot_wsf_harmonized,
  plot_wsf_growth,
  plot_ce,
  plot_deforestation_area1,
  plot_deforestation_area2,
  plot_deforestation_area3,
  plot_deforestation_area4,
  plot_deforestation_area5,
  plot_deforestation_area6
};

// Default export with init - use: import p from "./ojs/plots.js"
export default function() {
  return {
    plot_pga, plot_pgp, plot_pas, plot_pas_pyramid, plot_age, plot_dependency,
    plot_rwi_area, plot_uba_area, plot_ubaa, plot_ubap, plot_lc, plot_uddm,
    plot_pv_area, plot_pv_alt, plot_pv_d, plot_pv, plot_aq, plot_summer_area,
    plot_ndvi_area, plot_fe, plot_fu, plot_pu, plot_cu, plot_comb,
    plot_e, plot_s, plot_ls_area, plot_l_area, plot_fwi, plot_fwi_d,
    plot_flood_prob, plot_ee, plot_wsf_harmonized, plot_wsf_growth,
    plot_ce, plot_deforestation_area1, plot_deforestation_area2, plot_deforestation_area3, plot_deforestation_area4, plot_deforestation_area5, plot_deforestation_area6
  };
}
