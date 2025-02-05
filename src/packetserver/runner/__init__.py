"""Package runs arbitrary commands/jobs via different mechanisms."""
from typing import Union,Optional,Iterable,Self
from enum import Enum
import datetime
from uuid import UUID, uuid4
from threading import Lock

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
    def __init__(self, username: str, args: Iterable[str], job_id: int, environment: Optional[dict] = None,
                 timeout_secs: str = 300, refresh_db: bool = True, labels: Optional[list] = None):
        self.status = RunnerStatus.CREATED
        self.username = username.strip().lower()
        self.args = args
        self.env = {}
        self.started = datetime.datetime.now()
        if environment:
            for key in environment:
                self.env[key] = environment[key]
        self.labels = []
        for l in labels:
            self.labels.append(l)

        self.timeout_seconds = timeout_secs
        self.refresh_db = refresh_db
        self.created_at = datetime.datetime.now(datetime.UTC)

    def is_finished(self):
        if self.status in [RunnerStatus.TIMED_OUT, RunnerStatus.SUCCESSFUL, RunnerStatus.FAILED]:
            return True
        return False

    def start(self):
        self.started = datetime.datetime.now()

    def stop(self):
        raise RuntimeError("Attempting to stop an abstract class.")

    def heartbeat(self):
        """Does any housekeeping while the underlying task is running. When the task is finished,
        update status and do any cleanup activities."""
        pass

    @property
    def output(self) -> str:
        raise RuntimeError("Attempting to interact with an abstract class.")

    @property
    def errors(self) -> str:
        raise RuntimeError("Attempting to interact with an abstract class.")

    @property
    def return_code(self) -> Optional[int]:
        raise RuntimeError("Attempting to interact with an abstract class.")

    @property
    def artifacts(self) -> list:
        raise RuntimeError("Attempting to interact with an abstract class.")

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
                 timeout_secs: str = 300, refresh_db: bool = True, labels: Optional[list] = None) -> Runner:
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