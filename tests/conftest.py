from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "yomiyasu-en"
SCRIPTS = SKILL / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.dont_write_bytecode = True
