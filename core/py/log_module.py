# log_module.py
import logging
import os

# Module-level state for the file handler
_file_handler = None


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
    # Parallel Cloud Run fan-out: each container gets its own log file so they
    # don't clobber each other on the shared GCS-FUSE mount (stale file handle).
    task_index = os.environ.get("CLOUD_RUN_TASK_INDEX")
    log_name = f"app.{task_index}.log" if task_index is not None else "app.log"
    log_path = os.path.join(log_dir, log_name)
    _file_handler = logging.FileHandler(log_path, mode='w')
    _file_handler.setFormatter(logging.Formatter(file_format))

    # Attach to all existing loggers that have a console handler (i.e. ours)
    for lg_name in logging.Logger.manager.loggerDict:
        lg = logging.getLogger(lg_name)
        if any(isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler) for h in lg.handlers):
            lg.addHandler(_file_handler)
