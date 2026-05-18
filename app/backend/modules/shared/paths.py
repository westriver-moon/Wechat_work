from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = BACKEND_ROOT.parent
DATA_ROOT = APP_ROOT / "data"
WEB_ROOT = APP_ROOT / "web"