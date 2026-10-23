import json
import logging
import sys
import threading
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

DEFAULT_LOG_DIR = Path(__file__).resolve().parent / "logs"

# Every attribute a plain LogRecord already has. Anything on a record that is NOT
# in this set must have come from `extra={...}`, so we treat it as a custom field.
STANDARD_ATTRS = set(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()
) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    """Turn one LogRecord into one line of JSON."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc)
            .isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        for key, value in record.__dict__.items():
            if key not in STANDARD_ATTRS:
                payload[key] = value

        if record.exc_info and record.exc_info[0] is not None:
            exc_type, exc_value, _ = record.exc_info
            payload["exception"] = {
                "type": exc_type.__name__,
                "message": str(exc_value),
                "traceback": self.formatException(record.exc_info),
            }

        return json.dumps(payload, default=str)


class ContextFilter(logging.Filter):
    """Stamp constant context (service, environment) onto every record.

    A value passed per call via `extra={...}` wins over the constant.
    """

    def __init__(self, **context):
        super().__init__()
        self.context = context

    def filter(self, record: logging.LogRecord) -> bool:
        for key, value in self.context.items():
            if not hasattr(record, key):
                setattr(record, key, value)
        return True


def install_exception_hooks(logger_name="uncaught"):
    """Route uncaught exceptions (main thread and other threads) into logging."""
    logger = logging.getLogger(logger_name)

    def handle_uncaught(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            # Ctrl+C is not a bug: let Python handle it the normal way
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logger.critical(
            "Uncaught exception",
            exc_info=(exc_type, exc_value, exc_traceback),
        )

    def handle_thread_exception(args):
        if issubclass(args.exc_type, SystemExit):
            return
        logger.critical(
            "Uncaught exception in thread",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
            extra={"thread_name": args.thread.name if args.thread else None},
        )

    sys.excepthook = handle_uncaught
    threading.excepthook = handle_thread_exception


def setup_logging(
    log_dir=DEFAULT_LOG_DIR,
    log_name="app.log",
    console_level=logging.INFO,
    file_level=logging.DEBUG,
    max_bytes=1_000_000,
    backup_count=5,
    service="sales_api",
    environment="development",
    capture_uncaught=True,
):
    """Configure the root logger once: JSON to stdout + JSON to a rotating file."""
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    formatter = JsonFormatter()
    context_filter = ContextFilter(service=service, environment=environment)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(console_level)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(context_filter)

    file_handler = RotatingFileHandler(
        log_dir / log_name,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(file_level)
    file_handler.setFormatter(formatter)
    file_handler.addFilter(context_filter)

    root = logging.getLogger()
    root.setLevel(min(console_level, file_level))

    # Safe to call twice: close and remove old handlers first, so no duplicate lines
    # and no stale file handle holding the log file open (matters on Windows).
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()

    root.addHandler(console_handler)
    root.addHandler(file_handler)

    if capture_uncaught:
        install_exception_hooks()