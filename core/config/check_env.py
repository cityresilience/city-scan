"""Environment preflight: verify R, Python, GEE, GCS, Quarto, and input files.

Invoked via `python -m tasks --check [targets...]`. Run all targets by default,
or a subset like `--check r gee`. Reports per-check ✓/✗, prints actionable fix
commands for failures, and offers interactive prompts for auto-installable
issues (R packages). Non-interactive fixes (auth, gcloud login) print the
command without prompting — the user runs it themselves.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path


OK = "\033[32m✓\033[0m"
FAIL = "\033[31m✗\033[0m"
WARN = "\033[33m!\033[0m"


def _prompt_yes(question):
    """Interactive y/N prompt. Non-tty = no (safe default)."""
    if not sys.stdin.isatty():
        return False
    try:
        ans = input(f"  {question} [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return ans in ("y", "yes")


def _print_header(name):
    print(f"\n{name}")


def _print_check(icon, message, hint=None):
    print(f"  {icon} {message}")
    if hint:
        print(f"      {hint}")


# ---------- R ----------
def check_r():
    _print_header("R environment")
    rscript = shutil.which("Rscript")
    if not rscript:
        _print_check(FAIL, "Rscript not on PATH",
                     "Install R from https://cloud.r-project.org/")
        return False

    version = subprocess.run(
        [rscript, "--version"], capture_output=True, text=True
    ).stderr.strip() or subprocess.run(
        [rscript, "--version"], capture_output=True, text=True
    ).stdout.strip()
    _print_check(OK, f"Rscript: {version}")

    # Check `here` and `librarian` — the two packages setup.R needs before
    # `librarian::shelf()` can install everything else.
    required = ["here", "librarian"]
    missing = []
    for pkg in required:
        r = subprocess.run(
            [rscript, "-e", f"cat(requireNamespace('{pkg}', quietly=TRUE))"],
            capture_output=True, text=True,
        )
        if "TRUE" in r.stdout:
            _print_check(OK, f"R package '{pkg}'")
        else:
            _print_check(FAIL, f"R package '{pkg}' missing")
            missing.append(pkg)

    if missing and _prompt_yes(f"Install {', '.join(missing)} via install.packages()?"):
        for pkg in missing:
            print(f"  Installing {pkg}...")
            r = subprocess.run(
                [rscript, "-e",
                 f"install.packages('{pkg}', repos='https://cloud.r-project.org')"],
            )
            if r.returncode == 0:
                _print_check(OK, f"{pkg} installed")
            else:
                _print_check(FAIL, f"{pkg} install failed")
                return False
        missing = []

    if missing:
        print(f"      Run in R: install.packages(c({', '.join(repr(p) for p in missing)}))")
        return False

    # Librarian handles the rest via setup.R — we don't probe the full list
    # here because a dry-run of librarian::shelf() would actually install.
    _print_check(OK, "setup.R will resolve remaining packages via librarian::shelf")
    return True


# ---------- Python ----------
def check_python():
    _print_header("Python environment")
    ok = True
    _print_check(OK, f"Python {sys.version.split()[0]}")
    required = [
        "geopandas", "rasterio", "numpy", "pandas", "yaml",
        "ee", "google.cloud.storage", "shapely", "pyproj",
    ]
    for mod in required:
        try:
            __import__(mod)
            _print_check(OK, f"{mod}")
        except ImportError:
            _print_check(FAIL, f"{mod} not importable")
            ok = False
    if not ok:
        print("      Fix: pip install -r requirements.txt")
    return ok


# ---------- GEE ----------
GEE_LOGIN_CMD = (
    "gcloud auth application-default login "
    "--scopes=openid,https://www.googleapis.com/auth/userinfo.email,"
    "https://www.googleapis.com/auth/cloud-platform,"
    "https://www.googleapis.com/auth/earthengine"
)


def check_gee():
    _print_header("Google Earth Engine")
    try:
        import ee
        import google.auth
    except ImportError as e:
        _print_check(FAIL, f"{e.name} not importable")
        return False

    _GEE_SCOPES = [
        "https://www.googleapis.com/auth/earthengine",
        "https://www.googleapis.com/auth/cloud-platform",
    ]

    def _try_init():
        creds, detected_project = google.auth.default(scopes=_GEE_SCOPES)
        project = os.environ.get("GEE_PROJECT", detected_project)
        ee.Initialize(credentials=creds, project=project)
        return project

    try:
        project = _try_init()
        _print_check(OK, f"authenticated (project={project})")
        return True
    except Exception as e:
        msg = str(e).splitlines()[0] if str(e) else type(e).__name__
        _print_check(FAIL, f"ee.Initialize() failed: {msg}")
        print(f"      Fix: create ADC with the earthengine scope")
        print(f"      {GEE_LOGIN_CMD}")
        if _prompt_yes("Run it now?"):
            result = subprocess.run(GEE_LOGIN_CMD, shell=True)
            if result.returncode == 0:
                try:
                    project = _try_init()
                    _print_check(OK, f"authenticated after interactive login (project={project})")
                    return True
                except Exception as e2:
                    _print_check(FAIL, f"still failing: {e2}")
        return False


# ---------- GCS ----------
def check_gcs():
    _print_header("Google Cloud Storage")
    try:
        from google.auth import default
    except ImportError:
        _print_check(FAIL, "google-auth not installed",
                     "pip install google-auth google-cloud-storage")
        return False
    try:
        creds, project = default()
        who = getattr(creds, 'service_account_email', None) or "application default credentials"
        _print_check(OK, f"credentials found ({who}, project={project})")
        return True
    except Exception as e:
        msg = str(e).splitlines()[0]
        _print_check(FAIL, f"no credentials: {msg}",
                     "Run: gcloud auth application-default login")
        return False


# ---------- Quarto ----------
def check_quarto():
    _print_header("Quarto")
    quarto = shutil.which("quarto")
    if not quarto:
        _print_check(FAIL, "quarto not on PATH",
                     "Install from https://quarto.org/docs/get-started/")
        return False
    r = subprocess.run([quarto, "--version"], capture_output=True, text=True)
    _print_check(OK, f"quarto {r.stdout.strip()}")
    return True


# ---------- Inputs ----------
def check_inputs():
    _print_header("Input files")
    root = Path(__file__).parent.parent.parent
    inputs_dir = root / "inputs"
    ok = True
    for name in ["menu.yml", "city_inputs.yml"]:
        path = inputs_dir / name
        if path.exists():
            _print_check(OK, f"inputs/{name}")
        else:
            _print_check(FAIL, f"inputs/{name} missing")
            ok = False
    aoi_dir = inputs_dir / "AOI"
    if aoi_dir.exists():
        subdirs = [d for d in aoi_dir.iterdir() if d.is_dir()]
        _print_check(OK, f"inputs/AOI ({len(subdirs)} subfolders)")
    else:
        _print_check(WARN, "inputs/AOI missing (ok if not using multicity)")
    return ok


CHECKS = {
    "r": check_r,
    "python": check_python,
    "gee": check_gee,
    "gcs": check_gcs,
    "quarto": check_quarto,
    "inputs": check_inputs,
}


def run_checks(targets):
    """Run the selected checks. Returns True iff all passed."""
    print(f"\n  Environment check: {', '.join(targets)}")
    print(f"  {'─' * 40}")
    results = {}
    for t in targets:
        results[t] = CHECKS[t]()
    failed = [t for t, ok in results.items() if not ok]
    print()
    if failed:
        print(f"  {FAIL} Failed: {', '.join(failed)}")
        return False
    print(f"  {OK} All checks passed")
    return True
