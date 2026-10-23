import logging
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR/ "logs"
LOG_DIR.mkdir(exist_ok=True)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "baseline.log"),
        ],
)

logger = logging.getLogger("sales_api.baseline")


def save_sale(branch, transaction_id, quantity):
    logger.info(f"Saving sale {transaction_id} from {branch}")
    try:
        return 1000 / quantity
    except ZeroDivisionError:
        logger.exception(f"Failed to save sale {transaction_id} from {branch}")
        return None

save_sale("Eldoret", "TXN-0001", 2)
save_sale("Nairobi", "TXN-0002", 0)
logger.warning("Retrying sale TXN-0002 for Nairobi")

raise RuntimeError("Unhandled crash in baseline")