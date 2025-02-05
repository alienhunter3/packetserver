"""Uses podman to run jobs in containers."""
from . import Runner, Orchestrator, RunnerStatus
from collections import namedtuple
from typing import Optional, Iterable
import subprocess
import podman
import os
import os.path
import logging
import ZODB
import datetime

PodmanOptions = namedtuple("PodmanOptions", ["default_timeout", "max_timeout", "image_name",
                                             "max_active_jobs", "container_keepalive", "name_prefix"])

class PodmanRunner(Runner):
    def __init__(self, username):
        pass

    def start(self):
        super().start()

    def heartbeat(self):
        pass

class PodmanOrchestrator(Orchestrator):
    def __init__(self, uri: Optional[str] = None, options: Optional[PodmanOptions] = None):
        super().__init__()
        self.started = False
        self.user_containers = {}
        if uri:
            self.uri = uri
        else:
            self.uri = f"unix:///run/user/{os.getuid()}/podman/podman.sock"

        if not os.path.exists(self.uri):
            raise FileNotFoundError(f"Podman socket not found: {self.uri}")

        logging.debug(f"Testing podman socket. Version: {self.client.version()}")

        self.username_containers = {}
        if options:
            self.opts = options
        else:
            self.opts = PodmanOptions(default_timeout=300, max_timeout=3600, image_name="debian", max_active_jobs=5,
                                  container_keepalive=300, name_prefix="packetserver_")

    @property
    def client(self):
        return podman.PodmanClient(base_url=self.uri)

    def refresh_user_db(self, username: str, db: ZODB.DB):
        pass

    def podman_start_user_container(self, username: str):
        pass

    def podman_stop_user_container

    def podman_container_exists(self, container_name: str) -> bool:
        return False

    def clean_orphaned_containers(self):
        pass

    def get_container_name(self, username: str) -> str:
        return self.opts.name_prefix + username.lower().strip()

    def touch_user_container(self, username: str):
        self.user_containers[self.get_container_name(username)] = datetime.datetime.now()

    def start_user_container(self, username: str):
        if not self.podman_container_exists(self.get_container_name(username)):
            self.podman_start_user_container(username)
        self.touch_user_container(username)

    def clean_containers(self):
        """Checks running containers and stops them if they have been running too long."""
        for c in self.user_containers:
            if (datetime.datetime.now() - self.user_containers[c]) > self.opts.container_keepalive:
                # stop the container TODO
                del self.user_containers[c]

    def runners_in_process(self) -> int:
        count = 0
        for r in self.runners:
            if not r.is_finished():
                count = count + 1
        return count

    def runners_available(self) -> bool:
        if not self.started:
            return False

        if self.runners_in_process() < self.opts.max_active_jobs:
            return True

        return False

    def new_runner(self, username: str, args: Iterable[str], job_id: int, environment: Optional[dict] = None,
                 timeout_secs: str = 300, refresh_db: bool = True, labels: Optional[list] = None) -> Optional[Runner]:
        with self.runner_lock:
            if not self.runners_available():
                return None
            pass

    def manage_lifecycle(self):
        with self.runner_lock:
            for r in self.runners:
                if r.status is RunnerStatus.RUNNING:
                    r.heartbeat()
                if not r.is_finished():
                    self.touch_user_container(r.username)
            self.clean_containers()
            self.clean_orphaned_containers()

    def start(self):
        self.started = True

    def stop(self):
        self.started = False