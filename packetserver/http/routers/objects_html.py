from fastapi import APIRouter, Depends, Request, Form, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from uuid import UUID
import base64

from packetserver.http.dependencies import get_current_http_user
from packetserver.http.auth import HttpUser
from packetserver.http.server import templates
from packetserver.http.routers.objects import router as api_router  # to call internal endpoints
from packetserver.http.database import DbDependency
from packetserver.http.routers.objects import get_object_metadata as api_get_metadata
from packetserver.http.routers.objects import ObjectUpdate


router = APIRouter(tags=["objects_html"])

# Internal reference to the list function (assuming it's list_my_objects)
from packetserver.http.routers.objects import list_my_objects as api_list_objects

@router.get("/objects", response_class=HTMLResponse)
async def objects_page(
    db: DbDependency,
    request: Request,
    current_user: HttpUser = Depends(get_current_http_user)
):
    # Call the API list endpoint internally
    objects_resp = await api_list_objects(db, current_user=current_user)  # db injected via dependency
    objects = objects_resp  # it's already the list

    return templates.TemplateResponse(
        "objects.html",
        {
            "request": request,
            "current_user": current_user.username,
            "objects": objects
        }
    )

@router.get("/objects/{uuid}", response_class=HTMLResponse)
async def object_detail_page(
    request: Request,
    uuid: UUID,
    db: DbDependency,
    current_user: HttpUser = Depends(get_current_http_user)
):
    # Call the existing metadata API function
    obj = await api_get_metadata(uuid=uuid, db=db, current_user=current_user)

    return templates.TemplateResponse(
        "object_detail.html",
        {
            "request": request,
            "current_user": current_user.username,
            "obj": obj
        }
    )

@router.post("/objects/{uuid}")
async def update_object(
    db: DbDependency,
    uuid: UUID,
    request: Request,
    name: str = Form(None),
    private: str = Form("off"),  # checkbox sends "on" if checked
    new_text: str = Form(None),
    new_file: UploadFile = File(None),
    new_base64: str = Form(None),
    current_user: HttpUser = Depends(get_current_http_user)
):
    payload = {}
    if name is not None:
        payload["name"] = name
    payload["private"] = (private == "on")

    if new_text is not None and new_text.strip():
        payload["data_text"] = new_text.strip()
    elif new_file and new_file.filename:
        content = await new_file.read()
        payload["data_base64"] = base64.b64encode(content).decode('ascii')
    elif new_base64 and new_base64.strip():
        payload["data_base64"] = new_base64.strip()

    # Call the PATCH API internally (simple requests or direct function call)
    from packetserver.http.routers.objects import update_object as api_update
    await api_update(uuid=uuid, payload=ObjectUpdate(**payload), db=db, current_user=current_user)

    # Redirect back to the detail page (or /objects list)
    return RedirectResponse(url=f"/objects/{uuid}", status_code=303)