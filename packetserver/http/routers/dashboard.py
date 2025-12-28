# packetserver/http/routers/dashboard.py
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from packetserver.http.dependencies import get_current_http_user
from packetserver.http.auth import HttpUser
from packetserver.http.server import templates
from packetserver.http.database import DbDependency

router = APIRouter(tags=["dashboard"])

# Import the function at module level (safe now that circular import is fixed)
from packetserver.http.routers.messages import get_messages as api_get_messages
from .bulletins import list_bulletins


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    db: DbDependency,
    request: Request,
    current_user: HttpUser = Depends(get_current_http_user)
):
    messages_resp = await api_get_messages(
        db,
        current_user=current_user,
        type="all",
        limit=100,
        since=None  # prevents Query wrapper
    )
    with db.transaction() as conn:
        # Internal call – pass explicit defaults to avoid Query object injection

        messages = messages_resp["messages"]

        bulletins_resp = await list_bulletins(conn, limit=10, since=None)
        recent_bulletins = bulletins_resp["bulletins"]

        return templates.TemplateResponse(
            "dashboard.html",
            {
            "request": request,
            "current_user": current_user.username,
            "messages": messages,
            "bulletins": recent_bulletins
             }
        )

@router.get("/dashboard/profile", response_class=HTMLResponse)
async def profile_page(
    db: DbDependency,
    request: Request,
    current_user: HttpUser = Depends(get_current_http_user)
):
    from packetserver.http.routers.profile import profile as api_profile
    profile_data = await api_profile(db, current_user=current_user)

    return templates.TemplateResponse(
        "profile.html",
        {"request": request, "current_user": current_user.username, "profile": profile_data}
    )