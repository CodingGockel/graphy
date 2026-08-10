import logging
from pathlib import Path

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

logger = logging.getLogger("BACKEND")
logger.setLevel(logging.DEBUG)

formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)

console = logging.StreamHandler()
console.setLevel(logging.INFO)
console.setFormatter(formatter)

file = logging.FileHandler(LOG_DIR / "server.log", mode="w", encoding="utf-8", delay=False)
file.setLevel(logging.DEBUG)
file.setFormatter(formatter)

if not logger.handlers:
    logger.addHandler(console)
    logger.addHandler(file)

logger.propagate = False