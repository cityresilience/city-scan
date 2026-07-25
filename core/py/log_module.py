# log_module.py
import logging
import os
import sys

# Module-level state for the file handler
_file_handler = None


def _force_utf8_console():
    """Make stdout/stderr UTF-8 so log messages can't crash the process.

    Windows consoles default to cp1252. Several log lines here contain box-
    drawing characters ('─' in the task/phase headers), and city names can carry
    accents, so a plain StreamHandler raises UnicodeEncodeError mid-run. Python
    prints '--- Logging error ---' and continues, but it buries real output and
    signals a fault that isn't one. errors='replace' means an unmappable glyph
    degrades to '?' instead of throwing.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream is not None and hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa — never let logging setup break a run
            pass


_force_utf8_console()


def setup_logger(name: str = None):
    """
    Central logging setup.
    Usage in modules:
        logger = setup_logger(__name__)
    """

    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False  # prevent duplicate logs from parent loggers

    # Avoid duplicate handlers if logger is created multiple times
    if logger.hasHandlers():
        return logger

    # Console: short format
    console_format = "%(levelname)s | %(name)s | %(message)s"
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(console_format))
    logger.addHandler(console_handler)

    # Attach file handler if already configured
    if _file_handler is not None:
        logger.addHandler(_file_handler)

    return logger


def set_log_dir(log_dir):
    """
    Set the log file directory. Call once after the city folder is known.
    Overwrites previous log. Attaches file handler to all existing loggers.
    """
    global _file_handler

    os.makedirs(log_dir, exist_ok=True)

    file_format = "%(asctime)s | %(levelname)s | %(name)s | %(filename)s:%(lineno)d | %(message)s"
    log_path = os.path.join(log_dir, "app.log")
    _file_handler = logging.FileHandler(log_path, mode='w', encoding='utf-8')
    _file_handler.setFormatter(logging.Formatter(file_format))

    # Attach to all existing loggers that have a console handler (i.e. ours)
    for lg_name in logging.Logger.manager.loggerDict:
        lg = logging.getLogger(lg_name)
        if any(isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler) for h in lg.handlers):
            lg.addHandler(_file_handler)
