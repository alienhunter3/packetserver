import datetime
import tempfile

import pe.app
from packetserver.common import Response, Message, Request, PacketServerConnection, send_response, send_blank_response
from packetserver.server.constants import default_server_config
from packetserver.server.users import User
from copy import deepcopy
import ax25
from pathlib import Path
import ZODB, ZODB.FileStorage
from BTrees.OOBTree import OOBTree
from persistent.mapping import PersistentMapping
from persistent.list import PersistentList
from packetserver.server.requests import standard_handlers
import logging
import signal
import time
from msgpack.exceptions import OutOfData
from typing import Callable, Self, Union
from traceback import  format_exc
from os import linesep
from shutil import rmtree
from threading import Thread
from packetserver.server.jobs import get_orchestrator_from_config, Job, JobStatus
from packetserver.runner import RunnerStatus, RunnerFile, Orchestrator, Runner

VERSION="0.2.0-alpha"

def init_bulletins(root: PersistentMapping):
    if 'bulletins' not in root:
        root['bulletins'] = PersistentList()
    if 'bulletin_counter' not in root:
        root['bulletin_counter'] = 0

class Server:
    def __init__(self, pe_server: str, port: int, server_callsign: str, data_dir: str = None, zeo: bool = True):
        if not ax25.Address.valid_call(server_callsign):
            raise ValueError(f"Provided callsign '{server_callsign}' is invalid.")
        self.callsign = server_callsign
        self.pe_server = pe_server
        self.pe_port = port
        self.handlers = deepcopy(standard_handlers)
        self.zeo_addr = None
        self.zeo_stop = None
        self.zeo = zeo
        self.started = False
        self.orchestrator = None
        self.worker_thread = None
        self.check_job_queue = True
        self.last_check_job_queue = datetime.datetime.now()
        self.job_check_interval = 60
        self.quick_job = False
        if data_dir:
            data_path = Path(data_dir)
        else:
            data_path = Path.home().joinpath(".packetserver")
        if data_path.is_dir():
            if data_path.joinpath("data.zopedb").exists():
                if not data_path.joinpath("data.zopedb").is_file():
                    raise FileExistsError("data.zopedb exists as non-file in specified path")
            self.home_dir = data_path
        else:
            if data_path.exists():
                raise FileExistsError(f"Non-Directory path '{data_dir}' already exists.")
            else:
                data_path.mkdir()
                self.home_dir = data_path
        self.storage = ZODB.FileStorage.FileStorage(self.data_file)
        self.db = ZODB.DB(self.storage)
        with self.db.transaction() as conn:
            logging.debug(f"checking for datastructures: conn.root.keys(): {list(conn.root().keys())}")
            if 'config' not in conn.root():
                logging.debug("no config, writing blank default config")
                conn.root.config = PersistentMapping(deepcopy(default_server_config))
                conn.root.config['blacklist'] = PersistentList()
            if 'SYSTEM' not in conn.root.config['blacklist']:
                logging.debug("Adding 'SYSTEM' to blacklist in case someone feels like violating FCC rules.")
                conn.root.config['blacklist'].append('SYSTEM')
            if 'users' not in conn.root():
                logging.debug("users missing, creating bucket")
                conn.root.users = PersistentMapping()
            if 'messages' not in conn.root():
                logging.debug("messages container missing, creating bucket")
                conn.root.messages = PersistentMapping()
            if 'SYSTEM' not in conn.root.users:
                logging.debug("Creating system user for first time.")
                User('SYSTEM', hidden=True, enabled=False).write_new(conn.root())
            if 'objects' not in conn.root():
                logging.debug("objects bucket missing, creating")
                conn.root.objects = OOBTree()
            if 'jobs' not in conn.root():
                logging.debug("jobss bucket missing, creating")
                conn.root.jobs = OOBTree()
            if 'job_queue' not in conn.root():
                conn.root.job_queue = PersistentList()
            if 'user_jobs' not in conn.root():
                conn.root.user_jobs = PersistentMapping()
            init_bulletins(conn.root())
            if ('jobs_enabled' in conn.root.config) and conn.root.config['jobs_enabled']:
                logging.debug(conn.root.config['jobs_enabled'])
                logging.debug(conn.root.config['jobs_config'])
                if 'runner' in conn.root.config['jobs_config']:
                    val = str(conn.root.config['jobs_config']['runner']).lower().strip()
                    if val in ['podman']:
                        logging.debug("Enabling podman orchestrator")
                        self.orchestrator = get_orchestrator_from_config(conn.root.config['jobs_config'])

        self.app = pe.app.Application()
        PacketServerConnection.receive_subscribers.append(lambda x: self.server_receiver(x))
        PacketServerConnection.connection_subscribers.append(lambda x: self.server_connection_bouncer(x))
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)
        self.db.close()
        self.storage.close()

    @property
    def data_file(self) -> str:
        return str(Path(self.home_dir).joinpath('data.zopedb'))

    def ping_job_queue(self):
        self.check_job_queue = True
        self.last_check_job_queue = datetime.datetime.now()
        if self.quick_job:
            logging.debug("Setting the final quick job timer.")
            self.job_check_interval = 5
            self.quick_job = False
        else:
            self.job_check_interval = 60

    def server_connection_bouncer(self, conn: PacketServerConnection):
        logging.debug("new connection bouncer checking user status")
        # blacklist check
        blacklisted = False
        base = ax25.Address(conn.remote_callsign).call
        with self.db.transaction() as storage:
            if 'blacklist' in storage.root.config:
                bl = storage.root.config['blacklist']
                logging.debug(f"A blacklist exists: {bl}")
                logging.debug(f"Checking callsign {base.upper()}")
                if base.upper() in bl:
                    logging.debug(f"Connection from blacklisted callsign {base}")
                    conn.closing = True
                    blacklisted = True

            # user object check
            logging.debug(f"checking user existence for {base}")
            logging.debug(f"users in db right now: {list(storage.root.users.keys())}")
            if base in storage.root.users:
                logging.debug(f"User {base} exists in db.")
                u = storage.root.users[base]
                u.seen()
            else:
                logging.debug(f"User {base} doesn't exist in db")
                logging.info(f"Creating new user {base}")
                u = User(base.upper().strip())
                u.write_new(storage.root())
        if blacklisted:
            count = 0
            while count < 10:
                time.sleep(.5)
                if conn.state.name == "CONNECTED":
                    break
            conn.close()

    def handle_request(self, req: Request, conn: PacketServerConnection):
        """Handles a proper request by handing off to the appropriate function depending on method and Path."""
        logging.debug(f"asked to handle request: {req}")
        if conn.closing:
            logging.debug("Connection marked as closing. Ignoring it.")
            return
        req_root_path = req.path.split("/")[0]
        if 'quick' in req.vars:
            logging.debug("Setting quick job timer for a quick job.")
            self.job_check_interval = 8
            self.quick_job = True
        if req_root_path in self.handlers:
            logging.debug(f"found handler for req {req}")
            self.handlers[req_root_path](req, conn, self.db)
            return
        logging.warning(f"unhandled request found: {req}")
        send_blank_response(conn, req, status_code=404)

    def process_incoming_data(self, connection: PacketServerConnection):
        """Handles incoming data."""
        logging.debug("Running process_incoming_data on connection")
        with connection.data_lock:
            logging.debug("Data lock acquired")
            while True:
                try:
                    msg = Message.partial_unpack(connection.data.unpack())
                    logging.debug(f"parsed a Message from data received")
                except OutOfData:
                    logging.debug("no complete message yet, done until more data arrives")
                    break
                except ValueError:
                    connection.send_data(b"BAD REQUEST. COULD NOT PARSE INCOMING DATA AS PACKETSERVER MESSAGE")
                try:
                    request = Request(msg)
                    logging.debug(f"parsed Message into request {request}")
                except ValueError:
                    connection.send_data(b"BAD REQUEST. DID NOT RECEIVE A REQUEST MESSAGE.")
                logging.debug(f"attempting to handle request {request}")
                self.handle_request(request, connection)
                self.ping_job_queue()
                logging.debug("request handled")

    def server_receiver(self, conn: PacketServerConnection):
        logging.debug("running server receiver")
        try:
            self.process_incoming_data(conn)
        except Exception:
            logging.debug(f"Unhandled exception while processing incoming data:\n{format_exc()}")

    def register_path_handler(self, path_root: str, fn: Callable):
        self.handlers[path_root.strip().lower()] = fn

    def server_worker(self):
        """When called, do things. Should get called every so often."""
        if not self.started:
            return
        # Add things to do here:
        now = datetime.datetime.now()
        if (now - self.last_check_job_queue).total_seconds() > self.job_check_interval:
            self.ping_job_queue()
        if (self.orchestrator is not None) and self.orchestrator.started and self.check_job_queue:
            with self.db.transaction() as storage:
                # queue as many jobs as possible
                while self.orchestrator.runners_available():
                    if len(storage.root.job_queue) > 0:
                        jid = storage.root.job_queue[0]
                        try:
                            logging.info(f"Starting job {jid}")
                            job = Job.get_job_by_id(jid, storage.root())
                        except:
                            logging.error(f"Error retrieving job {jid}")
                            break
                        runner = self.orchestrator.new_runner(job.owner, job.cmd, jid, environment=job.env, files=job.files)
                        if runner is not None:
                            storage.root.job_queue.remove(jid)
                            job.status = JobStatus.RUNNING
                            job.started_at = datetime.datetime.now()
                            logging.info(f"Started job {job}")
                    else:
                        break
                if len(storage.root.job_queue) == 0:
                    self.check_job_queue = False
                else:
                    self.ping_job_queue()

            finished_runners = []
            for runner in self.orchestrator.runners:
                if runner.is_finished():
                    logging.debug(f"Finishing runner {runner}")
                    with self.db.transaction() as storage:
                        try:
                            if Job.update_job_from_runner(runner, storage.root()):
                                finished_runners.append(runner)
                                logging.info(f"Runner {runner} successfully synced with jobs.")
                            else:
                                logging.error(f"update_job_from_runner returned False.")
                                logging.error(f"Error while finishing runner and updating job status {runner}")
                        except:
                            logging.error(f"Error while finishing runner and updating job status {runner}\n:{format_exc()}")
            for runner in finished_runners:
                logging.info(f"Removing completed runner {runner}")
                with self.orchestrator.runner_lock:
                    self.orchestrator.runners.remove(runner)

    def run_worker(self):
        """Intended to be running as a thread."""
        logging.info("Starting worker thread.")
        while self.started:
            self.server_worker()
            time.sleep(.5)

    def __del__(self):
        self.stop()

    def start_db(self):
        if not self.zeo:
            self.storage = ZODB.FileStorage.FileStorage(self.data_file)
            self.db = ZODB.DB(self.storage)
        else:
            import ZEO
            address, stop = ZEO.server(path=self.data_file)
            self.zeo_addr = address
            self.zeo_stop = stop
            self.db = ZEO.DB(self.zeo_addr)
            logging.info(f"Starting ZEO server with address {self.zeo_addr}")
            try:
                zeo_address_file = str(self.home_dir.joinpath("zeo-address.txt"))
                open(zeo_address_file, 'w').write(f"{self.zeo_addr[0]}:{self.zeo_addr[1]}{linesep}")
                logging.info(f"Wrote ZEO server info to '{zeo_address_file}'")
            except:
                logging.warning(f"Couldn't write ZEO server info to '{zeo_address_file}'\n{format_exc()}")

    def start(self):
        self.start_db()
        self.app.start(self.pe_server, self.pe_port)
        self.app.register_callsigns(self.callsign)
        self.started = True
        if self.orchestrator is not None:
            logging.info(f"Starting orchestrator {self.orchestrator}")
            self.orchestrator.start()
        self.worker_thread = Thread(target=self.run_worker)
        self.worker_thread.start()

    def exit_gracefully(self, signum, frame):
        self.stop()

    def stop_db(self):
        self.storage.close()
        self.db.close()
        if self.zeo:
            logging.info("Stopping ZEO.")
            self.zeo_stop()

    def stop(self):
        self.started = False
        cm = self.app._engine._active_handler._handlers[1]._connection_map
        for key in cm._connections.keys():
            cm._connections[key].close()
        if self.orchestrator is not None:
            self.orchestrator.stop()
        self.app.stop()
        self.stop_db()


