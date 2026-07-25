"""Mirror local City Scan mnt/ folders (+ UCRA plots) into gs://crp-city-scan/2026-06-pakistan/.

Uses google-cloud-storage with Application Default Credentials (the azizlums
identity that the `scan --upload` step authenticates with), NOT the gcloud CLI
account — so it has the same write access that already succeeded on this bucket.

Resumable: a file is skipped if a blob of the same size already exists at the
destination, so re-running after an interruption only uploads what's missing.
"""
import os
import sys
import concurrent.futures as cf
from google.cloud import storage

BUCKET = "crp-city-scan"
HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)  # ...\UCRA and City Scan Ultra

# (local_root, dest_prefix) — every file under local_root is mirrored under
# BUCKET/dest_prefix/<relative path>, preserving subfolders.
MNT = os.path.join(HERE, "mnt")
PAKISTAN_PLOTS = os.path.join(PROJECT_ROOT, "Pakistan", "plots")

JOBS = []
# the 13 city folders in mnt (folders only; skip stray top-level files like README.md)
for name in sorted(os.listdir(MNT)):
    p = os.path.join(MNT, name)
    if os.path.isdir(p):
        JOBS.append((p, f"2026-06-pakistan/{name}"))
# UCRA national plots
if os.path.isdir(PAKISTAN_PLOTS):
    JOBS.append((PAKISTAN_PLOTS, "2026-06-pakistan/ucra-plots"))

client = storage.Client()
bucket = client.bucket(BUCKET)

# Pre-list existing blobs under the destination prefix once (name -> size) so we
# can skip what's already uploaded without an API call per file.
print("Listing existing objects under 2026-06-pakistan/ ...", flush=True)
existing = {}
for b in client.list_blobs(bucket, prefix="2026-06-pakistan/"):
    existing[b.name] = b.size
print(f"  found {len(existing)} existing objects\n", flush=True)

# Build the full work list
tasks = []  # (local_path, blob_name, size)
for local_root, dest_prefix in JOBS:
    for root, _dirs, files in os.walk(local_root):
        for fn in files:
            lp = os.path.join(root, fn)
            rel = os.path.relpath(lp, local_root).replace("\\", "/")
            blob_name = f"{dest_prefix}/{rel}"
            tasks.append((lp, blob_name, os.path.getsize(lp)))

total = len(tasks)
to_upload = [t for t in tasks if existing.get(t[1]) != t[2]]
skipped = total - len(to_upload)
print(f"Total files: {total} | already present: {skipped} | to upload: {len(to_upload)}\n", flush=True)

done = 0
uploaded = 0
failed = []
lock_done = 0


def _upload(t):
    lp, blob_name, _size = t
    # 8 MiB chunks => resumable upload for large rasters; long per-request timeout
    # and a few retries to ride out transient write timeouts on a slow uplink.
    last = None
    for attempt in range(4):
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
        if done % 100 == 0 or done == len(to_upload):
            print(f"  [{done}/{len(to_upload)}] uploaded={uploaded} failed={len(failed)}", flush=True)

print(f"\nDONE. uploaded={uploaded}, skipped(existing)={skipped}, failed={len(failed)}", flush=True)
if failed:
    print("FAILURES (first 20):", flush=True)
    for name, err in failed[:20]:
        print(f"  {name}: {err}", flush=True)
    sys.exit(1)
print(f"\nAll files present under gs://{BUCKET}/2026-06-pakistan/", flush=True)
