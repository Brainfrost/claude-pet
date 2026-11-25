import logging
import logging.handlers
import os
import sys

os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "0")

from . import winapi  # noqa: E402

winapi.set_dpi_awareness()

LOG_DIR = os.path.join(os.environ.get("LOCALAPPDATA", "."), "claude-pet")


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
    if not winapi.single_instance():
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
