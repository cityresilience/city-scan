import subprocess
import time
from pathlib import Path
from google.cloud import storage
from tqdm import tqdm

# -------------------------
# CONFIG
# -------------------------

BUCKET = "city-scan-global-public"
PREFIX = "globfire/"      # folder inside bucket
OUTPUT_DIR = Path("/Users/danielcp/local_drive/01_CRP/city-scan-automation/outputs/globfire_fgb")  # change this

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# -------------------------
# LIST FILES IN BUCKET
# -------------------------

client = storage.Client.create_anonymous_client()
bucket = client.bucket(BUCKET)

blobs = list(client.list_blobs(bucket, prefix=PREFIX))

shp_files = sorted([
    blob.name for blob in blobs if blob.name.endswith(".shp")
])

print(f"Found {len(shp_files)} shapefiles in bucket")

# -------------------------
# CONVERSION LOOP
# -------------------------

start_total = time.perf_counter()

for shp in tqdm(shp_files, desc="Converting"):

    name = Path(shp).stem
    out = OUTPUT_DIR / f"{name}.fgb"

    if out.exists():
        continue

    remote_path = f"/vsicurl/https://storage.googleapis.com/{BUCKET}/{shp}"

    t0 = time.perf_counter()

    cmd = [
        "ogr2ogr",
        "-f", "FlatGeobuf",
        str(out),
        remote_path,
        "-nlt", "PROMOTE_TO_MULTI",
        "-makevalid",
        "-skipfailures",
        "-progress"
    ]

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError:
        print(f"\n❌ Failed: {shp}")
        continue

    t1 = time.perf_counter()

    print(f"\n✔ {name} | {t1 - t0:.1f}s")

elapsed = time.perf_counter() - start_total

print(f"\nTOTAL TIME: {elapsed/60:.1f} minutes")
