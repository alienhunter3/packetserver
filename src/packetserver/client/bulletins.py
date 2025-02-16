from packetserver.client import Client
from packetserver.common import Request, Response, PacketServerConnection
from typing import Union, Optional
import datetime
import time

class BulletinWrapper:
    def __init__(self, data: dict):
        for i in ['author', 'id', 'subject', 'body', 'created_at', 'updated_at']:
            if i not in data:
                raise ValueError("Was not given a bulletin dictionary.")
        self.data = data

    @property
    def created(self) -> datetime.datetime:
        return datetime.datetime.fromisoformat(self.data['created_at'])

    @property
    def updated(self) -> datetime.datetime:
        return datetime.datetime.fromisoformat(self.data['updated_at'])

    @property
    def author(self) -> str:
        return self.data['author']

    @property
    def subject(self) -> str:
        return self.data['subject']

    @property
    def body(self) -> str:
        return self.data['body']

def post_bulletin(client: Client, bbs_callsign: str, subject: str, body: str) -> int:
    req = Request.blank()
    req.path = "bulletin"
    req.payload = {'subject': subject, 'body': body}
    req.method = Request.Method.POST
    response = client.send_receive_callsign(req, bbs_callsign)
    if response.status_code != 201:
        raise RuntimeError(f"Posting bulletin failed: {response.status_code}: {response.payload}")
    return response.payload['bulletin_id']

def get_bulletin_by_id(client: Client, bbs_callsign: str, bid: int) -> BulletinWrapper:
    req = Request.blank()
    req.path = "bulletin"
    req.set_var('id', bid)
    req.method = Request.Method.GET
    response = client.send_receive_callsign(req, bbs_callsign)
    if response.status_code != 200:
        raise RuntimeError(f"Sending job failed: {response.status_code}: {response.payload}")
    return BulletinWrapper(response.payload)

def get_bulletins_recent(client: Client, bbs_callsign: str, limit: int = None) -> list[BulletinWrapper]:
    req = Request.blank()
    req.path = "bulletin"
    req.method = Request.Method.GET
    if limit is not None:
        req.set_var('limit', limit)
    response = client.send_receive_callsign(req, bbs_callsign)
    if response.status_code != 200:
        raise RuntimeError(f"Sending job failed: {response.status_code}: {response.payload}")
    out_list = []
    for b in response.payload:
        out_list.append(BulletinWrapper(b))
    return out_list