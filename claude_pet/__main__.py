import logging
import os
import sys

os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "0")

from . import winapi  # noqa: E402

winapi.set_dpi_awareness()


def main():
    log_dir = os.path.join(os.environ.get("LOCALAPPDATA", "."), "claude-pet")
    os.makedirs(log_dir, exist_ok=True)
    logging.basicConfig(filename=os.path.join(log_dir, "pet.log"), level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s", encoding="utf-8")
    if not winapi.single_instance():
        logging.info("läuft schon – beende")
        return 0
    from .ui import run
    try:
        return run()
    except Exception:
        logging.exception("abgestürzt")
        raise


if __name__ == "__main__":
    sys.exit(main())
