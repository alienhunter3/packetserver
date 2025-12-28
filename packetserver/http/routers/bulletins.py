from fastapi import APIRouter, Path, Query, Depends, HTTPException, Request, status, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from typing import Optional, List
from pydantic import BaseModel, Field, constr
from datetime import datetime
import transaction
from persistent.list import PersistentList
from ZODB.Connection import Connection
import logging

from packetserver.http.database import DbDependency
from ..dependencies import get_current_http_user
from ..auth import HttpUser
from ..server import templates

from packetserver.server.bulletin import Bulletin

# API router (/api/v1)
router = APIRouter(prefix="/api/v1", tags=["bulletins"])

# HTML router (pretty URLs: /bulletins, /bulletins/{bid})
html_router = APIRouter(tags=["bulletins-html"])

# --- API Endpoints ---

async def list_bulletins(connection: Connection, limit: int = 50, since: Optional[datetime] = None) -> dict:
    root = connection.root()
    bulletins_list: List[Bulletin] = root.get("bulletins", [])

    # Newest first
    bulletins_list = sorted(bulletins_list, key=lambda b: b.created_at, reverse=True)

    if since:
        bulletins_list = [b for b in bulletins_list if b.created_at > since]

    bulletins = [
        {
            "id": b.id,
            "author": b.author,
            "subject": b.subject,
            "body": b.body,
            "created_at": b.created_at.isoformat() + "Z",
            "updated_at": b.updated_at.isoformat() + "Z",
        }
        for b in bulletins_list[:limit]
    ]

    return {"bulletins": bulletins}

@router.get("/bulletins")
async def api_list_bulletins(
    db: DbDependency,
    limit: Optional[int] = Query(50, le=100),
    since: Optional[datetime] = None,
):
    with db.transaction() as conn:
        return await list_bulletins(conn, limit=limit, since=since)

async def get_one_bulletin(connection: Connection, bid: int) -> dict:
    root = connection.root()
    bulletins_list: List[Bulletin] = root.get("bulletins", [])

    for b in bulletins_list:
        if b.id == bid:
            return {
                "id": b.id,
                "author": b.author,
                "subject": b.subject,
                "body": b.body,
                "created_at": b.created_at.isoformat() + "Z",
                "updated_at": b.updated_at.isoformat() + "Z",
            }
    raise HTTPException(status_code=404, detail="Bulletin not found")

@router.get("/bulletins/{bid}")
async def api_get_bulletin(
    db: DbDependency,
    bid: int,
):
    with db.transaction() as conn:
        return await get_one_bulletin(conn, bid)

class CreateBulletinRequest(BaseModel):
    subject: constr(min_length=1, max_length=100) = Field(..., description="Bulletin subject/title")
    body: constr(min_length=1) = Field(..., description="Bulletin body text")

@router.post("/bulletins", status_code=status.HTTP_201_CREATED)
async def create_bulletin(
    db: DbDependency,
    payload: CreateBulletinRequest,
    current_user: HttpUser = Depends(get_current_http_user)
):
    with db.transaction() as conn:
        root = conn.root()

        if 'bulletins' not in root:
            root['bulletins'] = PersistentList()

        new_bulletin = Bulletin(
            author=current_user.username,
            subject=payload.subject.strip(),
            text=payload.body.strip()
        )

        new_id = new_bulletin.write_new(root)

        transaction.commit()

        return {
            "id": new_id,
            "author": new_bulletin.author,
            "subject": new_bulletin.subject,
            "body": new_bulletin.body,
            "created_at": new_bulletin.created_at.isoformat() + "Z",
            "updated_at": new_bulletin.updated_at.isoformat() + "Z",
        }

# --- HTML Pages (require login) ---

@html_router.get("/bulletins", response_class=HTMLResponse)
async def bulletin_list_page(
    db: DbDependency,
    request: Request,
    limit: Optional[int] = Query(50, le=100),
    current_user: HttpUser = Depends(get_current_http_user)
):
    with db.transaction() as conn:
        api_resp = await list_bulletins(conn, limit=limit, since=None)
        bulletins = api_resp["bulletins"]

        return templates.TemplateResponse(
            "bulletin_list.html",
            {
                "request": request,
                "bulletins": bulletins,
                "current_user": current_user.username
            }
        )

@html_router.get("/bulletins/new", response_class=HTMLResponse)
async def bulletin_new_form(
    request: Request,
    current_user: HttpUser = Depends(get_current_http_user)  # require login
):
    return templates.TemplateResponse(
        "bulletin_new.html",
        {"request": request, "error": None, "current_user": current_user.username}
    )

@html_router.post("/bulletins/new")
async def bulletin_new_submit(
    db: DbDependency,
    request: Request,
    subject: str = Form(...),
    body: str = Form(...),
    current_user: HttpUser = Depends(get_current_http_user)
):
    if not subject.strip() or not body.strip():
        return templates.TemplateResponse(
            "bulletin_new.html",
            {"request": request, "error": "Subject and body are required."},
            status_code=400
        )
    with db.transaction() as conn:
        root = conn.root()

        if 'bulletins' not in root:
            root['bulletins'] = PersistentList()

        new_bulletin = Bulletin(
            author=current_user.username,
            subject=subject.strip(),
            text=body.strip()
        )

        new_id = new_bulletin.write_new(root)

        return RedirectResponse(url=f"/bulletins/{new_id}", status_code=303)

@html_router.get("/bulletins/{bid}", response_class=HTMLResponse)
async def bulletin_detail_page(
    db: DbDependency,
    request: Request,
    bid: int = Path(...),
    current_user: HttpUser = Depends(get_current_http_user)
):
    with db.transaction() as conn:
        bulletin = await get_one_bulletin(conn, bid=bid)

        return templates.TemplateResponse(
            "bulletin_detail.html",
            {"request": request, "bulletin": bulletin, "current_user": current_user.username}
        )

@router.delete("/bulletins/{bid}", status_code=204)
async def delete_bulletin(
    bid: int,
    db: DbDependency,
    current_user: HttpUser = Depends(get_current_http_user)
):
    username = current_user.username

    try:
        with db.transaction() as conn:
            root = conn.root()
            bulletins_list: PersistentList = root.get("bulletins", PersistentList())

            # Find the bulletin
            bulletin_to_delete = None
            for b in bulletins_list:
                if b.id == bid:
                    bulletin_to_delete = b
                    break

            if not bulletin_to_delete:
                raise HTTPException(status_code=404, detail="Bulletin not found")

            if bulletin_to_delete.author != username:
                raise HTTPException(status_code=403, detail="Not authorized to delete this bulletin")

            # Remove it
            bulletins_list.remove(bulletin_to_delete)

            logging.info(f"User {username} deleted bulletin {bid}")

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Bulletin delete failed for {username} on {bid}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete bulletin")

    return None  # 204 No Content