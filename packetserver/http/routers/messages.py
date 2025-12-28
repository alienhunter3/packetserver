# packetserver/http/routers/messages.py
from fastapi import APIRouter, Depends, Query, HTTPException, Path, Request
from fastapi.responses import HTMLResponse
from typing import Optional
from datetime import datetime
from persistent.mapping import PersistentMapping
import persistent.list
import transaction
from pydantic import BaseModel, Field, validator

from packetserver.http.dependencies import get_current_http_user
from packetserver.http.auth import HttpUser
from packetserver.http.database import DbDependency


html_router = APIRouter(tags=["messages-html"])
router = APIRouter(prefix="/api/v1", tags=["messages"])

# Simple request model (only allow setting to true)
class MarkRetrievedRequest(BaseModel):
    retrieved: bool = Field(..., description="Set to true to mark as retrieved")

    @validator("retrieved")
    def must_be_true(cls, v):
        if not v:
            raise ValueError("retrieved must be true")
        return v


@router.get("/messages")
async def get_messages(
    db: DbDependency,
    current_user: HttpUser = Depends(get_current_http_user),
    type: str = Query("received", description="received, sent, or all"),
    limit: Optional[int] = Query(20, le=100, description="Max messages to return (default 20, max 100)"),
    since: Optional[str] = Query(None, description="ISO UTC timestamp filter (e.g. 2025-12-01T00:00:00Z)"),

):
    if limit is None or limit < 1:
        limit = 20

    username = current_user.username
    with db.transaction() as conn:
        root = conn.root()

        if 'messages' not in root:
            root['messages'] = PersistentMapping()
        if username not in root['messages']:
            root['messages'][username] = persistent.list.PersistentList()

        mailbox = root['messages'][username]

        since_dt = None
        if since:
            try:
                since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid 'since' format")

        messages = []
        for msg in mailbox:
            if type == "received" and msg.msg_from == username:
                continue
            if type == "sent" and msg.msg_from != username:
                continue
            if since_dt and msg.sent_at < since_dt:
                continue

            messages.append({
                "id": str(msg.msg_id),
                "from": msg.msg_from,
                "to": list(msg.msg_to) if isinstance(msg.msg_to, tuple) else [msg.msg_to],
                "sent_at": msg.sent_at.isoformat() + "Z",
                "text": msg.text,
                "has_attachments": len(msg.attachments) > 0,
                "retrieved": msg.retrieved,
            })

        messages.sort(key=lambda m: m["sent_at"], reverse=True)

        return {"messages": messages[:limit], "total_returned": len(messages[:limit])}

@router.get("/messages/{msg_id}")
async def get_message(
    db: DbDependency,
    msg_id: str = Path(..., description="UUID of the message (as string)"),
    mark_retrieved: bool = Query(False, description="If true, mark message as retrieved/read"),
    current_user: HttpUser = Depends(get_current_http_user)
):
    with db.transaction() as conn:
        root = conn.root()

        username = current_user.username

        messages_root = root.get('messages', {})
        mailbox = messages_root.get(username)
        if not mailbox:
            raise HTTPException(status_code=404, detail="Mailbox not found")

        # Find message by ID
        target_msg = None
        for msg in mailbox:
            if str(msg.msg_id) == msg_id:
                target_msg = msg
                break

        if not target_msg:
            raise HTTPException(status_code=404, detail="Message not found")

        # Optionally mark as retrieved
        if mark_retrieved and not target_msg.retrieved:
            target_msg.retrieved = True
            target_msg._p_changed = True
            mailbox._p_changed = True
            # Explicit transaction for the write
            transaction.get().commit()

        return {
            "id": str(target_msg.msg_id),
            "from": target_msg.msg_from or "UNKNOWN",
            "to": list(target_msg.msg_to),
            "sent_at": target_msg.sent_at.isoformat() + "Z",
            "text": target_msg.text,
            "retrieved": target_msg.retrieved,
            "has_attachments": len(target_msg.attachments) > 0,
            # Future: "attachments": [...] metadata
        }

@router.patch("/messages/{msg_id}")
async def mark_message_retrieved(
    db: DbDependency,
    msg_id: str = Path(..., description="Message UUID as string"),
    payload: MarkRetrievedRequest = None,
    current_user: HttpUser = Depends(get_current_http_user)
):
    with db.transaction() as conn:
        root = conn.root()

        username = current_user.username
        mailbox = root.get('messages', {}).get(username)

        if not mailbox:
            raise HTTPException(status_code=404, detail="Mailbox not found")

        target_msg = None
        for msg in mailbox:
            if str(msg.msg_id) == msg_id:
                target_msg = msg
                break

        if not target_msg:
            raise HTTPException(status_code=404, detail="Message not found")

        if target_msg.retrieved:
            # Already marked – idempotent success
            return {"status": "already_retrieved", "id": msg_id}

        target_msg.retrieved = True
        target_msg._p_changed = True
        mailbox._p_changed = True
        transaction.get().commit()

        return {"status": "marked_retrieved", "id": msg_id}

@html_router.get("/messages", response_class=HTMLResponse)
async def message_list_page(
    db: DbDependency,
    request: Request,
    type: str = Query("received", alias="msg_type"),  # matches your filter links
    limit: Optional[int] = Query(50, le=100),
    current_user: HttpUser = Depends(get_current_http_user)
):
    from packetserver.http.server import templates
    # Directly call the existing API endpoint function
    api_resp = await get_messages(db, current_user=current_user, type=type, limit=limit, since=None)
    messages = api_resp["messages"]

    return templates.TemplateResponse(
        "message_list.html",
        {
            "request": request,
            "messages": messages,
            "msg_type": type,
            "current_user": current_user.username
        }
    )