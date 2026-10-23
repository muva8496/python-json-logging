import logging
import random
import threading
from pathlib import Path

from app_logging import setup_logging

SAMPLE_DIR = Path(__file__).resolve().parent / "sample_logs"
SAMPLE_DIR.mkdir(exist_ok=True)
for old in SAMPLE_DIR.glob("app.log*"):
    old.unlink()  # start clean so every run produces the same kind of sample

setup_logging(
    log_dir=SAMPLE_DIR,
    console_level=logging.WARNING,  # console stays quiet; the file keeps everything
    max_bytes=10_000,               # tiny on purpose, so rotation is easy to see
    backup_count=5,
    environment="demo",
)
logger = logging.getLogger("sales_api.demo")

random.seed(7)
BRANCHES = ["Nairobi", "Mombasa", "Kisumu", "Nakuru", "Eldoret"]
TOTAL_SALES = 80


class DatabaseLocked(Exception):
    pass


def submit_sale(i):
    branch = random.choice(BRANCHES)
    transaction_id = f"TXN-{1000 + i}"
    amount = random.randint(1, 6) * 1500
    context = {"branch": branch, "transaction_id": transaction_id}

    logger.debug("Validating payload", extra=context)
    roll = random.random()
    try:
        if roll < 0.08:
            raise DatabaseLocked("database is locked")
        if roll < 0.20:
            logger.warning("Duplicate sale rejected", extra=context)
            return
        logger.info("Sale saved", extra={**context, "amount_ksh": amount})
    except DatabaseLocked:
        logger.exception("Failed to save sale", extra=context)


for i in range(TOTAL_SALES):
    submit_sale(i)


def report_worker():
    raise RuntimeError("Report worker crashed")


worker = threading.Thread(target=report_worker, name="report-worker")
worker.start()
worker.join()

logger.info("Demo finished", extra={"sales_submitted": TOTAL_SALES})

print("\nFiles written to sample_logs/:")
for path in sorted(SAMPLE_DIR.glob("app.log*")):
    print(f"  {path.name:<12} {path.stat().st_size:>7} bytes")