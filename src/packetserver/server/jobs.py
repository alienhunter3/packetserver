import re

import ax25
import persistent
import persistent.list
from persistent.mapping import PersistentMapping
import datetime
from typing import Self,Union,Optional,Tuple
from traceback import format_exc
from packetserver.common import PacketServerConnection, Request, Response, Message, send_response, send_blank_response
from packetserver.common.constants import no_values, yes_values
from packetserver.server.db import get_user_db_json
import ZODB
from persistent.list import PersistentList
import logging
from packetserver.server.users import user_authorized
import gzip
import tarfile
import time
import json
from packetserver.runner.podman import TarFileExtractor, PodmanOrchestrator, PodmanRunner, PodmanOptions
from packetserver.runner import Orchestrator, Runner, RunnerStatus, RunnerFile
from enum import Enum
from io import BytesIO
import base64

class JobStatus(Enum):
    CREATED = 1
    QUEUED = 2
    STARTING = 3
    RUNNING = 4
    STOPPING = 5
    SUCCESSFUL = 6
    FAILED = 7
    TIMED_OUT = 8

def get_orchestrator_from_config(cfg: dict) -> Union[Orchestrator, PodmanOrchestrator]:
    if 'runner' in cfg:
        val = cfg['runner'].lower().strip()
        if val == "podman":
            image = cfg.get('image', 'debian')
            opts = PodmanOptions(default_timeout=300, max_timeout=3600, image_name=image, max_active_jobs=5,
                                  container_keepalive=300, name_prefix="packetserver_")
            orch = PodmanOrchestrator(options=opts)
            return orch
        else:
            raise RuntimeError("Other orchestrators not implemented yet.")
    else:
        raise RuntimeError("Runners not configured in root.config.jobs_config")

def get_new_job_id(root: PersistentMapping) -> int:
    if 'job_counter' not in root:
        root['job_counter'] = 1
        return 0
    else:
        current = root['job_counter']
        root['job_counter'] = current + 1
        return current

class Job(persistent.Persistent):
    @classmethod
    def update_job_from_runner(cls, runner: Runner, db_root: PersistentMapping) -> True:
        job = Job.get_job_by_id(runner.job_id, db_root)
        if job is None:
            logging.warning(f"Couldn't match runner {runner} with a job by id.")
            return False
        if not runner.is_finished():
            return False
        job.finished_at = datetime.datetime.now()
        job.output = runner.output
        job.errors = runner.errors
        job.return_code = runner.return_code
        job._artifact_archive = runner._artifact_archive
        if runner.status == RunnerStatus.SUCCESSFUL:
            job.status = JobStatus.SUCCESSFUL
        else:
            job.status = JobStatus.FAILED
        return True

    @classmethod
    def get_job_by_id(cls, jid: int, db_root: PersistentMapping) -> Optional[Self]:
        if jid in db_root['jobs']:
            return db_root['jobs'][jid]
        return None

    @classmethod
    def get_jobs_by_username(cls, username:str, db_root: PersistentMapping) -> list[Self]:
        un = username.strip().upper()
        if un in db_root['user_jobs']:
            l = []
            for j in db_root['user_jobs'][un]:
                l.append(Job.get_job_by_id(j, db_root))
            return l
        else:
            return []

    @classmethod
    def num_jobs_queued(cls, db_root: PersistentMapping) -> int:
        return len(db_root['job_queue'])

    @classmethod
    def jobs_in_queue(cls, db_root: PersistentMapping) -> bool:
        if Job.num_jobs_queued(db_root) > 0:
            return True
        else:
            return False

    @classmethod
    def get_next_queued_job(cls, db_root: PersistentMapping) -> Self:
        return db_root['job_queue'][0]

    def __init__(self, cmd: Union[list[str], str], owner: Optional[str] = None, timeout: int = 300,
                 env: dict = None, files: list[RunnerFile] = None):
        self.owner = None
        if owner is not None:
            self.owner = str(owner).upper().strip()
        self.cmd = cmd
        self.env = {}
        if env is not None:
            for key in env:
                self.env[key] = env[key]
        self.files = []
        if files is not None:
            self.files = files
        self.created_at = datetime.datetime.now(datetime.UTC)
        self.started_at = None
        self.finished_at = None
        self._artifact_archive = b''
        self.output = b''
        self.errors = b''
        self.return_code = 0
        self.id = None
        self.status = JobStatus.CREATED

    @property
    def is_finished(self) -> bool:
        if self.finished_at is None:
            return False
        else:
            return True

    @property
    def output_str(self) -> str:
        return self.output.decode()

    @property
    def errors_str(self) -> str:
        return self.errors.decode()

    @property
    def artifacts(self) -> TarFileExtractor:
        if self._artifact_archive == b'':
            return TarFileExtractor(BytesIO(b''))
        else:
            return TarFileExtractor(gzip.GzipFile(fileobj=BytesIO(self._artifact_archive)))

    @property
    def num_artifacts(self) -> int:
        return len(list(self.artifacts))

    def __repr__(self) -> str:
        return f"<Job[{self.id}] - {self.owner} - {self.status.name}>"

    def artifact(self, index: int) -> Tuple[str, bytes]:
        artifacts = list(self.artifacts)
        if (index + 1) > len(artifacts):
            raise IndexError(f"Index {index} out of bounds.")
        else:
            return artifacts[index][0], artifacts[index][1].read()

    def queue(self, db_root: PersistentMapping) -> int:
        logging.debug(f"Attempting to queue job {self}")
        if self.owner is None or (str(self.owner).strip() == ""):
            raise ValueError("Job must have an owner to be queued.")

        if self.id is None:
            self.id = get_new_job_id(db_root)
            owner = self.owner.upper().strip()
            if owner not in db_root['user_jobs']:
                db_root['user_jobs'][owner] = PersistentList()
            db_root['user_jobs'][owner].append(self.id)
            db_root['jobs'][self.id] = self
            db_root['job_queue'].append(self.id)
        return self.id

    def to_dict(self, include_data: bool = True, binary_safe: bool = False):
        started_at = None
        finished_at = None
        if self.started_at is not None:
            started_at = self.started_at.isoformat()
        if self.finished_at is not None:
            finished_at = self.finished_at.isoformat()
        output = {
            "cmd": self.cmd,
            "owner": self.owner,
            "created_at": self.created_at.isoformat(),
            "started_at": started_at,
            "finished_at": finished_at,
            "output": b'',
            "errors": b'',
            "return_code": self.return_code,
            "artifacts": [],
            "status": self.status.name,
            "id": self.id
        }
        if include_data:
            if binary_safe:
                output['output'] = base64.b64encode(self.output).decode()
                output['errors'] = base64.b64encode(self.errors).decode()
            else:
                output['output'] = self.output
                output['errors'] = self.errors

            for a in self.artifacts:
                if binary_safe:
                    output['artifacts'].append((a[0], base64.b64encode(a[1].read()).decode()))
                else:
                    output['artifacts'].append((a[0], a[1].read()))
        return output

    def json(self, include_data: bool = True) -> str:
        return json.dumps(self.to_dict(include_data=include_data, binary_safe=True))

def handle_job_get_id(req: Request, conn: PacketServerConnection, db: ZODB.DB, jid: int):
    username = ax25.Address(conn.remote_callsign).call.upper().strip()
    value = "y"
    include_data = True
    for key in req.vars:
        if key.lower().strip() == "data":
            value = req.vars[key].lower().strip()
    if value in no_values:
        include_data = False

    with db.transaction() as storage:
        try:
            job = Job.get_job_by_id(jid, storage.root())
            if job is None:
                send_blank_response(conn, req, 404)
                return
            if job.owner != username:
                send_blank_response(conn, req, 401)
                return
            send_blank_response(conn, req, 200, job.to_dict(include_data=include_data))
            return
        except:
            logging.error(f"Error looking up job {jid}:\n{format_exc()}")
            send_blank_response(conn, req, 500, payload="unknown server error")

def handle_job_get_user(req: Request, conn: PacketServerConnection, db: ZODB.DB):
    username = ax25.Address(conn.remote_callsign).call.upper().strip()
    jobs = []
    value = "y"
    include_data = True
    for key in req.vars:
        if key.lower().strip() == "data":
            value = req.vars[key].lower().strip()
    if value in no_values:
        include_data = False
    id_only = False
    if 'id_only' in req.vars:
        if req.vars['id_only'] in yes_values:
            id_only = True
    with db.transaction() as storage:
        for jid in storage.root()['user_jobs'][username]:
            jobs.append(Job.get_job_by_id(jid, storage.root()).to_dict(include_data=include_data))

    if id_only:
        send_blank_response(conn, req, status_code=200, payload=[x['id'] for x in jobs])
    else:
        send_blank_response(conn, req, status_code=200, payload=jobs)

def handle_job_get(req: Request, conn: PacketServerConnection, db: ZODB.DB):
    spl = [x for x in req.path.split("/") if x.strip() != ""]
    if (len(spl) == 2) and (spl[1].isdigit()):
        handle_job_get_id(req, conn, db, int(spl[1]))
    elif (len(spl) == 2) and (spl[1].lower() == "user"):
        handle_job_get_user(req, conn, db)
    else:
        send_blank_response(conn, req, status_code=404)

def handle_new_job_post(req: Request, conn: PacketServerConnection, db: ZODB.DB):
    username = ax25.Address(conn.remote_callsign).call.upper().strip()
    quick = False
    if 'quick' in req.vars:
        quick_val = req.vars['quick']
        if type(quick_val) is str:
            quick_val = quick_val.lower()
        if quick_val in yes_values:
            quick = True
    if 'cmd' not in req.payload:
        logging.info(f"request {req} did not contain job command (cmd) key")
        send_blank_response(conn, req, 401, "job post must contain cmd key containing str or list[str]")
        return
    if type(req.payload['cmd']) not in [str, list]:
        send_blank_response(conn, req, 401, "job post must contain cmd key containing str or list[str]")
        return
    files = []
    if 'db' in req.payload:
        logging.debug(f"Fetching a user db as requested.")
        dbf = RunnerFile('user-db.json.gz', data=get_user_db_json(username.lower(), db))
        files.append(dbf)
    if 'files' in req.payload:
        if type(files) is dict:
            for key in req.payload['files']:
                val = req.payload['files'][key]
                if type(val) is bytes:
                    files.append(RunnerFile(key, data=val))
    env = {}
    if 'env' in req.payload:
        if type(req.payload['env']) is dict:
            for key in req.payload['env']:
                env[key] = req.payload['env'][key]
    job = Job(req.payload['cmd'], owner=username, env=env, files=files)
    with db.transaction() as storage:
        try:
            new_jid = job.queue(storage.root())
            logging.info(f"New job created with id {new_jid}")
        except:
            logging.error(f"Failed to queue new job {job}:\n{format_exc()}")
            send_blank_response(conn, req, 500, "unknown server error while queuing job")
            return
    if quick:
        start_time = datetime.datetime.now()
        now = datetime.datetime.now()
        job_done = False
        quick_job = None
        logging.debug(f"{start_time}: Waiting for a quick job for 30 seconds")
        while (now - start_time).total_seconds() < 30:
            with db.transaction() as storage:
                try:
                    j = Job.get_job_by_id(new_jid, storage.root())
                    if j.is_finished:
                        job_done = True
                        quick_job = j
                        break
                except:
                    pass
            time.sleep(1)
            now = datetime.datetime.now()
        if job_done and (type(quick_job) is Job):
            send_blank_response(conn, req, 200, job.to_dict(include_data=True))
        else:
            logging.warning(f"Quick job {new_jid} timed out.")
            send_blank_response(conn, req, status_code=202, payload={'job_id': new_jid, 'msg': 'queued'})
    else:
        send_blank_response(conn, req, 201, {'job_id': new_jid})

def handle_job_post(req: Request, conn: PacketServerConnection, db: ZODB.DB):
    spl = [x for x in req.path.split("/") if x.strip() != ""]

    if len(spl) == 1:
        handle_new_job_post(req, conn, db)
    else:
        send_blank_response(conn, req, status_code=404)

def job_root_handler(req: Request, conn: PacketServerConnection, db: ZODB.DB):
    logging.debug(f"{req} being processed by job_root_handler")
    if not user_authorized(conn, db):
        logging.debug(f"user {conn.remote_callsign} not authorized")
        send_blank_response(conn, req, status_code=401)
        return
    logging.debug("user is authorized")
    with db.transaction() as storage:
        if 'jobs_enabled' in storage.root.config:
            jobs_enabled = storage.root.config['jobs_enabled']
        else:
            jobs_enabled = False
    if not jobs_enabled:
        send_blank_response(conn, req, 400, payload="jobs not enabled on this server")
        return
    if req.method is Request.Method.GET:
        handle_job_get(req, conn, db)
    elif req.method is Request.Method.POST:
        handle_job_post(req, conn, db)
    else:
        send_blank_response(conn, req, status_code=404)