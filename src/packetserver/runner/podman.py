"""Uses podman to run jobs in containers."""
from . import Runner, Orchestrator
from collections import namedtuple
from typing import Optional
import subprocess
import podman
import os
import os.path
import logging
import ZODB

PodmanOptions = namedtuple("PodmanOptions", ["default_timeout", "max_timeout", "image_name",
                                             "max_active_jobs", "container_keepalive", "name_prefix"])

class PodmanRunner(Runner):
    def __init__(self, username):
        pass

class PodmanOrchestrator(Orchestrator):
    def __init__(self, uri: Optional[str] = None, options: Optional[PodmanOptions] = None):
        super().__init__()
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
