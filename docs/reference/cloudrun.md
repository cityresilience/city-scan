# Cloud Run workflows

Practical how-to for running scans, delivery, and publishing on Cloud Run.
For the image/build internals (Dockerfile, caching, job config), see
[`deploy/cloudrun.md`](../../deploy/cloudrun.md).

- **GCP project:** `city-scan-gee-test`
- **Job:** `cityscan` (one execution per run)
- **Region:** `us-central1`
- **Data bucket:** `gs://crp-city-scan/<scan_id>/`

The CLI is `python -m tasks …` (aliased to `scan`). `--cloudrun` submits the run to
the `cityscan` Cloud Run job instead of running locally.

---

## Setup (one-time, per person)

The project, region, job name, and image are **fixed in the code** — you never pass them:

| what | value | defined in |
|---|---|---|
| GCP project | `city-scan-gee-test` | `core/config/run.py` `CLOUDRUN_PROJECT` |
| Cloud Run job | `cityscan` | `core/config/run.py` `CLOUDRUN_JOB` |
| region | `us-central1` | `core/config/run.py` `CLOUDRUN_REGION` |
| image | `us-central1-docker.pkg.dev/city-scan-gee-test/cityscan/cityscan` | `cloudbuild.yaml` `_IMAGE` |

What **you** set up is auth — that's the "IAM" (who Google sees you as):

```bash
gcloud auth login                              # your Google account
gcloud auth application-default login          # app-default creds (GCS + GEE from the pipeline)
gcloud config set project city-scan-gee-test   # optional — commands pass --project explicitly
earthengine authenticate                       # Earth Engine (once)
```

Then ask whoever owns `city-scan-gee-test` to grant you access on that project:
- **Cloud Build** (submit builds), **Cloud Run** (update + execute the `cityscan` job),
  **Artifact Registry** (push the image), and read/write on the `crp-city-scan` +
  `cityresilience` buckets.
- Registered as an **Earth Engine** user on the project.

You do **not** edit the constants above — the whole team builds/runs against the same
project, job, and image. Your identity is the only thing that differs.

---

## 1. Rebuild the image (deploy code changes)

Cloud Run runs a **frozen image** — code changes only take effect after a rebuild.

**The build is from your LOCAL working directory**, not from GitHub. `gcloud builds submit`
uploads your local repo dir as the build context and builds *that* — so whatever is on your
disk is what gets deployed. There is **no build-on-push trigger**; a `git push` does not
rebuild anything.

```bash
# rebuild + push the image (x86, built on GCP) — deploys your LOCAL code
gcloud builds submit --project=city-scan-gee-test
```

- Cached build (code/config edits) ≈ 1–2 min. Only `requirements.txt` or `core/R/deps.R`
  changes trigger the slow (~1 h) package layers.
- Nothing on Cloud Run picks up your edit until this rebuild finishes.
- Watch: <https://console.cloud.google.com/cloud-build/builds?project=city-scan-gee-test>

---

## 2. `--cloudrun` — run tasks on Cloud Run

Runs `<tasks>` for a city whose data lives in the bucket (`--scan-id`).

```bash
scan <tasks> --collect --cloudrun --scan-id <scan_id>
# e.g.
scan dust aerosol precipitation --collect --cloudrun --scan-id 2026-07-uzbekistan
scan --all --collect --analyze --cloudrun --scan-id 2026-07-uzbekistan
```

- Independent tasks **fan out** — one container per dependency chain, in parallel.
- Add `--analyze` to recompute the CSVs, `--all` to run every menu-enabled task.
- GEE tasks use `ee.batch.Export` (server-side, batch quota — not the interactive EECU pool).

**What actually happens (build vs. run):** the build (step 1) only updates the **image**.
The Cloud Run **job** `cityscan` is a persistent template pointing at `:latest`. Each
`--cloudrun` run does two gcloud calls under the hood (`run.py`):

1. `gcloud run jobs update cityscan --tasks=<n>` — set the container count (fan-out)
2. `gcloud run jobs execute cityscan --args=<your CLI args>` — start one **execution**

Cloud Run auto-names each execution `cityscan-<random>` (e.g. `cityscan-j89jk`), which pulls
`:latest`, runs `python -m tasks <args>`, and dies. So: **image built once (step 1); each
`--cloudrun` = one `cityscan-xxxxx` execution.**

**Monitor a run:**
```bash
gcloud run jobs executions describe <exec_name> \
  --region=us-central1 --project=city-scan-gee-test \
  --format='value(status.runningCount,status.succeededCount,status.failedCount)'
```
Note: a container exiting 0 ("succeeded") does **not** mean the task succeeded — check the
per-container `task_report.<idx>.txt` / `app.<idx>.log` in `gs://crp-city-scan/<scan_id>/logs/`,
or confirm the actual output file landed in `.../02-process-output/spatial/`.

---

## 3. `--collect` a crop-fed city (bucketdata)

For a **crop-fed** city (a single city inside a national/regional scan), set the source
scan in the city's `city_inputs.yml`:

```yaml
bucketdata: crp-city-scan/2026-07-uzbekistan   # the larger scan to collect (crop) from
AOI_shp_name: Chust_fua                         # this city's boundary
```

Then just **collect** — with `bucketdata` set, collect doesn't run GEE; it masks every
layer in the source scan's `02-process-output/spatial/` to this city's AOI (renaming
`<src>_X` → `<city>_X`):

```bash
scan --collect --scan-id <scan_id>            # collects by cropping from bucketdata (no GEE)
scan --collect --analyze --scan-id <scan_id>  # + recompute CSVs from the cropped data
```

That's it — you don't pass any flag for "crop". (`--crop` forces the same behaviour
explicitly, but it's redundant: on a `bucketdata` scan, **collect *is* the crop**.)

Collecting reprojects the AOI into each raster's CRS, so mixed-CRS sources crop fine, but the
**output keeps the source CRS** — reproject non-4326 layers to 4326 afterward if needed for the web.

---

## 4. `--cogify` — deliver COGs

Turns each `02-process-output` raster into a Cloud-Optimized GeoTIFF, copies vectors/tabular
as-is, and writes a manifest to the target in `cogify.yml` (`target.bucket` / `prefix`).

First time: copy the template and set your delivery target:
```bash
cp templates/cogify.yml inputs/cogify.yml   # then edit target.bucket / prefix + any extra layers
scan --cogify --cloudrun --scan-id <scan_id>
```

- Run it **on `--cloudrun`** so it reads the regional bucket data (running locally reads a
  possibly-stale local `mnt/` copy).
- Resampling per layer comes from `cogify.yml` (`nearest` for categorical, `average` for
  continuous). With `--scan-id`, cogify reads the **bucket's** `01-user-input/cogify.yml` —
  keep it in sync (`gcloud storage cp inputs/cogify.yml gs://crp-city-scan/<scan_id>/01-user-input/`).

---

## 5. `--publish` — publish reports to GitHub Pages

Copies a rendered report into the delivery repo (`cityresilience/delivery`) and pushes.
Render first — `--publish` only copies `_site`, it does not render.

```bash
cd mnt/<scan_id> && quarto render                       # produces _site/
scan --publish <folder> --scan-id <scan_id>             # -> <folder>/<city>/
scan --publish --scan-id <scan_id>                      # -> <country-city>/ (scan-id minus date)
# e.g.
scan --publish uzbekistan-atlas --scan-id 2026-07-uzbekistan-chust
```

→ live at `https://cityresilience.github.io/delivery/<folder>/<city>/publish/`

Each run does a fresh `gh repo clone` into a temp dir, so it's not tied to any local clone.
**Requirements (per person):** `gh auth login` with write access to `cityresilience/delivery`,
and a configured git identity (`git config --global user.name/user.email`) — the commit is
authored by whoever runs it.

