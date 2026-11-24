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