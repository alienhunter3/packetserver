from fastapi import APIRouter, Path, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse

from packetserver.http.dependencies import get_current_http_user
from packetserver.http.auth import HttpUser
from packetserver.http.server import templates
from packetserver.http.database import DbDependency

router = APIRouter(tags=["message-detail"])

@router.get("/dashboard/message/{msg_id}", response_class=HTMLResponse)
async def message_detail_page(
    db: DbDependency,
    request: Request,
    msg_id: str = Path(..., description="Message UUID as string"),
    current_user: HttpUser = Depends(get_current_http_user)
):
    # Reuse the existing API endpoint logic internally
    from packetserver.http.routers.messages import get_message as api_get_message

    # Call with mark_retrieved=True to auto-mark as read on view (optional—remove if you prefer manual)
    message_data = await api_get_message(
        db,
        msg_id=msg_id,
        mark_retrieved=True,
        current_user=current_user
    )

    return templates.TemplateResponse(
        "message_detail.html",
        {
            "request": request,
            "message": message_data,
            "current_user": current_user.username
        }
    )