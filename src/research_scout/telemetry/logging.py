import logging
import time
import uuid
from pathlib import Path

log = logging.getLogger("research_scout")


def new_run_id() -> str:
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return f"{stamp}-{uuid.uuid4().hex[:6]}"


def setup_logging(path: Path) -> None:
    log.setLevel(logging.INFO)
    log.handlers.clear()
    log.propagate = False
    handler = logging.FileHandler(path, encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%dT%H:%M:%SZ")
    formatter.converter = time.gmtime
    handler.setFormatter(formatter)
    log.addHandler(handler)
