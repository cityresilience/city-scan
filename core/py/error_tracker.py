import logging
import threading


class ErrorTracker:
    """Counts ERROR+ and WARNING log calls for the current thread only."""
    def __init__(self):
        self.count = 0
        self.warning_count = 0
        self.no_data_count = 0
        self.messages = []
        self._original = None
        self._thread_id = None

    @property
    def status(self):
        if self.count > 0:
            return "ERROR"
        if self.warning_count > 0:
            return "WARNING"
        if self.no_data_count > 0:
            return "NO_DATA"
        return "OK"

    def __enter__(self):
        self._thread_id = threading.current_thread().ident
        self._original = logging.Logger._log
        tracker = self
        original = self._original
        def _counting_log(logger_self, level, msg, args, **kwargs):
            if threading.current_thread().ident == tracker._thread_id:
                if level >= logging.ERROR:
                    tracker.count += 1
                    try:
                        tracker.messages.append(str(msg) % args if args else str(msg))
                    except Exception:
                        tracker.messages.append(str(msg))
                elif level >= logging.WARNING:
                    msg_str = str(msg) % args if args else str(msg)
                    if "[NO_DATA]" in msg_str:
                        tracker.no_data_count += 1
                    else:
                        tracker.warning_count += 1
            original(logger_self, level, msg, args, **kwargs)
        logging.Logger._log = _counting_log
        return self

    def __exit__(self, *exc):
        logging.Logger._log = self._original
        return False
