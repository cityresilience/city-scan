import os
from pathlib import Path

_city_root = Path(__file__).resolve().parents[2]  # core/config -> core -> city folder

if (_city_root / "01-user-input").exists() and not (_city_root / "inputs").exists():
    # Running from within a city folder (has 01-user-input but no inputs/)
    PROJECT_ROOT = _city_root
    INPUTS = _city_root / "01-user-input"
    OUTPUTS = _city_root.parent  # mnt/ level
else:
    # Running from repo root
    PROJECT_ROOT = _city_root
    INPUTS = _city_root / "inputs"
    OUTPUTS = _city_root / "mnt"


# ---------------------------------------------------------------------------
# External data roots (FCS / UCRA)
# ---------------------------------------------------------------------------
# The FCS and UCRA *code* is vendored into tasks/, but their bulk input data is
# tens to hundreds of GB and cannot live in the repo. Those trees therefore sit
# outside it, and where they sit differs per machine — which is exactly what
# used to be hardcoded as `D:/Aziz/GFDRR/CRP/FCS/` and broke for everyone else.
#
# Resolution order, first hit wins:
#   1. the value in inputs/menu.yml            (explicit, per-project)
#   2. the environment variable                (per-machine, no file edits)
#   3. <repo parent>/<default_name>            (works if the trees sit beside
#                                               the checkout, the common layout)
#
# Values may use ~ and $VARS. Nothing is created or validated here — the caller
# reports a missing tree with the context to fix it.

def external_dir(menu, key, env_var, default_name):
    """Resolve an external data root. Returns a Path (may not exist)."""
    value = ""
    if menu:
        value = str(menu.get(key) or "").strip()
    if not value:
        value = os.environ.get(env_var, "").strip()
    if not value:
        return (PROJECT_ROOT.parent / default_name).resolve()
    return Path(os.path.expandvars(os.path.expanduser(value))).resolve()


def describe_external(key, env_var, default_name):
    """One-line hint naming every way to point a missing tree somewhere real."""
    return (f"Set `{key}` in inputs/menu.yml, or the {env_var} environment "
            f"variable, or place the tree at <repo parent>/{default_name}.")
