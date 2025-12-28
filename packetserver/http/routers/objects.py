from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Header, Request
from fastapi.responses import PlainTextResponse, Response, JSONResponse, StreamingResponse, RedirectResponse
from typing import List, Optional
from datetime import datetime
from uuid import UUID
import mimetypes
import logging
from traceback import format_exc
import base64
import traceback
from pydantic import BaseModel, model_validator
import re

from packetserver.http.dependencies import get_current_http_user
from packetserver.http.auth import HttpUser
from packetserver.http.database import DbDependency
from packetserver.server.objects import Object
from packetserver.server.users import User


router = APIRouter(prefix="/api/v1", tags=["objects"])

class ObjectSummary(BaseModel):
    uuid: UUID
    name: str
    binary: bool
    size: int
    content_type: str
    private: bool
    created_at: datetime
    modified_at: datetime

@router.get("/objects", response_model=List[ObjectSummary])
async def list_my_objects(db: DbDependency, current_user: HttpUser = Depends(get_current_http_user)):
    username = current_user.username.upper().strip()  # ensure uppercase consistency
    logging.debug(f"Listing objects for user {username}")
    user_objects = []
    with db.transaction() as conn:
        for obj in Object.get_objects_by_username(username, conn):
            logging.debug(f"Found object {obj.uuid} for {username}")
            if obj:  # should always exist, but guard anyway
                content_type, _ = mimetypes.guess_type(obj.name)
                if content_type is None:
                    content_type = "application/octet-stream" if obj.binary else "text/plain"

                user_objects.append(ObjectSummary(
                    uuid=obj.uuid,
                    name=obj.name,
                    binary=obj.binary,
                    size=obj.size,
                    content_type=content_type,
                    private=obj.private,
                    created_at=obj.created_at,
                    modified_at=obj.modified_at
                ))

        # Sort newest first
        user_objects.sort(key=lambda x: x.created_at, reverse=True)

        return user_objects

@router.post("/objects", response_model=ObjectSummary)
async def upload_object(
    db: DbDependency,
    file: UploadFile = File(...),
    name: Optional[str] = Form(None),
    private: bool = Form(True),
    force_text: bool = Form(False),  # NEW: force treat as UTF-8 text
    current_user: HttpUser = Depends(get_current_http_user)
):
    username = current_user.username

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file upload")

    obj_name = (name or file.filename or "unnamed_object").strip()
    if len(obj_name) > 300:
        raise HTTPException(status_code=400, detail="Object name too long (max 300 chars)")
    if not obj_name:
        raise HTTPException(status_code=400, detail="Invalid object name")

    try:
        with db.transaction() as conn:
            root = conn.root()
            user = User.get_user_by_username(username, root)
            if not user:
                raise HTTPException(status_code=404, detail="User not found")

        # Handle force_text logic
        if force_text:
            try:
                text_content = content.decode('utf-8', errors='strict')
                object_data = text_content  # str → will set binary=False
            except UnicodeDecodeError:
                raise HTTPException(status_code=400, detail="Content is not valid UTF-8 and cannot be forced as text")
        else:
            object_data = content  # bytes → will set binary=True

        # Create and persist the object
        new_object = Object(name=obj_name, data=object_data)
        new_object.private = private

        obj_uuid = new_object.write_new(db, username=username)

        if force_text:
            obj_type = 'string'
        else:
            obj_type = 'binary'

        logging.info(f"User {username} uploaded {obj_type} object {obj_uuid} ({obj_name}, {len(content)} bytes, force_text={force_text})")

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Object upload failed for {username}: {e}\n{format_exc()}")
        raise HTTPException(status_code=500, detail="Failed to store object")

    # Build summary (matching your existing list endpoint)
    content_type, _ = mimetypes.guess_type(new_object.name)
    if content_type is None:
        content_type = "application/octet-stream" if new_object.binary else "text/plain"

    return ObjectSummary(
        uuid=obj_uuid,
        name=new_object.name,
        binary=new_object.binary,
        size=new_object.size,
        content_type=content_type,
        private=new_object.private,
        created_at=new_object.created_at,
        modified_at=new_object.modified_at
    )

class TextObjectCreate(BaseModel):
    text: str
    name: Optional[str] = None
    private: bool = True

@router.post("/objects/text", response_model=None)  # Remove response_model to allow mixed returns
async def create_text_object(
    request: Request,
    db: DbDependency,
    current_user: HttpUser = Depends(get_current_http_user)
):
    username = current_user.username

    # Determine content type and parse accordingly
    content_type = request.headers.get("content-type", "").lower()

    if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
        form = await request.form()
        name = form.get("name")
        text = form.get("text")
        private_str = form.get("private")  # "on" if checked, None otherwise
        is_form = True
    elif "application/json" in content_type:
        try:
            json_data = await request.json()
            name = json_data.get("name")
            text = json_data.get("text")
            private_str = json_data.get("private")
            is_form = False
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")
    else:
        raise HTTPException(status_code=415, detail="Unsupported Media Type")

    # Validate text
    if not text:
        raise HTTPException(status_code=400, detail="Text content cannot be empty")

    # Normalize name (optional, default like original)
    obj_name = (name or "text_object.txt").strip()
    if len(obj_name) > 300:
        raise HTTPException(status_code=400, detail="Object name too long (max 300 chars)")
    if not obj_name:
        raise HTTPException(status_code=400, detail="Invalid object name")

    # Normalize private to bool (handles form "on"/None, JSON bool, or string)
    if isinstance(private_str, bool):
        private = private_str
    elif isinstance(private_str, str):
        private = private_str.lower() in ("true", "on", "1", "yes")
    else:
        private = False  # Default to False if invalid/missing

    try:
        with db.transaction() as conn:
            root = conn.root()
            user = User.get_user_by_username(username, root)
            if not user:
                raise HTTPException(status_code=404, detail="User not found")

            # Create object with str data → forces binary=False
            new_object = Object(name=obj_name, data=text)
            new_object.private = private

            obj_uuid = new_object.write_new(db, username=username)

            logging.info(f"User {username} created text object {obj_uuid} ({obj_name}, {len(text)} chars)")

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Text object creation failed for {username}: {e}\n{format_exc()}")
        raise HTTPException(status_code=500, detail="Failed to create text object")

    # Build summary (for JSON responses)
    content_type_guess, _ = mimetypes.guess_type(new_object.name)
    if content_type_guess is None:
        content_type_guess = "text/plain"  # always text here

    summary = ObjectSummary(
        uuid=obj_uuid,
        name=new_object.name,
        binary=new_object.binary,  # should be False
        size=new_object.size,
        content_type=content_type_guess,
        private=new_object.private,
        created_at=new_object.created_at,
        modified_at=new_object.modified_at
    )

    # Return based on input type
    if is_form:
        return RedirectResponse(url="/objects", status_code=303)  # Back to HTML list
    else:
        return JSONResponse(content=summary.model_dump(), status_code=201)

class BinaryObjectCreate(BaseModel):
    data_base64: str
    name: Optional[str] = None
    private: bool = True

@router.post("/objects/binary", response_model=ObjectSummary)
async def create_binary_object(
    payload: BinaryObjectCreate,
    db: DbDependency,
    current_user: HttpUser = Depends(get_current_http_user)
):
    username = current_user.username

    # Decode base64
    try:
        content = base64.b64decode(payload.data_base64, validate=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid base64 encoding")

    if not content:
        raise HTTPException(status_code=400, detail="Binary content cannot be empty")

    obj_name = (payload.name or "binary_object.bin").strip()
    if len(obj_name) > 300:
        raise HTTPException(status_code=400, detail="Object name too long (max 300 chars)")
    if not obj_name:
        raise HTTPException(status_code=400, detail="Invalid object name")

    try:
        with db.transaction() as conn:
            root = conn.root()
            user = User.get_user_by_username(username, root)
            if not user:
                raise HTTPException(status_code=404, detail="User not found")

        # Pass bytes → forces binary=True
        new_object = Object(name=obj_name, data=content)
        new_object.private = payload.private

        obj_uuid = new_object.write_new(db, username=username)

        logging.info(f"User {username} created binary object {obj_uuid} ({obj_name}, {len(content)} bytes via base64)")

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Binary object creation failed for {username}: {e}\n{format_exc()}")
        raise HTTPException(status_code=500, detail="Failed to create binary object")

    # Build summary
    content_type, _ = mimetypes.guess_type(new_object.name)
    if content_type is None:
        content_type = "application/octet-stream"  # always safe for binary

    return ObjectSummary(
        uuid=obj_uuid,
        name=new_object.name,
        binary=new_object.binary,  # should be True
        size=new_object.size,
        content_type=content_type,
        private=new_object.private,
        created_at=new_object.created_at,
        modified_at=new_object.modified_at
    )

class ObjectUpdate(BaseModel):
    name: Optional[str] = None
    private: Optional[bool] = None
    data_text: Optional[str] = None      # Update to text content → forces binary=False
    data_base64: Optional[str] = None    # Update to binary content → forces binary=True

    @model_validator(mode='before')
    @classmethod
    def check_mutually_exclusive_content(cls, values: dict) -> dict:
        if values.get('data_text') is not None and values.get('data_base64') is not None:
            raise ValueError('data_text and data_base64 cannot be provided together')
        return values

@router.patch("/objects/{uuid}", response_model=ObjectSummary)
async def update_object(
    uuid: UUID,
    payload: ObjectUpdate,
    db: DbDependency,
    current_user: HttpUser = Depends(get_current_http_user)
):
    username = current_user.username

    if all(v is None for v in [payload.name, payload.private, payload.data_text, payload.data_base64]):
        raise HTTPException(status_code=400, detail="No updates provided")

    try:
        with db.transaction() as conn:
            root = conn.root()
            obj = Object.get_object_by_uuid(uuid, root)
            if not obj:
                raise HTTPException(status_code=404, detail="Object not found")

            user = User.get_user_by_username(username, root)
            if not user or user.uuid != obj.owner:
                raise HTTPException(status_code=403, detail="Not authorized to modify this object")

            updated = False

            if payload.name is not None:
                new_name = payload.name.strip()
                if len(new_name) > 300:
                    raise HTTPException(status_code=400, detail="Object name too long (max 300 chars)")
                if not new_name:
                    raise HTTPException(status_code=400, detail="Invalid object name")
                obj.name = new_name
                updated = True

            if payload.private is not None:
                obj.private = payload.private
                updated = True

            if payload.data_text is not None:
                if not payload.data_text:
                    raise HTTPException(status_code=400, detail="Text content cannot be empty")
                obj.data = payload.data_text  # str → forces binary=False, calls touch()
                updated = True

            if payload.data_base64 is not None:
                try:
                    content = base64.b64decode(payload.data_base64, validate=True)
                except Exception:
                    raise HTTPException(status_code=400, detail="Invalid base64 encoding")
                if not content:
                    raise HTTPException(status_code=400, detail="Binary content cannot be empty")
                obj.data = content  # bytes → forces binary=True, calls touch()
                updated = True

            if not updated:
                raise HTTPException(status_code=400, detail="No valid updates applied")

            logging.info(f"User {username} updated object {uuid}")

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Object update failed for {username} on {uuid}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Failed to update object")

    content_type, _ = mimetypes.guess_type(obj.name)
    if content_type is None:
        content_type = "application/octet-stream" if obj.binary else "text/plain"

    return ObjectSummary(
        uuid=obj.uuid,
        name=obj.name,
        binary=obj.binary,
        size=obj.size,
        content_type=content_type,
        private=obj.private,
        created_at=obj.created_at,
        modified_at=obj.modified_at
    )

@router.delete("/objects/{uuid}", status_code=204)
async def delete_object(
    uuid: UUID,
    db: DbDependency,
    current_user: HttpUser = Depends(get_current_http_user)
):
    username = current_user.username

    try:
        with db.transaction() as conn:
            root = conn.root()

            obj = Object.get_object_by_uuid(uuid, root)
            if not obj:
                raise HTTPException(status_code=404, detail="Object not found")

            user = User.get_user_by_username(username, root)
            if not user or user.uuid != obj.owner:
                raise HTTPException(status_code=403, detail="Not authorized to delete this object")

            # Remove references
            user.remove_obj_uuid(uuid)               # from user's object_uuids set
            del conn.root.objects[uuid]                  # from global objects mapping

            logging.info(f"User {username} deleted object {uuid}")

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Object delete failed for {username} on {uuid}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Failed to delete object")

    return None

@router.get("/objects/{uuid}/text", response_class=PlainTextResponse)
async def get_object_text(
    uuid: UUID,
    db: DbDependency,
    current_user: HttpUser = Depends(get_current_http_user)
):
    username = current_user.username

    try:
        with db.transaction() as conn:
            root = conn.root()

            obj = Object.get_object_by_uuid(uuid, root)
            if not obj:
                raise HTTPException(status_code=404, detail="Object not found")

            # Authorization check
            if obj.private:
                user = User.get_user_by_username(username, root)
                if not user or user.uuid != obj.owner:
                    raise HTTPException(status_code=403, detail="Not authorized to access this private object")

            # Only allow text objects
            if obj.binary:
                raise HTTPException(
                    status_code=400,
                    detail="This endpoint is for text objects only. Use /download or /binary for binary content."
                )

            # Safe to return as str since binary=False guarantees valid UTF-8
            content = obj.data  # will be str

            logging.info(f"User {username} downloaded text object {uuid} ({obj.name})")

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Text download failed for {username} on {uuid}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Failed to retrieve text object")

    return PlainTextResponse(content=content, media_type="text/plain; charset=utf-8")

class ObjectBinaryResponse(BaseModel):
    uuid: UUID
    name: str
    binary: bool
    size: int
    content_type: str
    data_base64: str
    private: bool
    created_at: datetime
    modified_at: datetime

@router.get("/objects/{uuid}/binary", response_model=ObjectBinaryResponse)
async def get_object_binary(
    uuid: UUID,
    db: DbDependency,
    current_user: HttpUser = Depends(get_current_http_user)
):
    username = current_user.username

    try:
        with db.transaction() as conn:
            root = conn.root()

            obj = Object.get_object_by_uuid(uuid, root)
            if not obj:
                raise HTTPException(status_code=404, detail="Object not found")

            # Authorization check for private objects
            if obj.private:
                user = User.get_user_by_username(username, root)
                if not user or user.uuid != obj.owner:
                    raise HTTPException(status_code=403, detail="Not authorized to access this private object")

            # Get content as bytes (works for both text and binary)
            content_bytes = obj.data_bytes  # uses the property that always returns bytes

            # Encode to base64
            data_base64 = base64.b64encode(content_bytes).decode('ascii')

            # Guess content_type
            content_type, _ = mimetypes.guess_type(obj.name)
            if content_type is None:
                content_type = "application/octet-stream" if obj.binary else "text/plain"

            logging.info(f"User {username} downloaded binary/base64 object {uuid} ({obj.name})")

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Binary download failed for {username} on {uuid}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Failed to retrieve object")

    return ObjectBinaryResponse(
        uuid=obj.uuid,
        name=obj.name,
        binary=obj.binary,
        size=obj.size,
        content_type=content_type,
        data_base64=data_base64,
        private=obj.private,
        created_at=obj.created_at,
        modified_at=obj.modified_at
    )

# Helper to sanitize filename for Content-Disposition
def sanitize_filename(filename: str) -> str:
    # Remove path separators and control chars
    filename = re.sub(r'[<>:"/\\|?*\x00-\x1F]', '_', filename)
    return filename or "download"

@router.get("/objects/{uuid}/download")
async def download_object(
    uuid: UUID,
    db: DbDependency,
    current_user: HttpUser = Depends(get_current_http_user),
    accept: str = Header(None)  # Optional: for future content negotiation if needed
):
    username = current_user.username

    try:
        with db.transaction() as conn:
            root = conn.root()

            obj = Object.get_object_by_uuid(uuid, root)
            if not obj:
                raise HTTPException(status_code=404, detail="Object not found")

            # Authorization check for private objects
            if obj.private:
                user = User.get_user_by_username(username, root)
                if not user or user.uuid != obj.owner:
                    raise HTTPException(status_code=403, detail="Not authorized to access this private object")

            # Get content as bytes
            content_bytes = obj.data_bytes

            # Guess content type
            content_type, _ = mimetypes.guess_type(obj.name)
            if content_type is None:
                content_type = "application/octet-stream" if obj.binary else "text/plain"

            # Sanitize filename for header
            safe_filename = sanitize_filename(obj.name)

            # Headers for download
            headers = {
                "Content-Disposition": f'attachment; filename="{safe_filename}"',
                "Content-Length": str(obj.size),
            }

            logging.info(f"User {username} downloaded object {uuid} ({obj.name}) via streaming")

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Download failed for {username} on {uuid}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Failed to stream object")

    # Stream the bytes directly (efficient, no full load in memory beyond ZODB)
    return StreamingResponse(
        iter([content_bytes]),  # single chunk since ZODB objects are usually small-ish
        media_type=content_type,
        headers=headers
    )

@router.get("/objects/{uuid}", response_model=ObjectSummary)
async def get_object_metadata(
    uuid: UUID,
    db: DbDependency,
    current_user: HttpUser = Depends(get_current_http_user)
):
    username = current_user.username

    try:
        with db.transaction() as conn:
            root = conn.root()

            obj = Object.get_object_by_uuid(uuid, root)
            if not obj:
                raise HTTPException(status_code=404, detail="Object not found")

            # Authorization: private objects only visible to owner
            if obj.private:
                user = User.get_user_by_username(username, root)
                if not user or user.uuid != obj.owner:
                    raise HTTPException(status_code=403, detail="Not authorized to view this private object")

            # Guess content_type for summary
            content_type, _ = mimetypes.guess_type(obj.name)
            if content_type is None:
                content_type = "application/octet-stream" if obj.binary else "text/plain"

            logging.info(f"User {username} retrieved metadata for object {uuid} ({obj.name})")

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Metadata retrieval failed for {username} on {uuid}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Failed to retrieve object metadata")

    return ObjectSummary(
        uuid=obj.uuid,
        name=obj.name,
        binary=obj.binary,
        size=obj.size,
        content_type=content_type,
        private=obj.private,
        created_at=obj.created_at,
        modified_at=obj.modified_at
    )