from packetserver.client import Client
from packetserver.common import Request, Response, PacketServerConnection
from typing import Union, Optional
import datetime
import time


class BulletinWrapper:
    def __init__(self, data: dict):
        for i in ['id', 'author', 'subject', 'body', 'created_at', 'updated_at']:
            if i not in data.keys():
                raise ValueError("Data dict was not a bulletin dictionary.")
        self.data = data

    def __repr__(self):
        return f"<Bulletin {self.id} - {self.author}>"

    @property
    def id(self) -> int:
        return int(self.data['id'])

    @property
    def author(self) -> str:
        return str(self.data['author']).strip().upper()

    @property
    def subject(self) -> str:
        return str(self.data['subject'])

    @property
    def body(self) -> str:
        return str(self.data['body'])

    @property
    def created(self) -> datetime.datetime:
        return datetime.datetime.fromisoformat(self.data['created_at'])

    @property
    def updated(self) -> datetime.datetime:
        return datetime.datetime.fromisoformat(self.data['updated_at'])

    def to_dict(self, json=True) -> dict:
        d = {
            'id': self.id,
            'author': self.author,
            'subject': self.subject,
            'body': self.body,
            'created_at': self.created,
            'updated_at': self.updated
        }
        if json:
            d['created_at'] = d['created_at'].isoformat()
            d['updated_at'] = d['updated_at'].isoformat()
        return d

def post_bulletin(client: Client, bbs_callsign: str, subject: str, body: str) -> int:
    req = Request.blank()
    req.path = "bulletin"
    req.payload = {'subject': subject, 'body': body}
    req.method = Request.Method.POST
    response = client.send_receive_callsign(req, bbs_callsign)
    if response.status_code != 201:
        raise RuntimeError(f"Posting bulletin failed: {response.status_code}: {response.payload}")
    return response.payload['bulletin_id']

def get_bulletin_by_id(client: Client, bbs_callsign: str, bid: int, only_subject=False) -> BulletinWrapper:
    req = Request.blank()
    req.path = "bulletin"
    req.set_var('id', bid)
    if only_subject:
        req.set_var('no_body', True)
    req.method = Request.Method.GET
    response = client.send_receive_callsign(req, bbs_callsign)
    if response.status_code != 200:
        raise RuntimeError(f"GET bulletin {bid} failed: {response.status_code}: {response.payload}")
    return BulletinWrapper(response.payload)

def get_bulletins_recent(client: Client, bbs_callsign: str, limit: int = None,
                         only_subject=False) -> list[BulletinWrapper]:
    req = Request.blank()
    req.path = "bulletin"
    req.method = Request.Method.GET
    if limit is not None:
        req.set_var('limit', limit)
    if only_subject:
        req.set_var('no_body', True)
    response = client.send_receive_callsign(req, bbs_callsign)
    if response.status_code != 200:
        raise RuntimeError(f"Listing bulletins failed: {response.status_code}: {response.payload}")
    out_list = []
    for b in response.payload:
        out_list.append(BulletinWrapper(b))
    return out_list

def delete_bulletin_by_id(client: Client, bbs_callsign: str, bid: int):
    req = Request.blank()
    req.path = "bulletin"
    req.set_var('id', bid)
    req.method = Request.Method.DELETE
    response = client.send_receive_callsign(req, bbs_callsign)
    if response.status_code != 200:
        raise RuntimeError(f"DELETE bulletin {bid} failed: {response.status_code}: {response.payload}")