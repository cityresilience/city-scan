# Setup Instructions 

<!-- ## Required and Recommended Software -->

<!-- For all activities, see
- [VS Code](#vs-code) (recommended) -->

<!-- For running a City Scan on Google Cloud, see
- [gcloud](#gcloud) (required) -->

<!-- To run visualizations and reports locally, you can run with [Docker](#docker) or natively. If using Docker, you will only need Docker, in addition to Git and an editor like VS Code. (The frontend script also requires gcloud, but we will add instructions that don't require it.)  -->

City Scan repo is multilangual: Python is used for data collection and analysis, R for mapping and charting, and Quarto for report compilation and web visualization. 

All City Scan tasks can be accessed through terminal with the required tools configured:

- [Git](#git)
- [Python](#python) 
- [R](#r)
- [Quarto](#quarto)
- [gcloud](#gcloud) 

Recommended:
- [Visual Studio Code]( #vs-code)


The following sections describe the recommended setup configuration and best practices.

---

### Authentication

Authentication is managed in `core/config/`:

- **`auth.py`** — initializes Google Earth Engine (GEE) and Google Cloud Storage (GCS) credentials
- **`scan.py`** — the Scan class that loads AOI, city config, and creates city output folders
- **`paths.py`** — auto-detects input/output directories based on project structure
- **`gdal_auth.py`** — configures GDAL for authenticated access to private GCS buckets via `/vsigs/`

Tasks that need GEE (forest, landcover, LST, NDVI, nightlight) or private GCS (WSF, fathom, landcover burn, basic info) are automatically authenticated before running. If auth fails, those tasks are skipped with a warning.

See [google cloud setup](../reference/googlecloud.md) for more details.


--- 

### Git

Git is a version control system. It's a timewarpy quantum tool that lets multiple dimensions and times exist at once. It lets you keep multiple versions of your files, and keep track of changes. It also makes it easier to collaborate with each other, as a conduit for "pulling" and "pushing" and "pulling" code from and to GitHub. Instead of downloading a repo from GitHub, you can "clone" it – which is still downloading, but with the added benefit of keeping a live connection to future changes (at your discretion). 

Git is already installed on most macOS and Linux systems. You can install it from [Git for Windows](https://gitforwindows.org/). If git is not installed, see the GitHub's [git installation guide](https://github.com/git-guides/install-git)


---

### Python

We recommend creating a python environment to run City Scan Tasks. Here are the options:


#### *Option 1*: Via Conda (Recommended for Mac, Windows, Linux)

##### Step 1: Install Anaconda

 Download and install Anaconda from the [official Anaconda website](https://www.anaconda.com/download): 

- Visit https://www.anaconda.com/download and select your operating system
- Follow the installation wizard and accept the default settings
- Restart your terminal after installation completes
- Verify installation by running: `conda --version`

> **If `conda --version` returns `command not found`** (especially in the VS Code integrated terminal), conda was installed but not initialized for your shell. Run once:
> ```bash
> conda init zsh        # macOS / Linux (zsh — default on modern macOS)
> conda init bash       # Linux / older macOS / WSL
> conda init powershell # Windows PowerShell
> ```
> Then close and reopen the terminal. You should see `(base)` in your prompt and `conda` should resolve.


##### Step 2: Create and Activate the Environment

```bash
conda create -n cityscan python=3.11.8 -y
conda activate cityscan
```

##### Step 3: Install Dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

##### Step 4: Register Jupyter Kernel (Optional, for notebook use)

```bash
python -m ipykernel install --user --name cityscan --display-name "Cityscan"
```




#### *Option 2*: Via Bootstrap Script (Alternative Setup -- only for Mac, Linux)

If you prefer automated system setup or Python is not installed, use the bootstrap approach:

##### Step 1: Clone the Repository

```bash
git clone --single-branch --branch unified https://github.com/varinaldi/city-scan-automation.git
cd city-scan-automation
```

##### Step 2: Run Bootstrap Script

This script prepares your system and installs Python 3.11.8 via pyenv:

```bash
bash bootstrap.sh
```

If you need to manually activate the environment later, use:

```bash
source venv/bin/activate
```

**Note:** Review the `bootstrap.sh` script first to ensure it meets your system requirements. It will:
- Install system dependencies
- Install and configure pyenv
- Install Python 3.11.8
- Update your shell configuration

If pyenv is installed for the first time, restart your terminal and run the script again.

##### Step 3: Run Setup Script

This script creates the virtual environment, installs dependencies, and registers the Jupyter kernel:

```bash
bash orchestrator.sh
```

When setup is successful, you should see:
- Python 3.11.8 ready via pyenv
- A new virtual environment created
- A Jupyter kernel registered: "Cityscan (Python 3.11)"


---

### R

R is used for the maps, charts, and scan-calculations report, and also for several data collection tasks (earthquake, oxford, cyclones, flood_events, gdp_gridded, coastal_erosion, sea_level_rise). You can download R [here](https://cran.r-project.org/). **Use the latest stable R release** (currently 4.5.x) — the repo depends on a current `ggplot2`, `terra`, `sf`, and `tidyterra` stack that won't install cleanly on older R. If you already have R, run `R --version` and upgrade if you're behind. To use R in VS Code, we recommend installing the [R extension](https://marketplace.visualstudio.com/items?itemName=REditorSupport.r): follow the instructions at the link; we also recommend installing [radian](https://github.com/randy3k/radian).

If you have used R in the past, you likely used RStudio as your editor. For the City Scan workflow and development, we recommend VS Code as it supports multiple languages and has a better terminal and Git integration. Still, RStudio can still be useful, and can be downloaded [here](https://posit.co/download/rstudio-desktop/).

---

### Quarto

Quarto is a publishing system that lets you create documents and websites with R, Python, JavaScript, and Julia. If you are familiar with R Markdown, Jupyter notebooks, or Observable notebooks, Quarto is similar but allows for the use of multiple languages in the same document. It is used to create the City Scan reports and website.

A Quarto file is a markdown document with code chunks that can be rendered into HTML, PDF, or other formats. The Python and R code is executed at the time of rendering and the output is included in the final document.

To install Quarto, follow the instructions at [Quarto's installation page](https://quarto.org/docs/get-started/).

---

### VS Code

VS Code isn't strictly necessary, but it makes working with multiple files and filetypes much easier. It also makes working with [Git](#git) much clearer. VS Code is a free code editor with an integrated terminal and near endless extensions. (If you're coming from R, you've probably been using RStudio; VS Code is like RStudio but for all languages, a better terminal, easier Git integration and better handling of multiple windows. If you're coming from Python, I'm not and don't know what you're probably using.)

Install VS Code from [Visual Studio Code](https://code.visualstudio.com/Download).

**Recommended extensions** for working with this repo:

- [Python](https://marketplace.visualstudio.com/items?itemName=ms-python.python) — Python language support
- [R](https://marketplace.visualstudio.com/items?itemName=REditorSupport.r) — R language support
- [Quarto](https://marketplace.visualstudio.com/items?itemName=quarto.quarto) — Quarto rendering + preview
- [Rainbow CSV](https://marketplace.visualstudio.com/items?itemName=mechatroner.rainbow-csv) — color-coded columns for the many CSVs under `02-process-output/tabular/`
- [Color Highlight](https://marketplace.visualstudio.com/items?itemName=naumovs.color-highlight) — inline color swatches for hex codes in `source/layers.yml`
- [Geo Data Viewer](https://marketplace.visualstudio.com/items?itemName=RandomFractalsInc.geo-data-viewer) — preview `.geojson`, `.shp`, and other vector files on a map
- [GeoTIFF Viewer](https://marketplace.visualstudio.com/items?itemName=omar2535.geotiff-viewer) — preview `.tif` rasters directly in the editor
<!-- 
### gcloud

The Google Cloud SDK, gcloud, is a commmand line tool for interacting with Google Cloud Platform. It lets us download and upload files from and to Cloud Storage, run Jobs, and so forth. You can do most of these things in the browser, but gcloud is often much more convenient.

The standard install instructions are [here](https://cloud.google.com/sdk/docs/install); slightly simpler instructions are [here](https://cloud.google.com/sdk/docs/downloads-interactive)

### Docker

Docker lets all of us, with our different devices, operating systems and softwares, pretend we all have the same setup. It lets us define and run *containers*, essentially mini virtual machines that can run anywhere Docker is installed. Docker is most important for us because it's how we package code up to run on Google Cloud, but it's also helpful for running code locally.

With Docker, we write instructions (a Dockerfile) that define a Docker *image*. This image defines the operating system, software, libraries, and code that will … TK

To install, follow the instructions at https://docs.docker.com/desktop. -->



<!-- --- -->

---

