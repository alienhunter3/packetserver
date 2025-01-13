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

class Runner:
    """Abstract class to take arguments and run a job and track the status and results."""
    def __init__(self, username: str, args: Iterable[str], job_id: int, environment: Optional[dict] = None,
                 timeout_secs: str = 300, refresh_db: bool = True, labels: Optional[list] = None):
        self.status = RunnerStatus.CREATED
        self.username = username.strip().lower()
        self.args = args
        self.env = {}
        if environment:
            for key in environment:
                self.env[key] = environment[key]
        self.labels = []
        for l in labels:
            self.labels.append(l)

        self.timeout_seconds = timeout_secs
        self.refresh_db = refresh_db
        self.created_at = datetime.datetime.now(datetime.UTC)

    def start(self):
        raise RuntimeError("Attempting to start an abstract class.")

    def stop(self):
        raise RuntimeError("Attempting to stop an abstract class.")

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

    def new_runner(self, username: str, args: Iterable[str], job_id: int, environment: Optional[dict] = None,
                 timeout_secs: str = 300, refresh_db: bool = True, labels: Optional[list] = None) -> Runner:
        pass

    def manage_lifecycle(self):
        """When called, starts any pending runners if queue allows, looks for finished runners and updates statuses."""
        pass