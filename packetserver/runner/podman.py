"""Uses podman to run jobs in containers."""
import time

from ZEO import client

from . import Runner, Orchestrator, RunnerStatus, RunnerFile, scripts_tar
from packetserver.runner.constants import podman_run_command
from urllib.parse import urlparse
from collections import namedtuple
from typing import Optional, Iterable, Union
from traceback import format_exc
import podman
import gzip
from podman.domain.containers import Container
import podman.errors
import os
import os.path
import logging
import datetime
from os.path import basename, dirname
from packetserver.common.util import bytes_to_tar_bytes, random_string, extract_tar_bytes, bytes_tar_has_files, \
    TarFileExtractor
from packetserver import VERSION as packetserver_version
import re
from threading import Thread
from io import BytesIO

env_splitter_rex = '''([a-zA-Z0-9]+)=([a-zA-Z0-9]*)'''

PodmanOptions = namedtuple("PodmanOptions", ["default_timeout", "max_timeout", "image_name",
                                             "max_active_jobs", "container_keepalive", "name_prefix"])

class PodmanRunner(Runner):
    def __init__(self, username: str, args: Union[str, list[str]], job_id: int, container: Container,
                 environment: Optional[dict] = None, timeout_secs: str = 300, labels: Optional[list] = None,
                 files: list[RunnerFile] = None):
        super().__init__(username, args, job_id, environment=environment, timeout_secs=timeout_secs,
                         labels=labels, files=files)
        self._artifact_archive = b''
        if not container.inspect()['State']['Running']:
            raise ValueError(f"Container {container} is not in state Running.")
        self.container = container
        self._thread = None
        self.env['PACKETSERVER_JOBID'] = str(job_id)
        self.job_path = os.path.join("/home", self.username, ".packetserver", str(job_id))
        self.archive_path = os.path.join("/artifact_output", f"{str(job_id)}.tar.gz")

    def thread_runner(self):
        self.status = RunnerStatus.RUNNING
        logging.debug(f"Thread for runner {self.job_id} started. Command for {(type(self.args))}:\n{self.args}")
        # run the exec call
        if type(self.args) is str:
            logging.debug(f"Running string: {self.args}")
            res = self.container.exec_run(cmd=self.args, environment=self.env, user=self.username, demux=True,
                                          workdir=self.job_path)
        else:
            logging.debug(f"Running iterable: {list(self.args)}")
            res = self.container.exec_run(cmd=list(self.args), environment=self.env, user=self.username, demux=True,
                                          workdir=self.job_path)
        logging.debug(str(res))
        # cleanup housekeeping
        self.status = RunnerStatus.STOPPING
        self._result = res
        # run cleanup script
        logging.debug(f"Running cleanup script for {self.job_id}")
        end_res = self.container.exec_run("bash /root/scripts/job_end_script.sh",
                                environment=self.env, user="root", tty=True)
        logging.debug(f"End result: {end_res}")
        if end_res[0] != 0:
            logging.error(f"End Job script failed:\n{end_res[1].decode()}")
        # collect any artifacts
        try:
            retrieved_tar_bytes = b''.join(self.container.get_archive(self.archive_path)[0])
            art_tar_bytes = extract_tar_bytes(retrieved_tar_bytes)[1]
            logging.debug(f"bytes retrieved: {retrieved_tar_bytes}")
            if bytes_tar_has_files(gzip.GzipFile(fileobj=BytesIO(art_tar_bytes))):
                logging.debug("found artifacts; attaching to runner object")
                self._artifact_archive = art_tar_bytes
            else:
                logging.debug(f"no artifacts returned for job {self.job_id}")
        except:
            logging.warning(f"Error retrieving artifacts for {self.job_id}:\n{format_exc()}")
            self._artifact_archive = b''
        self.finished_at = datetime.datetime.now(datetime.UTC)
        # set final status to FAILED or SUCCEEDED
        if self.return_code == 0:
            self.status = RunnerStatus.SUCCESSFUL
        else:
            self.status = RunnerStatus.FAILED

    @property
    def has_artifacts(self) -> bool:
        if self._artifact_archive == b'':
            return False
        else:
            return True

    @property
    def artifacts(self) -> TarFileExtractor:
        if self._artifact_archive == b'':
            return TarFileExtractor(BytesIO(b''))
        else:
            return TarFileExtractor(gzip.GzipFile(fileobj=BytesIO(self._artifact_archive)))

    @property
    def output(self) -> bytes:
        return self._result[1][0]

    @property
    def output_str(self) -> str:
        try:
            output = self.output.decode()
        except:
            output = str(self.output)
        return output

    @property
    def errors(self) -> str:
        return self._result[1][1]

    @property
    def errors_str(self) -> str:
        return self._result[1][1].decode()

    @property
    def return_code(self) -> int:
        return self._result[0]

    def start(self):
        logging.debug(f"Starting runner {self.job_id} for {self.username} with command:\n({type(self.args)}){self.args}")
        self.status = RunnerStatus.STARTING
        # Run job setup script
        logging.debug(f"Running job setup script for {self.job_id} runner")
        setup_res = self.container.exec_run("bash /root/scripts/job_setup_script.sh",
                                environment=self.env, user="root", tty=True)
        logging.debug(f"Job {self.job_id} setup script:\n{str(setup_res[1])}")
        if setup_res[0] != 0:
            self.status = RunnerStatus.FAILED
            raise RuntimeError(f"Couldn't run setup scripts for {self.job_id}:\n{setup_res[1]}")
        # put files where they need to be
        for f in self.files:
            logging.debug(f"Adding file {f} for job {self.job_id}")
            if not f.isabs:
                dest = os.path.join(self.job_path, f.destination_path)
                dirn = os.path.dirname(dest)
            else:
                dest = f.destination_path
                dirn = f.dirname
            if self.container.put_archive(dirn, f.tar_data()):
                logging.debug(f"Placed file {dest} for job {self.job_id}")
            else:
                logging.warning(f"Failed to place file {dest} for job {self.job_id}!!")
            if not f.root_owned:
                self.container.exec_run(f"chown -R {self.username} {dest}")

        # start thread
        logging.debug(f"Starting runner thread for {self.job_id}")
        self._thread = Thread(target=self.thread_runner)
        super().start()
        self._thread.start()

class PodmanOrchestrator(Orchestrator):
    def __init__(self, uri: Optional[str] = None, options: Optional[PodmanOptions] = None):
        super().__init__()
        self.started = False
        self.user_containers = {}
        self.manager_thread = None
        self._client = None
        self._five_min_ticker = 600

        if uri:
            self.uri = uri
        else:
            self.uri = f"unix:///run/user/{os.getuid()}/podman/podman.sock"
        uri_parsed = urlparse(self.uri)
        if uri_parsed.scheme == "unix":
            if not os.path.exists(uri_parsed.path):
                raise FileNotFoundError(f"Podman socket not found: {self.uri}")
        test_client = self.new_client()
        logging.debug(f"Testing podman socket. Version: {test_client.info()}")
        self._client = None

        self.username_containers = {}
        if options:
            self.opts = options
        else:
            self.opts = PodmanOptions(default_timeout=300, max_timeout=3600, image_name="debian", max_active_jobs=5,
                                  container_keepalive=300, name_prefix="packetserver_")

    @property
    def client(self) -> Optional[podman.PodmanClient]:
        return self._client

    def new_client(self) -> podman.PodmanClient:
        cli =  podman.PodmanClient(base_url=self.uri)
        self._client = cli
        return cli

    def add_file_to_user_container(self, username: str, data: bytes, path: str, root_owned=False):
        cli = self.client
        file_dir = dirname(path)
        tar_data_bytes = bytes_to_tar_bytes(basename(path), data)
        con = cli.containers.get(self.get_container_name(username))
        res = con.exec_run(cmd=["mkdir", "-p", file_dir], user="root")
        if res[0] != 1:
            raise RuntimeError("Couldn't create directory")
        con.put_archive(file_dir, tar_data_bytes)

    def get_file_from_user_container(self, username: str, path: str) -> bytes :
        cli = self.client
        con = cli.containers.get(self.get_container_name(username))
        tar_result = con.get_archive(path)
        bytes_tar = b"".join(list(tar_result[0]))
        return extract_tar_bytes(bytes_tar)[1]

    def podman_container_env(self, container_name: str) -> dict:
        cli = self.client
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
            return {}


    def podman_user_container_env(self, username: str) -> dict:
        container_name = self.get_container_name(username)
        return self.podman_container_env(container_name)


    def podman_start_user_container(self, username: str) -> Container:
        container_env = {
            "PACKETSERVER_VERSION": packetserver_version,
            "PACKETSERVER_USER": username.strip().lower()
        }
        logging.debug(f"Starting user container for {username} with command {podman_run_command}")
        con = self.client.containers.create(self.opts.image_name, name=self.get_container_name(username),
                                            command=podman_run_command,
                                            environment=container_env, user="root")
        con.start()
        logging.debug(f"Container started for {username} from image {self.opts.image_name}")
        started_at = datetime.datetime.now()
        logging.debug(f"Container state: \n{con.inspect()['State']}")
        while con.inspect()['State']['Status'] not in ['exited', 'running']:
            logging.debug("Container state not in ['exited', 'running']")
            now = datetime.datetime.now()
            if (now - started_at).total_seconds() > 300:
                con.stop()
                con.remove()
            time.sleep(.1)
        time.sleep(.5)
        if con.inspect()['State']['Status'] != 'running':
            logging.debug(f"Container for {username} isn't running. Cleaning it up.")
            try:
                con.stop()
            except:
                pass
            try:
                con.rename(f"{self.get_container_name(username)}_old")
                con.remove()
            except:
                pass
            raise RuntimeError(f"Couldn't start container for user {username}")
        if not con.put_archive('/root/scripts', scripts_tar()):
            con.stop()
            con.remove()
            raise RuntimeError("Failed to upload job scripts to container.")
        res = con.exec_run(cmd=["bash", "/root/scripts/container_setup_script.sh"], tty=True, user="root")
        logging.debug(f"Container setup script run:\n{res[1].decode()}\nExit Code: {res[0]}")
        if res[0] != 0:
            logging.error(f"Container setup script failed:\n{res[1].decode()}\nExit Code: {res[0]}")
            con.stop()
            con.remove()
            raise RuntimeError(f"Container setup script failed:\n{res[1].decode()}\nExit Code: {res[0]}")
        self.touch_user_container(username)
        return con

    def podman_remove_container_name(self, container_name: str):
        cli = self.client
        logging.debug(f"Attempting to remove container named {container_name}")
        try:
            con = cli.containers.get(container_name)
            if con.inspect()['State']['Status'] == 'running':
                con.exec_run(cmd="touch /root/ENDNOW", user="root")
                time.sleep(1)
        except podman.errors.exceptions.NotFound as e:
            logging.warning(f"Didn't find container named {container_name}")
            return
        try:
            con.rename(f"{container_name}_{random_string()}")
        except:
            logging.error(f"Couldn't rename container:\n{format_exc()}")
        if con.inspect()['State']['Status'] != 'exited':
            try:
                con.stop(timeout=10)
            except:
                logging.error(f"Couldn't stop container:\n{format_exc()}")
        try:
            con.remove()
        except:
            logging.error(f"Couldn't remove container:\n{format_exc()}")
        return

    def podman_stop_user_container(self, username: str):
        self.podman_remove_container_name(self.get_container_name(username))
        if self.get_container_name(username) in self.user_containers:
            del self.user_containers[self.get_container_name(username)]

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
                if str(i.name) not in self.user_containers:
                    self.podman_remove_container_name(str(i.name))

    def get_container_name(self, username: str) -> str:
        return self.opts.name_prefix + username.lower().strip()

    def get_username_from_container_name(self, container_name: str) -> str:
        if not self.opts.name_prefix in container_name:
            raise ValueError(f"{container_name} is not a user container")
        return container_name.replace(self.opts.name_prefix, "")


    def touch_user_container(self, username: str):
        self.user_containers[self.get_container_name(username)] = datetime.datetime.now()

    def start_user_container(self, username: str) -> Container:
        if not self.podman_user_container_exists(username):
            con = self.podman_start_user_container(username)
        else:
            con = self.client.containers.get(self.get_container_name(username))
        return con

    def clean_containers(self):
        """Checks running containers and stops them if they have been running too long."""
        containers_to_clean = set()
        for c in self.user_containers:
            if (datetime.datetime.now() - self.user_containers[c]).total_seconds() > self.opts.container_keepalive:
                logging.debug(f"Container {c} no activity for {self.opts.container_keepalive} seconds. Clearing.")
                containers_to_clean.add(c)
        for c in list(containers_to_clean):
            self.podman_remove_container_name(c)
            del self.user_containers[c]


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

    def new_runner(self, username: str, args: Union[str, list[str]], job_id: int, environment: Optional[dict] = None,
                 timeout_secs: str = 300, refresh_db: bool = True, labels: Optional[list] = None,
                   files: list[RunnerFile] = None) -> Optional[PodmanRunner]:
        if not self.started:
            logging.warning("Attempted to queue a runner when not started")
            return None
        with self.runner_lock:
            if not self.runners_available():
                logging.warning("Attempted to queue a runner when no runner slots available.")
                return None
            con = self.start_user_container(username)
            logging.debug(f"Started a container for {username} successfully.")
            self.touch_user_container(username)
            logging.debug(f"Queuing a runner on container {con}, with command '{args}' of type '{type(args)}'")
            runner = PodmanRunner(username, args, job_id, con, environment=environment, timeout_secs=timeout_secs,
                                  labels=labels, files=files)
            self.runners.append(runner)
            runner.start()
            return runner

    def manage_lifecycle(self):
        if not self.started:
            return
        with self.runner_lock:
            for r in self.runners:
                if not r.is_finished():
                    self.touch_user_container(r.username)
            self.clean_containers()

            if self._five_min_ticker >= 600:
                self.clean_orphaned_containers()
                self._five_min_ticker = 0

    def manager(self):
        logging.debug("Starting podman orchestrator thread.")
        while self.started:
            self.manage_lifecycle()
            time.sleep(.5)
        logging.debug("Stopping podman orchestrator thread.")

    def start(self):
        if not self.started:
            self.new_client()
            self.clean_orphaned_containers()
            self._five_min_ticker = 0
            self.started = True
            self.manager_thread = Thread(target=self.manager)
            self.manager_thread.start()

    def __del__(self):
        if self.started:
            self.stop()

    def stop(self):
        logging.debug("Stopping podman orchestrator.")
        self.started = False
        cli = self.client
        self.user_containers = {}
        self.clean_orphaned_containers()
        if self.manager_thread is not None:
            logging.debug("Joining orchestrator manager thread.")
            self.manager_thread.join(timeout=15)
        logging.debug("Orchestrator manager thread stopped")
        self.manager_thread = None
        self._client = None