from packetserver.client import Client
from packetserver.common import Request, Response
from typing import Union, Optional
import datetime

class JobWrapper:
    def __init__(self, data: dict):
        for i in ['output', 'errors', 'artifacts', 'return_code', 'status']:
            if i not in data:
                raise ValueError("Was not given a job dictionary.")
        self.data = data
        self.artifacts = {}
        for i in data['artifacts']:
            self.artifacts[i[0]] = self.artifacts[i][1]

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
    def started(self) -> datetime.datetime:
        return datetime.datetime.fromisoformat(self.data['started_at'])

    @property
    def finished(self) -> datetime.datetime:
        return datetime.datetime.fromisoformat(self.data['finished_at'])

    @property
    def id(self) -> int:
        return self.data['id']




def send_job(client: Client, bbs_callsign: str, cmd: Union[str, list]) -> int:
    """Send a job using client to bbs_callsign with args cmd. Return remote job_id."""
    req = Request.blank()
    req.path = "job"
    req.payload = {'cmd': cmd}
    req.method = Request.Method.POST
    response = client.send_receive_callsign(req, bbs_callsign)
    if response.status_code != 201:
        raise RuntimeError(f"Sending job failed: {response.status_code}: {response.payload}")
    return response.payload['job_id']

def get_job_id(client: Client, bbs_callsign: str, job_id: int, get_data=True) -> JobWrapper:
    req = Request.blank()
    req.path = f"job/{job_id}"
    req.method = Request.Method.GET
    response = client.send_receive_callsign(req, bbs_callsign)
    if response.status_code != 200:
        raise RuntimeError(f"Sending job failed: {response.status_code}: {response.payload}")
    return JobWrapper(response.payload)
