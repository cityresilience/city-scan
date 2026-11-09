# City Scan unified image — ONE container with both runtimes:
# Python drives (`python -m tasks`), shelling out to Rscript/quarto mid-run.
# Adapted from deploy/frontend/Dockerfile (old "nalgene" R image), plus Python.
# Build:  docker build -t cityscan .
# Run:    docker run --rm cityscan --check
#         docker run --rm cityscan --all --gcs --scan-id <id> --upload

ARG R_VERSION=4.3.2
FROM rocker/r-ver:${R_VERSION}
LABEL name=cityscan \
  organization="World Bank Group" \
  description="City Resilience Program City Scans (collection + analysis + render)"

# Install R-related tools
# While rocker has specific images for tidyverse and geospatial, they are not arm64 compatible
RUN set -e \
    && /rocker_scripts/install_tidyverse.sh \
    && /rocker_scripts/install_geospatial.sh \
    && /rocker_scripts/install_pandoc.sh \
    && export QUARTO_VERSION=1.5.57 \
    && /rocker_scripts/install_quarto.sh

# Install dependencies
RUN set -e \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        apt-utils \
        curl \
        gnupg \
        lsb-release \
        tini \
        wget && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Install gcloud
RUN set -e \
    && echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] http://packages.cloud.google.com/apt cloud-sdk main" | tee -a /etc/apt/sources.list.d/google-cloud-sdk.list \
    && curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | apt-key --keyring /usr/share/keyrings/cloud.google.gpg add - \
    && apt-get update \
    && apt-get install -y google-cloud-sdk \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install Python 3.11 (repo pin: .python-version 3.11.8; Ubuntu 22.04 ships 3.10)
RUN set -e \
    && apt-get update \
    && apt-get install -y --no-install-recommends software-properties-common \
    && add-apt-repository -y ppa:deadsnakes/ppa \
    && apt-get update \
    && apt-get install -y --no-install-recommends python3.11 python3.11-venv python3.11-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/* \
    && python3.11 -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

WORKDIR /app

# Python packages (own layer: re-runs only when requirements.txt changes)
# PIP_CONSTRAINT: packages without arm64 wheels (rasterio 1.3.8) build from
# source and need setuptools' pkg_resources, removed in setuptools >= 81
COPY requirements.txt ./
RUN printf 'setuptools<81\n' > /tmp/pip-constraints.txt
ENV PIP_CONSTRAINT=/tmp/pip-constraints.txt
RUN pip install --no-cache-dir -r requirements.txt

# R packages baked at build time via core/R/deps.R (the authority on R deps —
# includes github rspatial/terra + ggplot2 4.0 upgrade); otherwise librarian
# compiles them at every job start. deps.R reads source/layers.yml via here(),
# so give it an EMPTY placeholder (read_yaml -> NULL, fine at build) — the real
# file lands with COPY source below, so config edits don't bust this layer.
COPY core/R/deps.R core/R/deps.R
# Live CRAN repo (rocker pins a frozen snapshot — its ggplot2 tops out at 3.5);
# explicit github terra because librarian::shelf skips already-installed pkgs
# (rocker preinstalls CRAN terra). Version check = fail loud, match local env.
RUN touch .here && mkdir -p source && touch source/layers.yml \
    && Rscript -e "options(repos = c(CRAN = 'https://cloud.r-project.org')); install.packages('here'); library(here); source('core/R/deps.R')" \
    && Rscript -e "options(repos = c(CRAN = 'https://cloud.r-project.org')); remotes::install_github('rspatial/terra')" \
    && Rscript -e "stopifnot(packageVersion('ggplot2') >= '4.0.0', packageVersion('terra') >= '1.9.0')"

# Copy the codebase (last: code-only edits rebuild just this layer)
COPY core ./core
COPY tasks ./tasks
COPY source ./source
COPY scan-calculations ./scan-calculations
COPY inputs ./inputs
COPY templates ./templates

ENV PYTHONUNBUFFERED=1

# Use tini to manage zombie processes and signal forwarding
# Execution args append to `python -m tasks`, e.g. --args="--all,--gcs,--scan-id,<id>,--upload"
ENTRYPOINT ["/usr/bin/tini", "--", "python", "-m", "tasks"]
