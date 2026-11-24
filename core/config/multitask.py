# Parallel task runner with inline TUI
# Usage: called from __main__.py when --parallel flag is set

import threading
import time
import logging
import io
import sys
import os
import tty
import termios
import select
from concurrent.futures import ThreadPoolExecutor


# Resource concurrency limits
RESOURCE_LIMITS = {
    "gee": 1,
    "gcs": 2,
    "osm": 1,
    "default": 3,
}

# Task dependencies — sourced from source/tasks.yml (single source of truth)
from core.config.tasks import TASK_DEPENDENCIES

TASK_RESOURCES = {
    "forest": "gee",
    "landcover": "gee",
    "lst": "gee",
    "green": "gee",
    "ndmi": "gee",
    "nightlight": "gee",
    "wsf": "gcs",
    "fathom": "gcs",
    "burnability": "gcs",
    "elevation": "gcs",
    "accessibility": "osm",
    "buildings": "osm",
}

# ANSI helpers
CSI = "\033["
CLEAR_LINE = f"{CSI}2K"
HIDE_CURSOR = f"{CSI}?25l"
SHOW_CURSOR = f"{CSI}?25h"
BOLD = f"{CSI}1m"
DIM = f"{CSI}2m"
RESET = f"{CSI}0m"
RED = f"{CSI}31m"
GREEN = f"{CSI}32m"
YELLOW = f"{CSI}33m"
BLUE = f"{CSI}34m"
CYAN = f"{CSI}36m"
WHITE = f"{CSI}37m"
BG_BLUE = f"{CSI}44m"
BG_WHITE = f"{CSI}47m"
BLACK = f"{CSI}30m"
REVERSE = f"{CSI}7m"


class TaskState:
    WAITING = "waiting"
    RUNNING = "running"
    OK = "ok"
    ERROR = "error"
    SKIPPED = "skipped"

    def __init__(self, name, resource_type="default"):
        self.name = name
        self.resource_type = resource_type
        self.status = self.WAITING
        self.phase = ""
        self.last_log = ""
        self.start_time = None
        self.elapsed = 0
        self.error_count = 0
        self.logs = []


class TaskLogHandler(logging.Handler):
    def __init__(self, task_states):
        super().__init__()
        self.task_states = task_states

    def emit(self, record):
        msg = self.format(record)

        # Split multi-line messages into separate log entries
        lines = [line for line in msg.split('\n') if line.strip()]
        if not lines:
            lines = [msg]

        # Route by thread name (set by worker) — most reliable
        task_name = getattr(threading.current_thread(), '_task_name', None)
        if task_name and task_name in self.task_states:
            state = self.task_states[task_name]
            for line in lines:
                state.logs.append(line)
            if lines:
                state.last_log = lines[-1][:55]
            if record.levelno >= logging.ERROR:
                state.error_count += 1
            # Detect phase from logger name or __init__.py log messages
            rname = record.name or ""
            if ".collection" in rname:
                state.phase = "collect"
            elif ".analysis" in rname or ".analyze" in rname:
                state.phase = "analyze"
            elif ".visualization" in rname:
                state.phase = "visualize"
            elif f"tasks.{task_name}" == rname:
                # Messages from __init__.py — detect from message text
                ml = msg.lower()
                if "collect" in ml:
                    state.phase = "collect"
                elif "analyz" in ml:
                    state.phase = "analyze"
                elif "visualiz" in ml:
                    state.phase = "visualize"
            return

        # Fallback: match on logger name (e.g. "tasks.fwi.collection")
        for name, state in self.task_states.items():
            if f"tasks.{name}" in record.name:
                for line in lines:
                    state.logs.append(line)
                if lines:
                    state.last_log = lines[-1][:55]
                if record.levelno >= logging.ERROR:
                    state.error_count += 1
                return


def _get_terminal_size():
    try:
        cols, rows = os.get_terminal_size()
        return cols, rows
    except Exception:
        return 80, 24


def _read_key(timeout=0.3):
    """Non-blocking key read. Returns key string or None."""
    fd = sys.stdin.fileno()
    if select.select([fd], [], [], timeout)[0]:
        ch = os.read(fd, 1).decode('utf-8', errors='ignore')
        if ch == '\x1b':
            # Escape sequence
            if select.select([fd], [], [], 0.05)[0]:
                ch2 = os.read(fd, 1).decode('utf-8', errors='ignore')
                if ch2 == '[':
                    if select.select([fd], [], [], 0.05)[0]:
                        ch3 = os.read(fd, 1).decode('utf-8', errors='ignore')
                        if ch3 == 'A': return 'UP'
                        if ch3 == 'B': return 'DOWN'
                        if ch3 == 'C': return 'RIGHT'
                        if ch3 == 'D': return 'LEFT'
                return 'ESC'
            return 'ESC'
        if ch == '\r' or ch == '\n':
            return 'ENTER'
        return ch
    return None


def _elapsed_str(state):
    if not state.start_time:
        return ""
    e = state.elapsed if state.elapsed else time.time() - state.start_time
    if e >= 60:
        return f"{int(e//60)}m{int(e%60):02d}s"
    return f"{e:.0f}s"


def run_parallel(task_names, scan, step=None, run_task_fn=None, skip_tasks=None, auto_exit=False):
    # Force non-interactive matplotlib backend (macOS crashes if GUI is created from background thread)
    import matplotlib
    matplotlib.use('Agg')

    if skip_tasks is None:
        skip_tasks = set()

    out = sys.__stdout__  # always write to real stdout

    # Build task states
    task_states = {}
    for name in task_names:
        if name in skip_tasks:
            state = TaskState(name)
            state.status = TaskState.SKIPPED
            task_states[name] = state
        else:
            resource = TASK_RESOURCES.get(name, "default")
            task_states[name] = TaskState(name, resource)

    # Resource semaphores
    semaphores = {}
    for res, limit in RESOURCE_LIMITS.items():
        semaphores[res] = threading.Semaphore(limit)

    # Mute ALL log handlers, install our capture handler only
    root_logger = logging.getLogger()
    saved_handlers = list(root_logger.handlers)
    saved_level = root_logger.level
    for h in saved_handlers:
        root_logger.removeHandler(h)

    # Mute every existing logger (urllib3, ee, etc.)
    all_loggers = [logging.getLogger(name) for name in logging.Logger.manager.loggerDict]
    saved_logger_state = []
    for lg in all_loggers:
        saved_logger_state.append((lg, list(lg.handlers), lg.propagate))
        for h in list(lg.handlers):
            lg.removeHandler(h)
        lg.propagate = True

    capture = TaskLogHandler(task_states)
    capture.setFormatter(logging.Formatter("%(levelname)s | %(name)s | %(message)s"))
    root_logger.addHandler(capture)
    # Keep the file handler active so logs go to app.log too
    import core.py.log_module as _log_mod
    if _log_mod._file_handler is not None:
        root_logger.addHandler(_log_mod._file_handler)
    root_logger.setLevel(logging.INFO)

    # Also mute any loggers created AFTER this point
    old_getLogger = logging.getLogger
    def patched_getLogger(name=None):
        lg = old_getLogger(name)
        if name:
            for h in list(lg.handlers):
                lg.removeHandler(h)
            lg.propagate = True
        return lg
    logging.getLogger = patched_getLogger

    # Patch setup_logger so newly-imported modules propagate to our handler
    _original_setup_logger = _log_mod.setup_logger
    def _patched_setup_logger(name=None):
        lg = _original_setup_logger(name)
        for h in list(lg.handlers):
            lg.removeHandler(h)
        lg.propagate = True
        return lg
    _log_mod.setup_logger = _patched_setup_logger

    all_results = {}

    # Change to city folder so R here() and subprocesses resolve correctly
    city_dir = str(getattr(scan, 'input_dir', '')).replace('/01-user-input', '')
    if city_dir and os.path.isdir(city_dir):
        os.chdir(city_dir)

    # Patch subprocess.run to capture stdout/stderr from R and other subprocesses
    import subprocess as _subprocess
    _original_subprocess_run = _subprocess.run

    def _capturing_subprocess_run(*args, **kwargs):
        """Wrap subprocess.run to capture output in parallel mode."""
        # Find which task is running in this thread
        current_thread = threading.current_thread()
        task_name = getattr(current_thread, '_task_name', None)

        # Only capture if stdout/stderr not already redirected by caller
        if 'stdout' not in kwargs and 'capture_output' not in kwargs:
            kwargs['stdout'] = _subprocess.PIPE
        if 'stderr' not in kwargs and 'capture_output' not in kwargs:
            kwargs['stderr'] = _subprocess.PIPE

        result = _original_subprocess_run(*args, **kwargs)

        # Route captured output to task logs
        if task_name and task_name in task_states:
            state = task_states[task_name]
            for stream in [result.stdout, result.stderr]:
                if stream:
                    text = stream.decode('utf-8', errors='replace') if isinstance(stream, bytes) else stream
                    for line in text.splitlines():
                        line = line.strip()
                        if line:
                            state.logs.append(line)
                            state.last_log = line[:55]

        return result

    _subprocess.run = _capturing_subprocess_run

    # Events for dependency tracking — each task gets an event that's set when it finishes
    task_done_events = {name: threading.Event() for name in task_names}

    def worker(name):
        # Tag thread so subprocess wrapper knows which task owns it
        threading.current_thread()._task_name = name
        sys.stdout = io.StringIO()
        sys.stderr = io.StringIO()

        state = task_states[name]
        if state.status == TaskState.SKIPPED:
            task_done_events[name].set()
            return name, {"skipped": True}

        # Wait for dependencies to finish
        deps = TASK_DEPENDENCIES.get(name, set())
        for dep in deps:
            if dep in task_done_events:
                state.phase = f"waiting for {dep}"
                task_done_events[dep].wait()

        resource = state.resource_type
        sem = semaphores.get(resource, semaphores["default"])
        sem.acquire()
        try:
            state.status = TaskState.RUNNING
            state.phase = step or "run"
            state.start_time = time.time()
            result = run_task_fn(name, scan, step=step)
            state.elapsed = time.time() - state.start_time
            has_error = any(v == "ERROR" for v in result.values() if isinstance(v, str))
            state.status = TaskState.ERROR if has_error else TaskState.OK
            return name, result
        except Exception as e:
            state.elapsed = time.time() - state.start_time
            state.status = TaskState.ERROR
            state.last_log = str(e)[:55]
            state.logs.append(f"EXCEPTION: {e}")
            return name, {"error": str(e)}
        finally:
            sem.release()
            task_done_events[name].set()

    # Start all workers — dependencies are handled inside worker via events
    runnable = [n for n in task_names if n not in skip_tasks]
    pool = ThreadPoolExecutor(max_workers=sum(RESOURCE_LIMITS.values()))
    futures = {pool.submit(worker, name): name for name in runnable}

    # Collect results in background
    def collect_results():
        for future in futures:
            try:
                n, r = future.result()
                all_results[n] = r
            except Exception as e:
                nm = futures[future]
                all_results[nm] = {"error": str(e)}

    result_thread = threading.Thread(target=collect_results, daemon=True)
    result_thread.start()

    # TUI state
    selected = 0
    viewing_log = False
    log_offset = 0
    names = list(task_states.keys())
    quit_flag = False

    # Set terminal to raw mode for key capture
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    try:
        tty.setcbreak(fd)
        out.write(HIDE_CURSOR)
        # Disable scroll region / lock cursor area: print enough blank lines
        # to claim terminal space, then move cursor back to top of that area
        cols, rows = _get_terminal_size()
        tui_height = rows
        out.write("\n" * tui_height)  # push existing content up
        out.write(f"{CSI}{tui_height}A")  # move cursor back up
        # Save this position as our drawing origin
        out.write(f"{CSI}s")  # save cursor position
        # Disable terminal scrolling within our region
        out.write(f"{CSI}1;{tui_height}r")  # set scroll region
        out.flush()

        while not quit_flag:
          try:
            cols, rows = _get_terminal_size()
            view_h = rows - 3

            # Build frame buffer
            frame = []

            # Header (row 0)
            ok = sum(1 for s in task_states.values() if s.status == TaskState.OK)
            err = sum(1 for s in task_states.values() if s.status == TaskState.ERROR)
            run = sum(1 for s in task_states.values() if s.status == TaskState.RUNNING)
            wait = sum(1 for s in task_states.values() if s.status == TaskState.WAITING)
            done = all(s.status in (TaskState.OK, TaskState.ERROR, TaskState.SKIPPED) for s in task_states.values())

            scan_label = getattr(scan, 'scan_id', '') or getattr(scan, 'city_name', '') or ''
            header = f" {scan_label}  {GREEN}✓{ok}{RESET}  {CYAN}⟳{run}{RESET}  {DIM}⏳{wait}{RESET}  {RED}✗{err}{RESET}"
            if done:
                if auto_exit:
                    quit_flag = True
                header += f"  {GREEN}{BOLD}ALL DONE — press q to exit{RESET}"
            frame.append(f"{BG_BLUE}{WHITE}{BOLD} {scan_label} {RESET}{header}{RESET}")

            if viewing_log:
                state = task_states[names[selected]]
                title = f" ← Esc  │  {state.name} ({len(state.logs)} lines)"
                frame.append(f"{REVERSE}{title:{cols}}{RESET}")

                total = len(state.logs)
                start = max(0, total - view_h + log_offset)
                end = min(total, start + view_h)
                visible = state.logs[start:end]

                for i in range(view_h):
                    if i < len(visible):
                        line = visible[i][:cols-1]
                        if "ERROR" in visible[i] or "EXCEPTION" in visible[i]:
                            frame.append(f"{RED}{line}{RESET}")
                        elif "WARNING" in visible[i]:
                            frame.append(f"{YELLOW}{line}{RESET}")
                        else:
                            frame.append(line)
                    else:
                        frame.append("")

                frame.append(f"{DIM} [↑↓] scroll  [Esc] back  [q] quit{RESET}")
            else:
                for i, name in enumerate(names):
                    if i >= view_h:
                        break
                    state = task_states[name]
                    icons = {"waiting": "⏳", "running": "⟳ ", "ok": "✓ ", "error": "✗ ", "skipped": "─ "}
                    icon = icons[state.status]
                    elapsed = _elapsed_str(state)

                    if state.status == TaskState.OK:
                        status_text = "done"
                    elif state.status == TaskState.ERROR:
                        status_text = state.last_log or "failed"
                    elif state.status == TaskState.WAITING:
                        status_text = f"waiting ({state.resource_type})"
                    elif state.status == TaskState.SKIPPED:
                        status_text = "skipped"
                    else:
                        status_text = state.last_log or "running"

                    row = f" {icon} {name:<18} {state.phase:<8} {status_text:<45} {elapsed:>7}"
                    row = row[:cols]

                    if i == selected:
                        frame.append(f"{REVERSE}{row:{cols}}{RESET}")
                    elif state.status == TaskState.OK:
                        frame.append(f"{GREEN}{row}{RESET}")
                    elif state.status == TaskState.ERROR:
                        frame.append(f"{RED}{row}{RESET}")
                    elif state.status == TaskState.RUNNING:
                        frame.append(f"{CYAN}{row}{RESET}")
                    else:
                        frame.append(f"{DIM}{row}{RESET}")

                for i in range(len(names), view_h):
                    frame.append("")

                frame.append(f"{DIM} [↑↓] select  [Enter] log  [q] quit{RESET}")

            # Write entire frame at once with absolute positioning
            buf = []
            for row_idx, line in enumerate(frame):
                buf.append(f"{CSI}{row_idx+1};1H{CLEAR_LINE}{line}")
            out.write("".join(buf))
            out.flush()

            # Read key
            key = _read_key(0.4)

            if key == 'UP':
                if viewing_log:
                    log_offset = min(log_offset + 3, 0)
                else:
                    selected = max(0, selected - 1)
            elif key == 'DOWN':
                if viewing_log:
                    log_offset = max(log_offset - 3, -(len(task_states[names[selected]].logs)))
                else:
                    selected = min(len(names) - 1, selected + 1)
            elif key == 'ENTER':
                if not viewing_log:
                    viewing_log = True
                    log_offset = 0
            elif key == 'ESC':
                if viewing_log:
                    viewing_log = False
            elif key == 'q':
                quit_flag = True

          except KeyboardInterrupt:
            quit_flag = True

    finally:
        # Reset scroll region and restore terminal
        out.write(f"{CSI}r")  # reset scroll region to full screen
        # Clear the TUI area
        for i in range(tui_height):
            out.write(f"{CSI}{i+1};1H{CLEAR_LINE}")
        out.write(f"{CSI}1;1H")  # move to top
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        out.write(SHOW_CURSOR)
        out.flush()

    pool.shutdown(wait=True)
    result_thread.join(timeout=10)

    # Restore subprocess.run, setup_logger, and log handlers
    _subprocess.run = _original_subprocess_run
    _log_mod.setup_logger = _original_setup_logger
    logging.getLogger = old_getLogger
    root_logger.removeHandler(capture)
    for h in saved_handlers:
        root_logger.addHandler(h)

    # Summary
    ok = sum(1 for s in task_states.values() if s.status == TaskState.OK)
    err = sum(1 for s in task_states.values() if s.status == TaskState.ERROR)
    skip = sum(1 for s in task_states.values() if s.status == TaskState.SKIPPED)
    wall = max((s.elapsed for s in task_states.values() if s.elapsed), default=0)
    print(f"\n  {ok} passed  {err} failed  {skip} skipped  ({wall:.0f}s wall time)\n")

    for name, state in task_states.items():
        if state.status == TaskState.ERROR:
            print(f"  FAILED: {name}")
            for line in state.logs[-10:]:
                print(f"    {line}")
            print()

    return all_results
