import logging
import logging.handlers
import os
import sys

if sys.platform == "win32":
    # Windows: physische Pixel überall (UIA, Win32, Qt). Auf dem Mac rechnet alles in Punkten.
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "0")

from . import osapi  # noqa: E402
from .paths import data_dir  # noqa: E402

osapi.set_dpi_awareness()

LOG_DIR = data_dir()


def setup_logging():
    """Log mit Rotation (max. 3 × 1 MB). Ausführliche Statuszeilen nur mit CLAUDE_PET_DEBUG=1
    oder bei eingeschalteter Entwickler-Ansicht."""
    os.makedirs(LOG_DIR, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        os.path.join(LOG_DIR, "pet.log"), maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.DEBUG if os.environ.get("CLAUDE_PET_DEBUG") == "1" else logging.INFO)
    logging.getLogger("comtypes").setLevel(logging.WARNING)


def main():
    setup_logging()
    if not osapi.single_instance():
        logging.info("läuft schon – beende")
        return 0
    from .controller import run
    try:
        return run()
    except Exception:
        logging.exception("abgestürzt")
        raise


if __name__ == "__main__":
    sys.exit(main())
