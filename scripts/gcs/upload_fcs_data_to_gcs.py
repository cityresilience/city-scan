"""Mirror the FCS global input data into gs://city-scan-global-data/.

    python upload_fcs_data_to_gcs.py --dry-run     # manifest + byte count only
    python upload_fcs_data_to_gcs.py               # the working set (~34 GB)
    python upload_fcs_data_to_gcs.py --all         # every folder the code reads
    python upload_fcs_data_to_gcs.py --verify      # compare local vs bucket, no writes

Companion to `upload_ucra_data_to_gcs.py`, and deliberately the same shape:
Application Default Credentials, skip-if-a-blob-of-the-same-size-exists (so an
interrupted run resumes), 8 MiB resumable chunks, long timeouts and retries —
that combination is what took the earlier 58 GB UCRA push from 17 timeout
failures to zero.

WHY ONLY PART OF FCS/data
-------------------------
`FCS/data/` is ~160 GB across 28 folders, but grepping the canonical pipeline's
`src/*.py` shows only 8 of them are ever read. The rest are duplicates and dead
weight (`Extreme Heat Days - Copy`, `globalerosion` vs `globalErosionProjections`,
`fathomclean`, `test_cities`, `archive`) or belong to older notebooks
(`climatecentral` alone is 251,000 files / 22.6 GB).

WORKING_SET is narrower still: the folders needed by the FCS steps that actually
SUCCEED for the Pakistan MCs. `gdp` and `fathom` are referenced but excluded —
gdp fails for these cities (they are absent from the IIASA Global Cities DB) and
the flood steps skip (no Pakistan Fathom). Add them with --all when a country
that can use them comes along.
"""
import argparse
import os
import sys
import concurrent.futures as cf
from pathlib import Path

from google.cloud import storage

# scripts/gcs/<this> -> repo root, so the shared path resolver is importable.
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
from core.config.paths import external_dir  # noqa: E402

BUCKET = "city-scan-global-data"
DEST_PREFIX = "fcs-data"
INPUTS_PREFIX = "fcs-inputs"

# Folders the FCS steps that succeed for these MCs need. ~34 GB.
WORKING_SET = [
    "urbanland",          # 13.25 GB — urbanland step
    "popdynamics",        # 14.36 GB — population, country_population_ratio
    "heatflux",           #  5.74 GB — heatflux step
    "demographic",        #  0.67 GB — demographics step
    "urbanheatisland",    #  0.04 GB — urbanheatisland step
    "CCKP",               #  empty locally; kept so the prefix exists
]
# Everything the code references, for other countries. ~121 GB.
FULL_SET = WORKING_SET + [
    "gdp",                       # 56.85 GB — gdp, gdp_rescaling, country_gdp_ratio
    "fathom",                    # 30.32 GB — flood_*_exposure
    "globalErosionProjections",  #  0.13 GB — erosion
]


def manifest(folders):
    """(local_path, blob_name, size) for every file to mirror."""
    out = []
    for folder in folders:
        root = os.path.join(DATA_ROOT, folder)
        if not os.path.isdir(root):
            print(f"  ! skipping '{folder}' — not found at {root}")
            continue
        for dirpath, _dirs, files in os.walk(root):
            for fn in files:
                lp = os.path.join(dirpath, fn)
                rel = os.path.relpath(lp, DATA_ROOT).replace("\\", "/")
                out.append((lp, f"{DEST_PREFIX}/{rel}", os.path.getsize(lp)))
    if os.path.isdir(SHAPEFILES_ROOT):
        for dirpath, _dirs, files in os.walk(SHAPEFILES_ROOT):
            for fn in files:
                lp = os.path.join(dirpath, fn)
                rel = os.path.relpath(lp, SHAPEFILES_ROOT).replace("\\", "/")
                out.append((lp, f"{INPUTS_PREFIX}/shapefiles/{rel}", os.path.getsize(lp)))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true",
                    help="every folder the pipeline reads (~121 GB), not just the working set")
    ap.add_argument("--dry-run", action="store_true", help="print the plan, upload nothing")
    ap.add_argument("--verify", action="store_true",
                    help="compare local against the bucket and report gaps; no writes")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--fcs-dir", default=None,
                    help="FCS tree root; default is menu.yml / $CITYSCAN_FCS_DIR "
                         "/ <repo parent>/FCS")
    args = ap.parse_args()

    global DATA_ROOT, SHAPEFILES_ROOT
    base = (Path(args.fcs_dir).expanduser().resolve() if args.fcs_dir
            else external_dir({}, "fcs_base_dir", "CITYSCAN_FCS_DIR", "FCS"))
    DATA_ROOT = str(base / "data")
    # Lives outside data/ but the pipeline can't start without it (country borders).
    SHAPEFILES_ROOT = str(base / "01-inputs" / "shapefiles")
    if not os.path.isdir(DATA_ROOT):
        sys.exit(f"FCS data tree not found: {DATA_ROOT}\n"
                 "Set CITYSCAN_FCS_DIR, or pass --fcs-dir.")
    print(f"Source: {base}")

    folders = FULL_SET if args.all else WORKING_SET
    print(f"Set: {'FULL' if args.all else 'WORKING'}  ({len(folders)} folders)")

    tasks = manifest(folders)
    by_folder = {}
    for lp, blob, size in tasks:
        key = blob.split("/")[1] if blob.startswith(DEST_PREFIX) else "01-inputs/shapefiles"
        n, b = by_folder.get(key, (0, 0))
        by_folder[key] = (n + 1, b + size)
    print(f"\nLocal manifest — {len(tasks):,} files, "
          f"{sum(t[2] for t in tasks)/1e9:.2f} GB")
    for k in sorted(by_folder, key=lambda x: -by_folder[x][1]):
        n, b = by_folder[k]
        print(f"  {k:32s} {n:>7,} files  {b/1e9:>8.2f} GB")

    client = storage.Client()
    bucket = client.bucket(BUCKET)

    print(f"\nListing gs://{BUCKET}/{DEST_PREFIX}/ and /{INPUTS_PREFIX}/ ...", flush=True)
    existing = {}
    for prefix in (f"{DEST_PREFIX}/", f"{INPUTS_PREFIX}/"):
        for b in client.list_blobs(bucket, prefix=prefix):
            existing[b.name] = b.size
    print(f"  {len(existing):,} objects already there")

    todo = [t for t in tasks if existing.get(t[1]) != t[2]]
    todo.sort(key=lambda t: t[2])          # smallest first: partial state stays useful
    skipped = len(tasks) - len(todo)
    print(f"\nalready present: {skipped:,} | to upload: {len(todo):,} "
          f"({sum(t[2] for t in todo)/1e9:.2f} GB)")

    if args.verify:
        missing = [t for t in tasks if t[1] not in existing]
        wrong = [t for t in tasks if t[1] in existing and existing[t[1]] != t[2]]
        print(f"\nVERIFY — missing: {len(missing)} | size mismatch: {len(wrong)}")
        for lp, blob, size in (missing + wrong)[:15]:
            print(f"  {blob}  local={size:,} remote={existing.get(blob)}")
        return 0 if not (missing or wrong) else 1

    if args.dry_run:
        print("\n--dry-run: nothing uploaded.")
        return 0
    if not todo:
        print("\nNothing to do — the bucket already matches.")
        return 0

    def upload(t):
        lp, blob_name, _ = t
        last = None
        for _ in range(4):
            try:
                blob = bucket.blob(blob_name, chunk_size=8 * 1024 * 1024)
                blob.upload_from_filename(lp, timeout=900)
                return
            except Exception as e:  # noqa
                last = e
        raise last

    done = uploaded = 0
    failed = []
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(upload, t): t for t in todo}
        for fut in cf.as_completed(futs):
            t = futs[fut]
            done += 1
            try:
                fut.result()
                uploaded += 1
            except Exception as e:  # noqa
                failed.append((t[1], str(e)))
            if done % 25 == 0 or done == len(todo):
                print(f"  [{done}/{len(todo)}] uploaded={uploaded} failed={len(failed)}",
                      flush=True)

    print(f"\nDONE. uploaded={uploaded}, skipped={skipped}, failed={len(failed)}")
    if failed:
        print("FAILURES (first 20) — re-run to retry just these:")
        for name, err in failed[:20]:
            print(f"  {name}: {err}")
        return 1
    print(f"\nAll files present under gs://{BUCKET}/{DEST_PREFIX}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
