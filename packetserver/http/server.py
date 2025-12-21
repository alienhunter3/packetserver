# packetserver/http/server.py
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from ..database import get_db_connection  # reuse existing helper if available
from .database import get_http_user
from .auth import HttpUser

app = FastAPI(
    title="PacketServer HTTP API",
    description="RESTful interface to the AX.25 packet radio BBS",
    version="0.1.0",
)

# Mount static files
app.mount("/static", StaticFiles(directory="packetserver/http/static"), name="static")

# Templates
templates = Jinja2Templates(directory="packetserver/http/templates")

security = HTTPBasic()


async def get_current_http_user(credentials: HTTPBasicCredentials = Depends(security)):
    db = get_db_connection()  # your existing way to get the open DB
    user: HttpUser | None = get_http_user(db, credentials.username)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Basic"},
        )

    if not user.enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="HTTP access disabled for this user",
        )

    if not user.verify_password(credentials.password):
        user.record_login_failure()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Basic"},
        )

    user.record_login_success()
    return user


# ------------------------------------------------------------------
# Public routes (no auth)
# ------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "message": "Welcome to PacketServer HTTP Interface"}
    )


@app.get("/health")
async def health():
    return {"status": "ok", "service": "packetserver-http"}


# ------------------------------------------------------------------
# Protected routes (require auth)
# ------------------------------------------------------------------
@app.get("/api/v1/profile")
async def profile(current_user: HttpUser = Depends(get_current_http_user)):
    return {
        "username": current_user.username,
        "enabled": current_user.enabled,
        "rf_enabled": current_user.rf_enabled,
        "created_at": current_user.created_at,
        "last_login": current_user.last_login,
    }


# Example future endpoint – list recent messages (placeholder)
@app.get("/api/v1/messages")
async def list_messages(
    limit: int = 20,
    current_user: HttpUser = Depends(get_current_http_user)
):
    # TODO: implement actual message fetching from ZODB
    return {"messages": [], "note": "Not implemented yet"}