"""Materialise global input data from GCS into a local folder before a run.

WHY THIS EXISTS RATHER THAN /vsigs/ STREAMING
---------------------------------------------
City Scan's own R code never downloads global data — `core/R/gcs-overrides.R`
monkeypatches `rast`, `vect`, `read_sf` and `read_csv` so `resolve()` can hand
back `/vsigs/<bucket>/<key>` and GDAL streams the bytes it needs. That works
because the readers being patched are City Scan's own.

UCRA and FCS are separate repos, launched via `conda run` in their own conda
envs, doing plain `os.path.exists()` / `rasterio.open()` / `pd.read_csv()` on
absolute local paths. There is no reader to patch from here, so the honest
mechanism is to make the files exist before the pipeline starts — the same thing
City Scan already does for scan folders in `gcs_module.download_scan_folder()`.

The sync is content-addressed by (relative path, size) and therefore idempotent:
running it twice is a cheap listing, and an interrupted download resumes.
"""
import concurrent.futures as cf
import os
from pathlib import Path

from core.py.log_module import setup_logger

logger = setup_logger(__name__)

CHUNK = 8 * 1024 * 1024
TIMEOUT = 900
RETRIES = 4


def sync(bucket_name, prefix, dest, include=(), workers=8, dry_run=False):
    """Mirror gs://<bucket_name>/<prefix>/ into `dest`.

    include : subfolder names under the prefix to restrict to. Empty means
              everything. This is how the FCS task pulls only the folders its
              *enabled* layers need instead of the whole 121 GB.
    Returns  (downloaded, skipped, bytes_downloaded).
    """
    from google.cloud import storage

    dest = Path(dest)
    prefix = prefix.strip("/")
    client = storage.Client()

    wanted = [f"{prefix}/{i.strip('/')}/" for i in include] if include else [f"{prefix}/"]

    blobs = []
    for w in wanted:
        for b in client.list_blobs(bucket_name, prefix=w):
            if not b.name.endswith("/"):
                blobs.append(b)
    if not blobs:
        logger.warning(f"  no objects under gs://{bucket_name}/{prefix}/ "
                       f"{'for ' + ', '.join(include) if include else ''}")
        return 0, 0, 0

    todo = []
    skipped = 0
    for b in blobs:
        rel = b.name[len(prefix) + 1:]
        local = dest / rel
        if local.exists() and local.stat().st_size == b.size:
            skipped += 1
            continue
        todo.append((b, local))
    todo.sort(key=lambda t: t[0].size or 0)     # smallest first

    nbytes = sum((b.size or 0) for b, _ in todo)
    logger.info(f"  gs://{bucket_name}/{prefix}/ -> {dest}: "
                f"{len(blobs):,} objects | {skipped:,} already local | "
                f"{len(todo):,} to fetch ({nbytes/1e9:.2f} GB)")
    if dry_run or not todo:
        return 0, skipped, 0

    def fetch(item):
        blob, local = item
        local.parent.mkdir(parents=True, exist_ok=True)
        # Download to a sidecar first: a killed run must never leave a
        # half-written file that the size check would then accept as complete.
        tmp = local.with_suffix(local.suffix + ".part")
        last = None
        for _ in range(RETRIES):
            try:
                blob.chunk_size = CHUNK
                blob.download_to_filename(str(tmp), timeout=TIMEOUT)
                os.replace(tmp, local)
                return blob.size or 0
            except Exception as e:  # noqa
                last = e
        tmp.unlink(missing_ok=True)
        raise last

    done = downloaded = got = 0
    failed = []
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(fetch, t): t for t in todo}
        for fut in cf.as_completed(futs):
            done += 1
            try:
                got += fut.result()
                downloaded += 1
            except Exception as e:  # noqa
                failed.append((futs[fut][0].name, str(e)))
            if done % 25 == 0 or done == len(todo):
                logger.info(f"    [{done}/{len(todo)}] ok={downloaded} failed={len(failed)}")

    if failed:
        logger.warning(f"  {len(failed)} download(s) failed; re-run to retry just these")
        for name, err in failed[:5]:
            logger.warning(f"    {name}: {err}")
    return downloaded, skipped, got
