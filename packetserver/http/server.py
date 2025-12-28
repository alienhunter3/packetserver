# packetserver/http/server.py
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path
import base64

from .database import init_db, get_db, get_server_config_from_db
from .routers import public, profile, messages, send
from .logging import init_logging

init_logging()

BASE_DIR = Path(__file__).parent.resolve()

app = FastAPI(
    title="PacketServer HTTP API",
    description="RESTful interface to the AX.25 packet radio BBS",
    version="0.5.0",
)

# Define templates EARLY (before importing dashboard)
templates = Jinja2Templates(directory=BASE_DIR / "templates")



def b64decode_filter(value: str) -> str:
    try:
        decoded_bytes = base64.b64decode(value)
        # Assume UTF-8 text (common for job output/errors)
        return decoded_bytes.decode('utf-8', errors='replace')
    except Exception:
        return "[Invalid base64 data]"

templates.env.filters["b64decode"] = b64decode_filter

from datetime import datetime, timezone

def timestamp_to_date(ts):
    if ts is None:
        return "Never"
    try:
        dt = datetime.fromtimestamp(float(ts), tz=timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except (ValueError, TypeError):
        return "Invalid"

# Register the filter correctly
templates.env.filters["timestamp_to_date"] = timestamp_to_date

# Static files
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

# Now safe to import dashboard (it needs templates)
from .routers import dashboard, bulletins
from .routers.message_detail import router as message_detail_router
from .routers.messages import html_router
from .routers.objects import router as objects_router
from .routers import objects_html
from .routers.jobs import router as jobs_router
from .routers.jobs import dashboard_router as jobs_html_router

# initialize database
init_db()
db = get_db()
server_config = get_server_config_from_db(db)
templates.env.globals['server_name'] = server_config['server_name']
templates.env.globals['server_callsign'] = server_config['server_callsign']
templates.env.globals['motd'] = server_config['motd']
templates.env.globals['server_operator'] = server_config['operator']

# Include routers
app.include_router(public.router)
app.include_router(profile.router)
app.include_router(messages.router)
app.include_router(send.router)
app.include_router(dashboard.router)
app.include_router(bulletins.router)
app.include_router(bulletins.html_router)
app.include_router(message_detail_router)
app.include_router(html_router)
app.include_router(objects_router)
app.include_router(objects_html.router)
app.include_router(jobs_router)
app.include_router(jobs_html_router)

