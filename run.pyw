"""Starter ohne Konsolenfenster (für Autostart und Doppelklick)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)

from claude_pet.__main__ import main  # noqa: E402

sys.exit(main())
