"""Mirror local UCRA input data (Pakistan/data/*) into
gs://city-scan-global-data/ucra-data/.

Uses google-cloud-storage with Application Default Credentials (the azizlums
identity), which has confirmed write access to this shared bucket.

Resumable: a file is skipped if a blob of the same size already exists at the
destination, so re-running after an interruption only uploads what's missing.
Large rasters use 8 MiB resumable chunks, a long per-request timeout, and a few
retries to ride out transient write timeouts.
"""
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
DEST_PREFIX = "ucra-data"

# Same resolution as the ucra task: menu.yml -> $CITYSCAN_UCRA_DIR ->
# <repo parent>/ucra-data. Pass a path as argv[1] to override for a one-off.
if len(sys.argv) > 1:
    DATA_ROOT = str(Path(sys.argv[1]).expanduser().resolve() / "data")
else:
    DATA_ROOT = str(external_dir({}, "ucra_project_dir",
                                 "CITYSCAN_UCRA_DIR", "ucra-data") / "data")

if not os.path.isdir(DATA_ROOT):
    sys.exit(f"UCRA data tree not found: {DATA_ROOT}\n"
             "Set CITYSCAN_UCRA_DIR, or pass the project dir as an argument.")
print(f"Source: {DATA_ROOT}")

client = storage.Client()
bucket = client.bucket(BUCKET)

print(f"Listing existing objects under {DEST_PREFIX}/ ...", flush=True)
existing = {}
for b in client.list_blobs(bucket, prefix=f"{DEST_PREFIX}/"):
    existing[b.name] = b.size
print(f"  found {len(existing)} existing objects\n", flush=True)

# Build the full work list: every file under Pakistan/data mirrored to
# ucra-data/<relative path>, preserving subfolders.
tasks = []  # (local_path, blob_name, size)
for root, _dirs, files in os.walk(DATA_ROOT):
    for fn in files:
        lp = os.path.join(root, fn)
        rel = os.path.relpath(lp, DATA_ROOT).replace("\\", "/")
        blob_name = f"{DEST_PREFIX}/{rel}"
        tasks.append((lp, blob_name, os.path.getsize(lp)))

total = len(tasks)
to_upload = [t for t in tasks if existing.get(t[1]) != t[2]]
skipped = total - len(to_upload)
total_bytes = sum(t[2] for t in to_upload)
print(f"Total files: {total} | already present: {skipped} | "
      f"to upload: {len(to_upload)} ({total_bytes/1e9:.1f} GB)\n", flush=True)

done = 0
uploaded = 0
failed = []


def _upload(t):
    lp, blob_name, _size = t
    last = None
    for _attempt in range(4):
        try:
            blob = bucket.blob(blob_name, chunk_size=8 * 1024 * 1024)
            blob.upload_from_filename(lp, timeout=900)
            return blob_name
        except Exception as e:  # noqa
            last = e
    raise last


with cf.ThreadPoolExecutor(max_workers=8) as ex:
    futs = {ex.submit(_upload, t): t for t in to_upload}
    for fut in cf.as_completed(futs):
        t = futs[fut]
        done += 1
        try:
            fut.result()
            uploaded += 1
        except Exception as e:  # noqa
            failed.append((t[1], str(e)))
        if done % 50 == 0 or done == len(to_upload):
            print(f"  [{done}/{len(to_upload)}] uploaded={uploaded} "
                  f"failed={len(failed)}", flush=True)

print(f"\nDONE. uploaded={uploaded}, skipped(existing)={skipped}, "
      f"failed={len(failed)}", flush=True)
if failed:
    print("FAILURES (first 20):", flush=True)
    for name, err in failed[:20]:
        print(f"  {name}: {err}", flush=True)
    sys.exit(1)
print(f"\nAll files present under gs://{BUCKET}/{DEST_PREFIX}/", flush=True)
