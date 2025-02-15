import ax25
import persistent
import persistent.list
from persistent.mapping import PersistentMapping
import datetime
from typing import Self,Union,Optional,Tuple
from packetserver.common import PacketServerConnection, Request, Response, Message, send_response, send_blank_response
import ZODB
from persistent.list import PersistentList
import logging
from packetserver.server.users import user_authorized
import gzip
import tarfile
import json
from packetserver.runner.podman import TarFileExtractor
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

    def __init__(self, cmd: Union[list[str], str], owner: Optional[str] = None, timeout: int = 300):
        self.owner = None
        if self.owner is not None:
            self.owner = str(owner).upper().strip()
        self.cmd = cmd
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
        if self.owner is None or (str(self.owner).strip() == ""):
            raise ValueError("Job must have an owner to be queued.")
        if self.id is None:
            self.id = get_new_job_id(db_root)
            owner = self.owner.upper().strip()
            if owner not in db_root['user_jobs']:
                db_root['user_jobs'][owner] = PersistentList()
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
            "status": self.status,
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
