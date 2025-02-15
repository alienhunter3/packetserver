from packetserver.client import Client
from packetserver.common import Request, Response
from typing import Union, Optional

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

def get_job_id(client: Client, bbs_callsign: str, job_id: int) -> dict:
    req = Request.blank()
    req.path = f"job/{job_id}"
    req.method = Request.Method.GET
    response = client.send_receive_callsign(req, bbs_callsign)
    if response.status_code != 200:
        raise RuntimeError(f"Sending job failed: {response.status_code}: {response.payload}")
    return response.payload
