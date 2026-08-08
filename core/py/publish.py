"""--publish: copy a scan's rendered _site into the delivery repo (GitHub Pages).

Mirrors the manual flow: clone the delivery repo, drop the city's _site into a
subfolder, add a redirect index.html + .nojekyll, commit and push.

  scan --publish <folder> --scan-id <id>   -> <folder>/<city_name>/   (e.g. uzbekistan-atlas/chust/)
  scan --publish --scan-id <id>            -> <country-city>/         (scan-id minus the date prefix)

Does NOT render — run `quarto render` in the city folder first so _site is current.
"""
import os
import re
import shutil
import tempfile
import subprocess

from core.py.log_module import setup_logger

logger = setup_logger(__name__)

DELIVERY_REPO = "cityresilience/delivery"
REDIRECT = '<!doctype html><meta http-equiv="refresh" content="0; url=publish/">\n'


def run_publish(scan, folder=None):
    """Publish scan's _site into the delivery repo under folder/city (or country-city)."""

    city_root = os.path.dirname(str(scan.input_dir))        # OUTPUTS/<cityscan_id>
    site = os.path.join(city_root, "_site")
    if not os.path.isdir(site):
        logger.error(f"No _site at {site} — render first: `quarto render` in the city folder.")
        return

    # Destination path inside the delivery repo.
    if folder:
        subpath = f"{folder}/{scan.city_name}"
    else:
        subpath = re.sub(r"^\d{4}-\d{2}-", "", scan.cityscan_id)   # country-city
    logger.info(f"Publishing {scan.cityscan_id} -> {DELIVERY_REPO}:{subpath}/")

    tmp = tempfile.mkdtemp(prefix="publish-")
    try:
        repo = os.path.join(tmp, "repo")
        subprocess.run(["gh", "repo", "clone", DELIVERY_REPO, repo], check=True)

        dest = os.path.join(repo, subpath)
        shutil.rmtree(dest, ignore_errors=True)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copytree(site, dest)

        # /<subpath>/ -> /<subpath>/publish/ ; keep Pages from running Jekyll
        with open(os.path.join(dest, "index.html"), "w") as f:
            f.write(REDIRECT)
        open(os.path.join(repo, ".nojekyll"), "a").close()

        subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
        # Commit as whoever runs this — uses their own git config (name/email).
        commit = subprocess.run(["git", "-C", repo, "commit", "-m", f"Publish {subpath}"])
        if commit.returncode != 0:
            logger.info("Nothing to commit (no changes, or git identity not configured — "
                        "set `git config --global user.name/user.email`).")
            return
        subprocess.run(["git", "-C", repo, "push"], check=True)
        logger.info(f"Published -> https://cityresilience.github.io/delivery/{subpath}/publish/")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
