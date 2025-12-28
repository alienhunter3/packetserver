from fastapi import APIRouter, Depends, HTTPException, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from typing import List, Optional, Union, Tuple, Dict, Any
from pydantic import BaseModel
from datetime import datetime
import logging
import base64
from traceback import format_exc

from packetserver.http.dependencies import get_current_http_user
from packetserver.http.auth import HttpUser
from packetserver.http.database import DbDependency
from packetserver.server.jobs import Job, JobStatus
from packetserver.http.server import templates
from packetserver.runner import RunnerFile

router = APIRouter(prefix="/api/v1", tags=["jobs"])
dashboard_router = APIRouter(tags=["jobs"])

class JobSummary(BaseModel):
    id: int
    cmd: Union[str, List[str]]
    owner: str
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    status: str  # JobStatus.name
    return_code: int
    env: Dict[str, str] = {}

class JobDetail(JobSummary):
    output: str  # base64-encoded
    errors: str  # base64-encoded
    artifacts: List[Tuple[str, str]]  # list of (filename, base64_data)
    env: Dict[str, str] = {}

from typing import Dict

class JobCreate(BaseModel):
    cmd: Union[str, List[str]]
    env: Optional[Dict[str, str]] = None
    files: Optional[Dict[str, str]] = None

@router.get("/jobs", response_model=List[JobSummary])
async def list_user_jobs(
    db: DbDependency,
    current_user: HttpUser = Depends(get_current_http_user)
):
    username = current_user.username.upper().strip()

    try:
        with db.transaction() as conn:
            root = conn.root()
            user_jobs = Job.get_jobs_by_username(username, root)

            # Sort newest first
            user_jobs.sort(key=lambda j: j.created_at, reverse=True)

            summaries = []
            for j in user_jobs:
                summaries.append(JobSummary(
                    id=j.id,
                    cmd=j.cmd,
                    owner=j.owner,
                    created_at=j.created_at,
                    started_at=j.started_at,
                    finished_at=j.finished_at,
                    status=j.status.name,
                    return_code=j.return_code,
                    env=j.env
                ))

    except Exception as e:
        logging.error(f"Job list failed for {username}: {e}\n{format_exc()}")
        raise HTTPException(status_code=500, detail="Failed to list jobs")

    return summaries

@router.get("/jobs/{jid}", response_model=JobDetail)
async def get_job_detail(
    jid: int,
    db: DbDependency,
    current_user: HttpUser = Depends(get_current_http_user)
):
    username = current_user.username.upper().strip()

    try:
        with db.transaction() as conn:
            root = conn.root()
            job = Job.get_job_by_id(jid, root)
            if not job:
                raise HTTPException(status_code=404, detail="Job not found")

            if job.owner != username:
                raise HTTPException(status_code=403, detail="Not authorized to view this job")

            job_dict = job.to_dict(include_data=True, binary_safe=True)

            return JobDetail(
                id=job.id,
                cmd=job.cmd,
                owner=job.owner,
                created_at=job.created_at,
                started_at=job.started_at,
                finished_at=job.finished_at,
                status=job.status.name,
                return_code=job.return_code,
                output=job_dict["output"],
                errors=job_dict["errors"],
                artifacts=job_dict["artifacts"],
                env=job_dict.get("env", {})
            )

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Job detail failed for {username} on {jid}: {e}\n{format_exc()}")
        raise HTTPException(status_code=500, detail="Failed to retrieve job")

    return summaries

@dashboard_router.get("/jobs", response_class=HTMLResponse)
async def jobs_list_page(
    request: Request,
    db: DbDependency,
    current_user: HttpUser = Depends(get_current_http_user)
):
    jobs = await list_user_jobs(db=db, current_user=current_user)

    return templates.TemplateResponse(
        "jobs.html",
        {
            "request": request,
            "current_user": current_user.username,
            "jobs": jobs
        }
    )

@dashboard_router.get("/jobs/new", response_class=HTMLResponse)
async def new_job_form(
    request: Request,
    current_user: HttpUser = Depends(get_current_http_user)
):
    return templates.TemplateResponse(
        "job_new.html",
        {
            "request": request,
            "current_user": current_user.username
        }
    )

@dashboard_router.post("/jobs/new")
async def create_job_from_form(
    db: DbDependency,
    request: Request,
    cmd: str = Form(...),
    env_keys: List[str] = Form(default=[]),
    env_values: List[str] = Form(default=[]),
    files: List[UploadFile] = File(default=[]),
    current_user: HttpUser = Depends(get_current_http_user)
):
    # Build env dict from parallel lists
    env = {}
    for k, v in zip(env_keys, env_values):
        if k.strip():
            env[k.strip()] = v.strip()

    # Build files dict for API (filename → base64)
    files_dict = {}
    for upload in files:
        if upload.filename:
            content = await upload.read()
            files_dict[upload.filename] = base64.b64encode(content).decode('ascii')

    # Prepare payload for the existing API
    payload = {
        "cmd": [part.strip() for part in cmd.split() if part.strip()],  # split on whitespace, like shell
        "env": env if env else None,
        "files": files_dict if files_dict else None
    }

    # Call the API internally
    from packetserver.http.routers.jobs import create_job as api_create_job
    response = await api_create_job(
        payload=JobCreate(**{k: v for k, v in payload.items() if v is not None}),
        db=db,
        current_user=current_user
    )

    # Redirect to the new job detail page
    return RedirectResponse(url=f"/jobs/{response.id}", status_code=303)

@dashboard_router.get("/jobs/{jid}", response_class=HTMLResponse)
async def job_detail_page(
    request: Request,
    jid: int,
    db: DbDependency,
    current_user: HttpUser = Depends(get_current_http_user)
):
    job = await get_job_detail(jid=jid, db=db, current_user=current_user)

    return templates.TemplateResponse(
        "job_detail.html",
        {
            "request": request,
            "current_user": current_user.username,
            "job": job
        }
    )

@router.post("/jobs", response_model=JobSummary, status_code=201)
async def create_job(
    payload: JobCreate,
    db: DbDependency,
    current_user: HttpUser = Depends(get_current_http_user)
):
    username = current_user.username.upper().strip()

    try:
        # Process files: convert base64 dict to list of RunnerFile
        runner_files = []
        if payload.files:
            for filename, b64_data in payload.files.items():
                try:
                    data_bytes = base64.b64decode(b64_data)
                    runner_files.append(RunnerFile(filename, data=data_bytes))
                except Exception as e:
                    raise HTTPException(status_code=400, detail=f"Invalid base64 for file {filename}")

        # Create the Job instance
        new_job = Job(
            cmd=payload.cmd,
            owner=username,
            env=payload.env or {},
            files=runner_files
        )

        with db.transaction() as conn:
            root = conn.root()
            new_jid = new_job.queue(root)

            logging.info(f"User {username} queued job {new_jid}: {payload.cmd} with {len(runner_files)} files")

        return JobSummary(
            id=new_jid,
            cmd=new_job.cmd,
            owner=new_job.owner,
            created_at=new_job.created_at,
            started_at=new_job.started_at,
            finished_at=new_job.finished_at,
            status=new_job.status.name,
            return_code=new_job.return_code
        )

    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Job creation failed for {username}: {e}\n{format_exc()}")
        raise HTTPException(status_code=500, detail="Failed to queue job")

