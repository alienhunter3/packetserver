# packetserver/http/routers/profile.py
from fastapi import APIRouter, Depends

from packetserver.http.dependencies import get_current_http_user
from packetserver.http.auth import HttpUser
from packetserver.http.database import DbDependency

router = APIRouter(prefix="/api/v1", tags=["auth"])


@router.get("/profile")
async def profile(db: DbDependency, current_user: HttpUser = Depends(get_current_http_user)):
    username = current_user.username
    rf_enabled = current_user.is_rf_enabled(db)

    # Get main BBS User and safe dict
    with db.transaction() as conn:
        root = conn.root()
        main_users = root.get('users', {})
        bbs_user = main_users.get(username)
        safe_profile = bbs_user.to_safe_dict() if bbs_user else {}


        return {
            **safe_profile,
            "http_enabled": current_user.http_enabled,
            "rf_enabled": rf_enabled,
            "http_created_at": current_user.created_at,
            "http_last_login": current_user.last_login,
        }