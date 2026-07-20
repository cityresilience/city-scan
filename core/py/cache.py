"""Shared cache utilities for scan commands and task data downloads."""
from pathlib import Path
import os
import time
import re
import shutil
import rasterio

from core.config.paths import OUTPUTS
from core.py.log_module import setup_logger

logger = setup_logger(__name__)


DEFAULT_NAMESPACES = ("worldpop", "demographics", "osm-pbf")
_TARGET_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def get_cache_root() -> Path:
    """Resolve cache root directory.

    Priority:
      1) CITY_SCAN_CACHE_DIR env var
      2) <OUTPUTS>/.cache (shared across city scans)
    """
    override = os.environ.get("CITY_SCAN_CACHE_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return Path(OUTPUTS) / ".cache"


def get_cache_namespace_dir(namespace: str) -> Path:
    """Return namespace path under cache root."""
    namespace = (namespace or "").strip().lower()
    if not _TARGET_RE.match(namespace):
        raise ValueError(f"Invalid cache namespace: '{namespace}'")
    return get_cache_root() / namespace


def is_valid_cached_raster(path):
    """Quick validity check so truncated files are never reused."""
    if not path.exists() or path.stat().st_size <= 0:
        return False
    try:
        with rasterio.open(path) as src:
            return src.width > 0 and src.height > 0 and src.count > 0
    except Exception:
        return False


def acquire_lock(lock_path, timeout_s=600, poll_s=0.25):
    """Acquire file lock via exclusive create. Returns fd or None on timeout."""
    start = time.time()
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode("ascii", errors="ignore"))
            return fd
        except FileExistsError:
            try:
                age = time.time() - lock_path.stat().st_mtime
                if age > timeout_s:
                    lock_path.unlink(missing_ok=True)
                    continue
            except FileNotFoundError:
                continue
            if time.time() - start > timeout_s:
                return None
            time.sleep(poll_s)


def read_bytes_with_cache(url, cache_path, log_prefix):
    """Download bytes from URL to shared cache or return cached bytes with cross-process locking.
    
    Parameters
    ----------
    url : str
        Remote URL to download from
    cache_path : Path
        Local cache file path
    log_prefix : str
        Prefix for log messages (e.g. "WorldPop", "Demographics")
    
    Returns
    -------
    bytes
        File contents from cache or freshly downloaded
    """
    import urllib.request
    
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    if is_valid_cached_raster(cache_path):
        logger.info(f"  {log_prefix} cache hit: {cache_path.name}")
        return cache_path.read_bytes()

    if cache_path.exists():
        logger.warning(f"  {log_prefix} cache invalid, redownloading: {cache_path.name}")
        cache_path.unlink(missing_ok=True)

    lock_path = cache_path.with_suffix(cache_path.suffix + ".lock")
    lock_fd = acquire_lock(lock_path)
    if lock_fd is None:
        raise TimeoutError(f"Timeout waiting for cache lock: {lock_path}")

    tmp_path = None
    try:
        # Re-check after lock in case another process populated cache.
        if is_valid_cached_raster(cache_path):
            logger.info(f"  {log_prefix} cache hit: {cache_path.name}")
            return cache_path.read_bytes()

        logger.info(f"  {log_prefix} cache miss, downloading: {cache_path.name}")
        with urllib.request.urlopen(url) as response:
            raw = response.read()

        tmp_path = cache_path.with_suffix(cache_path.suffix + f".part.{os.getpid()}")
        with open(tmp_path, "wb") as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())

        os.replace(tmp_path, cache_path)
        if not is_valid_cached_raster(cache_path):
            cache_path.unlink(missing_ok=True)
            raise RuntimeError(f"Downloaded file failed validation: {cache_path.name}")

        logger.info(f"  {log_prefix} cache write: {cache_path} ({len(raw) / 1e6:.1f} MB)")
        return raw
    finally:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        os.close(lock_fd)
        lock_path.unlink(missing_ok=True)


def _split_targets(raw: str):
    out = []
    for part in (raw or "").split(","):
        t = part.strip().lower()
        if t:
            out.append(t)
    return out


def parse_cache_targets(args):
    """Parse --cache-targets from CLI args."""
    targets = []
    for i, a in enumerate(args):
        if a.startswith("--cache-targets="):
            targets.extend(_split_targets(a.split("=", 1)[1]))
        elif a == "--cache-targets" and i + 1 < len(args) and not args[i + 1].startswith("-"):
            targets.extend(_split_targets(args[i + 1]))
    return targets


def resolve_cache_targets(requested=None):
    """Resolve requested targets; defaults to all known + discovered namespaces."""
    root = get_cache_root()

    if requested:
        targets = []
        for t in requested:
            t = t.strip().lower()
            if t == "all":
                requested = []
                break
            if not _TARGET_RE.match(t):
                raise ValueError(f"Invalid cache target '{t}'. Use letters, digits, '-' or '_' only.")
            targets.append(t)
        if targets:
            return sorted(set(targets))

    discovered = []
    if root.exists():
        discovered = [p.name for p in root.iterdir() if p.is_dir()]
    return sorted(set(DEFAULT_NAMESPACES) | set(discovered))


def _dir_stats(path: Path):
    files = 0
    size = 0
    if not path.exists():
        return files, size
    for p in path.rglob("*"):
        if p.is_file():
            files += 1
            size += p.stat().st_size
    return files, size


def _fmt_bytes(num_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    n = float(num_bytes)
    for unit in units:
        if n < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(n)} {unit}"
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{num_bytes} B"


def print_cache_listing(targets=None):
    """Print cache root and per-namespace summary."""
    root = get_cache_root()
    resolved = resolve_cache_targets(targets)

    print("\n  Cache")
    print("  " + "-" * 60)
    print(f"  Root: {root}")

    total_files = 0
    total_size = 0
    if not resolved:
        print("  No cache namespaces found.")
        print()
        return

    print(f"  {'Namespace':<20} {'Files':>8} {'Size':>12} {'Status':>12}")
    print("  " + "-" * 60)
    for ns in resolved:
        ns_dir = get_cache_namespace_dir(ns)
        files, size = _dir_stats(ns_dir)
        total_files += files
        total_size += size
        status = "present" if ns_dir.exists() else "missing"
        print(f"  {ns:<20} {files:>8} {_fmt_bytes(size):>12} {status:>12}")

    print("  " + "-" * 60)
    print(f"  {'TOTAL':<20} {total_files:>8} {_fmt_bytes(total_size):>12}")
    print()


def purge_cache(targets=None, execute=False):
    """Purge selected cache namespaces.

    If execute=False, perform a dry-run preview only.
    """
    resolved = resolve_cache_targets(targets)

    print("\n  Cache Purge")
    print("  " + "-" * 60)
    print(f"  Root: {get_cache_root()}")

    removed = 0
    skipped = 0
    bytes_removed = 0
    for ns in resolved:
        ns_dir = get_cache_namespace_dir(ns)
        files, size = _dir_stats(ns_dir)
        if not ns_dir.exists():
            print(f"  {ns:<20} missing")
            skipped += 1
            continue
        if execute:
            shutil.rmtree(ns_dir)
            print(f"  {ns:<20} removed ({files} files, {_fmt_bytes(size)})")
            removed += 1
            bytes_removed += size
        else:
            print(f"  {ns:<20} would remove ({files} files, {_fmt_bytes(size)})")

    print("  " + "-" * 60)
    if execute:
        print(f"  Removed namespaces: {removed}")
        print(f"  Skipped namespaces: {skipped}")
        print(f"  Approx bytes removed: {_fmt_bytes(bytes_removed)}")
    else:
        print("  Dry run only. Re-run with --yes to actually purge.")
    print()


def run_cache_command(args):
    """Dispatch cache commands from CLI. Returns process exit code."""
    do_ls = "--cache-ls" in args
    do_purge = "--cache-purge" in args
    if not do_ls and not do_purge:
        return 0
    if do_ls and do_purge:
        print("  Use either --cache-ls or --cache-purge, not both.")
        return 2

    targets = parse_cache_targets(args)
    if do_ls:
        print_cache_listing(targets=targets)
        return 0

    execute = "--yes" in args
    purge_cache(targets=targets, execute=execute)
    if not execute:
        print("  Add --yes to confirm purge.")
    return 0
