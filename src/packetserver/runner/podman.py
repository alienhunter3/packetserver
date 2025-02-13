"""Uses podman to run jobs in containers."""
import time

from . import Runner, Orchestrator, RunnerStatus, RunnerFile, scripts_tar
from collections import namedtuple
from typing import Optional, Iterable
import subprocess
import podman
import podman.errors
import os
import os.path
import logging
import ZODB
import datetime
from os.path import basename, dirname
from packetserver.common.util import bytes_to_tar_bytes, random_string
from packetserver import VERSION as packetserver_version
import re
from threading import Thread

env_splitter_rex = '''([a-zA-Z0-9]+)=([a-zA-Z0-9]*)'''

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
        self.manager_thread = None
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

    def add_file_to_user_container(self, username: str, data: bytes, path: str):
        pass

    def get_file_from_user_container(self, username: str, path: str) -> bytes :
        pass

    def podman_container_env(self, container_name: str) -> dict:
        cli = self.client
        logging.debug(f"Attempting to remove container named {container_name}")
        try:
            con = cli.containers.get(container_name)
            splitter = re.compile(env_splitter_rex)
            env = {}
            for i in con.inspect()['Config']['Env']:
                m = splitter.match(i)
                if m:
                    env[m.groups()[0]] = m.groups()[1]
            return env
        except podman.errors.exceptions.NotFound as e:
            return

    def podman_container_version(self, container_name: str) -> str:
        try:
            env = self.podman_container_env(container_name)
        except:
            env = {}
        return env.get("PACKETSERVER_VERSION", "0.0.0")

    def podman_user_container_env(self, username: str) -> dict:
        container_name = self.get_container_name(username)
        return self.podman_container_env(container_name)

    def podman_user_container_version(self, username: str) -> str:
        container_name = self.get_container_name(username)
        return self.podman_container_version(container_name)

    def podman_start_user_container(self, username: str):
        container_env = {
            "PACKETSERVER_VERSION": packetserver_version,
            "PACKETSERVER_USER": username.strip().lower()
        }
        con = self.client.containers.create(self.opts.image_name, name=self.get_container_name(username),
                                            command=["tail", "-f", "/dev/null"])
        con.start()
        started_at = datetime.datetime.now()
        while con.inspect()['State']['Status'] not in ['exited', 'running']:
            now = datetime.datetime.now()
            if (now - started_at).total_seconds() > 300:
                con.stop()
                con.remove()
                raise RuntimeError(f"Couldn't start container for user {username}")
            time.sleep(.1)
        time.sleep(.5)
        if con.inspect()['State']['Status'] != 'running':
            con.stop()
            con.remove()
            raise RuntimeError(f"Couldn't start container for user {username}")
        self.touch_user_container(username)

    def podman_remove_container_name(self, container_name: str):
        cli = self.client
        logging.debug(f"Attempting to remove container named {container_name}")
        try:
            con = cli.containers.get(container_name)
        except podman.errors.exceptions.NotFound as e:
            return
        try:
            con.rename(f"{container_name}_{random_string()}")
        except:
            pass
        if con.inspect()['State']['Status'] != 'exited':
            try:
                con.stop()
            except:
                pass
        try:
            con.remove()
        except:
            pass
        return

    def podman_stop_user_container(self, username: str):
        self.podman_remove_container_name(self.get_container_name(username))

    def podman_user_container_exists(self, username: str) -> bool:
        try:
            self.client.containers.get(self.get_container_name(username))
            return True
        except podman.errors.exceptions.NotFound:
            return False

    def podman_run_command_simple(self, username: str, command: Iterable[str], as_root: bool = True) -> int:
        """Runs command defined by arguments iterable in container. As root by default. Returns exit code."""
        container_name = self.get_container_name(username)
        un = username.lower().strip()
        con = self.client.containers.get(container_name)
        if as_root:
            un = 'root'
        return con.exec_run(list(command), user=un)[0]

    def clean_orphaned_containers(self):
        cli = self.client
        for i in cli.containers.list(all=True):
            if self.opts.name_prefix in str(i.name):
                self.podman_remove_container_name(str(i.name))

    def get_container_name(self, username: str) -> str:
        return self.opts.name_prefix + username.lower().strip()

    def touch_user_container(self, username: str):
        self.user_containers[self.get_container_name(username)] = datetime.datetime.now()

    def start_user_container(self, username: str):
        if not self.podman_user_container_exists(username):
            self.podman_start_user_container(username)
        self.touch_user_container(username)

    def clean_containers(self):
        """Checks running containers and stops them if they have been running too long."""
        for c in self.user_containers:
            if (datetime.datetime.now() - self.user_containers[c]) > self.opts.container_keepalive:
                self.podman_remove_container_name(c)
                del self.user_containers[c]
            else:
                if packetserver_version < self.podman_user_container_version(c):

    def user_runners_in_process(self, username: str) -> int:
        un = username.strip().lower()
        count = 0
        for r in self.runners:
            if r.is_in_process:
                if r.username == un:
                    count = count + 1
        return count

    def user_running(self, username: str) -> bool:
        if self.user_runners_in_process(username) > 0:
            return True
        else:
            return False

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
                 timeout_secs: str = 300, refresh_db: bool = True, labels: Optional[list] = None,
                   files: list[RunnerFile] = None) -> Optional[Runner]:
        if not self.started:
            return None
        with self.runner_lock:
            if not self.runners_available():
                return None
            pass

    def manage_lifecycle(self):
        if not self.started:
            return
        with self.runner_lock:
            for r in self.runners:
                if r.status is RunnerStatus.RUNNING:
                    r.heartbeat()
                if not r.is_finished():
                    self.touch_user_container(r.username)
            self.clean_containers()
            self.clean_orphaned_containers()

    def manager(self):
        logging.debug("Starting podman orchestrator thread.")
        while self.started:
            self.manage_lifecycle()
            time.sleep(.5)
        logging.debug("Stopping podman orchestrator thread.")

    def start(self):
        if not self.started:
            self.clean_orphaned_containers()
            self.started = True
            self.manager_thread = Thread(target=self.manager)
            self.manager_thread.start()

    def stop(self):
        self.started = False
        if self.manager_thread is not None:
            self.manager_thread.join(timeout=15)
        self.manager_thread = None