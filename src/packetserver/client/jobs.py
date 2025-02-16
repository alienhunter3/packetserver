from packetserver.client import Client
from packetserver.common import Request, Response, PacketServerConnection
from typing import Union, Optional
import datetime
import time

class JobWrapper:
    def __init__(self, data: dict):
        for i in ['output', 'errors', 'artifacts', 'return_code', 'status']:
            if i not in data:
                raise ValueError("Was not given a job dictionary.")
        self.data = data
        self.artifacts = {}
        for i in data['artifacts']:
            self.artifacts[i[0]] = i[1]

    @property
    def return_code(self) -> int:
        return self.data['return_code']

    @property
    def output_raw(self) -> bytes:
        return self.data['output']

    @property
    def output_str(self) -> str:
        return self.data['output'].decode()

    @property
    def errors_raw(self) -> bytes:
        return self.data['errors']

    @property
    def errors_str(self) -> str:
        return self.data['errors'].decode()

    @property
    def status(self) -> str:
        return self.data['status']

    @property
    def owner(self) -> str:
        return self.data['owner']

    @property
    def cmd(self) -> Union[str, list]:
        return self.data['cmd']

    @property
    def created(self) -> datetime.datetime:
        return datetime.datetime.fromisoformat(self.data['created_at'])

    @property
    def started(self) -> Optional[datetime.datetime]:
        if not self.data['created_at']:
            return None
        return datetime.datetime.fromisoformat(self.data['created_at'])

    @property
    def finished(self) -> Optional[datetime.datetime]:
        if not self.data['finished_at']:
            return None
        return datetime.datetime.fromisoformat(self.data['finished_at'])

    @property
    def is_finished(self) -> bool:
        if self.finished is not None:
            return True
        return False

    @property
    def id(self) -> int:
        return self.data['id']

    def __repr__(self):
        return f"<Job {self.id} - {self.owner} - {self.status}>"

def send_job(client: Client, bbs_callsign: str, cmd: Union[str, list], db: bool = False, env: dict = None,
             files: dict = None) -> int:
    """Send a job using client to bbs_callsign with args cmd. Return remote job_id."""
    req = Request.blank()
    req.path = "job"
    req.payload = {'cmd': cmd}
    if db:
        req.payload['db'] = ''
    if env is not None:
        req.payload['env']= env
    if files is not None:
        req.payload['files'] = files
    req.method = Request.Method.POST
    response = client.send_receive_callsign(req, bbs_callsign)
    if response.status_code != 201:
        raise RuntimeError(f"Sending job failed: {response.status_code}: {response.payload}")
    return response.payload['job_id']

def send_job_quick(client: Client, bbs_callsign: str, cmd: Union[str, list], db: bool = False, env: dict = None,
             files: dict = None) -> JobWrapper:
    """Send a job using client to bbs_callsign with args cmd. Wait for quick job to return job results."""
    req = Request.blank()
    req.path = "job"
    req.payload = {'cmd': cmd}
    req.set_var('quick', True)
    if db:
        req.payload['db'] = ''
    if env is not None:
        req.payload['env']= env
    if files is not None:
        req.payload['files'] = files
    req.method = Request.Method.POST
    response = client.send_receive_callsign(req, bbs_callsign)
    if response.status_code == 200:
        return JobWrapper(response.payload)
    elif response.status_code == 202:
        raise RuntimeError(f"Quick Job timed out. Job ID: {response.payload}")
    else:
        raise RuntimeError(f"Waiting for quick job failed: {response.status_code}: {response.payload}")


def get_job_id(client: Client, bbs_callsign: str, job_id: int, get_data=True) -> JobWrapper:
    req = Request.blank()
    req.path = f"job/{job_id}"
    req.method = Request.Method.GET
    response = client.send_receive_callsign(req, bbs_callsign)
    if response.status_code != 200:
        raise RuntimeError(f"Sending job failed: {response.status_code}: {response.payload}")
    return JobWrapper(response.payload)

class JobSession:
    def __init__(self, client: Client, bbs_callsign: str, default_timeout: int = 300, stutter: int = 2):
        self.client = client
        self.bbs = bbs_callsign
        self.timeout = default_timeout
        self.stutter = stutter
        self.job_log = []

    def connect(self) -> PacketServerConnection:
        return self.client.new_connection(self.bbs)

    def send(self, cmd: Union[str, list], db: bool = False, env: dict = None, files: dict = None) -> int:
        return send_job(self.client, self.bbs, cmd, db=db, env=env, files=files)

    def send_quick(self, cmd: Union[str, list], db: bool = False, env: dict = None, files: dict = None) -> JobWrapper:
        return send_job_quick(self.client, self.bbs, cmd, db=db, env=env, files=files)

    def get_id(self, jid: int) -> JobWrapper:
        return get_job_id(self.client, self.bbs, jid)

    def run_job(self, cmd: Union[str, list], db: bool = False, env: dict = None, files: dict = None,
                quick: bool = False) -> JobWrapper:
        if quick:
            j = self.send_quick(cmd, db=db, env=env, files=files)
            self.job_log.append(j)
            return j
        else:
            jid = self.send(cmd, db=db, env=env, files=files)
            time.sleep(self.stutter)
            j = self.get_id(jid)
            while not j.is_finished:
                time.sleep(self.stutter)
                j = self.get_id(jid)
            self.job_log.append(j)
            return j



