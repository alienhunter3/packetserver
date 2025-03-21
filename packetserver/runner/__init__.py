"""Package runs arbitrary commands/jobs via different mechanisms."""
from typing import Union,Optional,Iterable,Self
from enum import Enum
import datetime
from uuid import UUID, uuid4
from threading import Lock
import os.path
from packetserver.runner.constants import job_setup_script, job_end_script, container_setup_script, container_run_script
from packetserver.common.util import multi_bytes_to_tar_bytes, bytes_to_tar_bytes, TarFileExtractor


def scripts_tar() -> bytes:
    return multi_bytes_to_tar_bytes({
        'job_setup_script.sh': job_setup_script.encode(),
        'job_end_script.sh': job_end_script.encode(),
        'container_run_script.sh': container_run_script.encode(),
        'container_setup_script.sh': container_setup_script.encode()
    })

class RunnerFile:
    def __init__(self, destination_path: str, source_path: str = None, data: bytes = b'', root_owned: bool = False):
        self._data = data
        self._source_path = ""

        if source_path is not None:
            if source_path.strip() != "":
                if not os.path.isfile(source_path.strip()):
                    raise ValueError("Source Path must point to a file.")
                self._source_path = source_path.strip()

        self.destination_path = destination_path.strip()
        if self.destination_path == "":
            raise ValueError("Destination path cannot be empty.")

        self.root_owned = root_owned

    def __repr__(self):
        return f"<RunnerFile: {self.basename}>"

    @property
    def basename(self) -> str:
        return os.path.basename(self.destination_path)

    @property
    def dirname(self) -> str:
        return os.path.dirname(self.destination_path)

    @property
    def isabs(self) -> bool:
        return os.path.isabs(self.destination_path)

    @property
    def data(self) -> bytes:
            if self._source_path == "":
                return self._data
            else:
                return open(self._source_path, "rb").read()

    def tar_data(self) -> bytes:
        return bytes_to_tar_bytes(self.basename, self.data)

class RunnerStatus(Enum):
    CREATED = 1
    QUEUED = 2
    STARTING = 3
    RUNNING = 4
    STOPPING = 5
    SUCCESSFUL = 6
    FAILED = 7
    TIMED_OUT = 8

class Runner:
    """Abstract class to take arguments and run a job and track the status and results."""
    def __init__(self, username: str, args: Union[str, list[str]], job_id: int, environment: Optional[dict] = None,
                 timeout_secs: str = 300, labels: Optional[list] = None,
                 files: list[RunnerFile] = None):
        self.files = []
        if files is not None:
            for f in files:
                self.files.append(f)
        self.status = RunnerStatus.CREATED
        self.username = username.strip().lower()
        self.args = args
        self.job_id = int(job_id)
        self.env = {}
        self.started_at = datetime.datetime.now(datetime.UTC)
        self.finished_at = None
        self._result = (0,(b'', b''))
        self._artifact_archive = b''
        if environment:
            for key in environment:
                self.env[key] = environment[key]
        self.labels = []
        if type(labels) is list:
            for l in labels:
                self.labels.append(l)

        self.timeout_seconds = timeout_secs
        self.created_at = datetime.datetime.now(datetime.UTC)

    def __repr__(self):
        return f"<{type(self).__name__}: {self.username}[{self.job_id}] - {self.status.name}>"

    def is_finished(self) -> bool:
        if self.status in [RunnerStatus.TIMED_OUT, RunnerStatus.SUCCESSFUL, RunnerStatus.FAILED]:
            return True
        return False

    def is_in_process(self) -> bool:
        if self.status in [RunnerStatus.QUEUED, RunnerStatus.RUNNING, RunnerStatus.STARTING, RunnerStatus.STOPPING]:
            return True
        return False

    def start(self):
        self.started = datetime.datetime.now()

    def stop(self):
        raise RuntimeError("Attempting to stop an abstract class.")

    @property
    def output(self) -> bytes:
        raise RuntimeError("Attempting to interact with an abstract class.")

    def output_str(self) -> str:
        raise RuntimeError("Attempting to interact with an abstract class.")

    @property
    def errors(self) -> bytes:
        raise RuntimeError("Attempting to interact with an abstract class.")

    @property
    def errors_str(self) -> str:
        raise RuntimeError("Attempting to interact with an abstract class.")

    @property
    def return_code(self) -> Optional[int]:
        raise RuntimeError("Attempting to interact with an abstract class.")

    @property
    def artifacts(self) -> TarFileExtractor:
        raise RuntimeError("Attempting to interact with an abstract class.")

    @property
    def has_artifacts(self) -> bool:
        raise RuntimeError("Abstract method called.")

class Orchestrator:
    """Abstract class holds configuration and also tracks runners through their lifecycle. Prepares environments to
    run jobs in runners."""
    def __init__(self):
        self.runners = []
        self.runner_lock = Lock()

    def get_finished_runners(self) -> list[Runner]:
        return [r for r in self.runners if r.is_finished()]

    def remove_runner(self, job_id: int):
        runner_object = None
        for r in self.runners:
            if r.job_id == job_id:
                runner_object = r
                break

        if runner_object is not None:
            self.runners.remove(runner_object)

    def get_runner_by_id(self, job_id: int) -> Optional[Runner]:
        for r in self.runners:
            if r.job_id == job_id:
                return r

    def runners_available(self) -> bool:
        """Abstract. True if a runner can be started. False, if queue is full or orchestrator not ready."""
        pass

    def new_runner(self, username: str, args: Iterable[str], job_id: int, environment: Optional[dict] = None,
                 timeout_secs: str = 300, refresh_db: bool = True, labels: Optional[list] = None,
                   files: list[RunnerFile] = None) -> Runner:
        pass

    def manage_lifecycle(self):
        """When called, updates runner statuses and performs any housekeeping."""
        pass

    def start(self):
        """Do any setup and then be ready to operate"""
        pass

    def stop(self):
        """Do any cleanup needed."""
        pass