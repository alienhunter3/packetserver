# packetserver/http/routers/public.py
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["public"])


@router.get("/", response_class=HTMLResponse)
async def root(request: Request):
    from packetserver.http.server import templates
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "message": "Welcome to PacketServer HTTP Interface"}
    )


@router.get("/health")
async def health():
    return {"status": "ok", "service": "packetserver-http"}