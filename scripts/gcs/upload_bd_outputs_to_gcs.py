"""Upload Bangladesh UCRA outputs (per-cluster folders + plots + SLR/stats) to
gs://crp-city-scan/Ucra-Bangladesh-clusters/, preserving folder structure.

Excludes data/ (junctions to the 56 GB Pakistan global inputs) and the
shapefiles*/ input folders. ADC (azizlums) auth; resumable (skip by name+size);
chunked + retried for the larger rasters.
"""
import os
import sys
import concurrent.futures as cf
from google.cloud import storage

BUCKET = "crp-city-scan"
DEST_PREFIX = "Ucra-Bangladesh-clusters"
HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
BD = os.path.join(PROJECT_ROOT, "Bangladesh")

# Output folders only (per-cluster results, plots, SLR mosaics, stats).
SRC_DIRS = [f"Cluster {i}" for i in range(1, 8)] + ["plots", "output", "stats"]

client = storage.Client()
bucket = client.bucket(BUCKET)

print(f"Listing existing objects under {DEST_PREFIX}/ ...", flush=True)
existing = {}
for b in client.list_blobs(bucket, prefix=f"{DEST_PREFIX}/"):
    existing[b.name] = b.size
print(f"  found {len(existing)} existing objects\n", flush=True)

tasks = []  # (local_path, blob_name, size)
for sub in SRC_DIRS:
    root_dir = os.path.join(BD, sub)
    if not os.path.isdir(root_dir):
        continue
    for root, _dirs, files in os.walk(root_dir):
        for fn in files:
            lp = os.path.join(root, fn)
            rel = os.path.relpath(lp, BD).replace("\\", "/")
            tasks.append((lp, f"{DEST_PREFIX}/{rel}", os.path.getsize(lp)))

total = len(tasks)
to_upload = [t for t in tasks if existing.get(t[1]) != t[2]]
skipped = total - len(to_upload)
total_bytes = sum(t[2] for t in to_upload)
print(f"Total files: {total} | already present: {skipped} | "
      f"to upload: {len(to_upload)} ({total_bytes/1e6:.0f} MB)\n", flush=True)

done = 0
uploaded = 0
failed = []


def _upload(t):
    lp, blob_name, _size = t
    last = None
    for _attempt in range(4):
        try:
            blob = bucket.blob(blob_name, chunk_size=8 * 1024 * 1024)
            blob.upload_from_filename(lp, timeout=600)
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
print(f"\nAll Bangladesh outputs present under gs://{BUCKET}/{DEST_PREFIX}/", flush=True)
