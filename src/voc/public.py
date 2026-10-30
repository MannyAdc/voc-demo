"""A13: the public copy of the dashboard, for a host such as Azure App Service.

Started by the host with `python -m uvicorn voc.public:app --host 0.0.0.0 --port 8000 --app-dir src`. It reads
the committed results files from the project folder, found from this file's own path. Azure App Service sets WEBSITE_HOSTNAME to the app's own host name, and the
app answers only to that name. The public copy never reads the local staged table, never serves complaint text
or the consumer's own choice, and stores no review (voc.api, voc.analyst).
"""
import os
from pathlib import Path

from voc.api import create_app

# The project folder, found from this file (src/voc/public.py), so the folder the host starts in does not matter.
ROOT = Path(__file__).resolve().parents[2]
HOST = os.environ.get("WEBSITE_HOSTNAME")
if not HOST:
    raise RuntimeError("WEBSITE_HOSTNAME is not set, so the public copy does not know which host name to answer to")

app = create_app(ROOT, public_host=HOST)
