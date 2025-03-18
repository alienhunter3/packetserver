import datetime

from packetserver.client import Client
from packetserver.common import Request, Response, PacketServerConnection
from packetserver.common.util import to_date_digits
from typing import Union, Optional
from uuid import UUID, uuid4
import os.path


class AttachmentWrapper:
    def __init__(self, data: dict):
        for i in ['name', 'binary', 'data']:
            if i not in data.keys():
                raise ValueError("Data dict was not an attachment dictionary.")
        self._data = data

    def __repr__(self):
        return f"<AttachmentWrapper: {self.name}>"

    @property
    def name(self) -> str:
        return self._data['name']

    @property
    def binary(self) -> bool:
        return self._data['binary']

    @property
    def data(self) -> Union[str,bytes]:
        if self.binary:
            return self._data['data']
        else:
            return self._data['data'].decode()

class MessageWrapper:
    def __init__(self, data: dict):
        for i in ['attachments', 'to', 'from', 'id', 'sent_at', 'text']:
            if i not in data.keys():
                raise ValueError("Data dict was not a message dictionary.")
        self.data = data

    @property
    def text(self) -> str:
        return self.data['text']

    @property
    def sent(self) -> datetime.datetime:
        return datetime.datetime.fromisoformat(self.data['sent_at'])

    @property
    def msg_id(self) -> UUID:
        return UUID(self.data['id'])

    @property
    def from_user(self) -> str:
        return self.data['from']

    @property
    def to_users(self) -> list[str]:
        return self.data['to']

    @property
    def attachments(self) -> list[AttachmentWrapper]:
        a_list = []
        for a in self.data['attachments']:
            a_list.append(AttachmentWrapper(a))
        return a_list

class MsgAttachment:
    def __init__(self, name: str, data: Union[bytes,str]):
        self.binary = True
        self.name = name
        if type(data) in [bytes, bytearray]:
            self.data = data
        else:
            self.data = str(data).encode()
            self.binary = False

    def __repr__(self) -> str:
        return f"<MsgAttachment {self.name}>"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "data": self.data,
            "binary": self.binary
        }

def attachment_from_file(filename: str, binary: bool = True) -> MsgAttachment:
    a = MsgAttachment(os.path.basename(filename), open(filename, 'rb').read())
    if not binary:
        a.binary = False
    return a

def send_message(client: Client, bbs_callsign: str, text: str, to: list[str],
                 attachments: list[MsgAttachment] = None) -> dict:
    payload = {
        "text": text,
        "to": to,
        "attachments": []
    }
    if attachments is not None:
        for a in attachments:
            payload["attachments"].append(a.to_dict())

    req = Request.blank()
    req.path = "message"
    req.method = Request.Method.POST
    req.payload = payload
    response = client.send_receive_callsign(req, bbs_callsign)
    if response.status_code != 201:
        raise RuntimeError(f"POST message failed: {response.status_code}: {response.payload}")
    return response.payload

def get_message_uuid(client: Client, bbs_callsign: str, msg_id: UUID, ) -> MessageWrapper:
    req = Request.blank()
    req.path = "message"
    req.method = Request.Method.GET
    req.set_var('id', msg_id.bytes)
    response = client.send_receive_callsign(req, bbs_callsign)
    if response.status_code != 200:
        raise RuntimeError(f"GET message failed: {response.status_code}: {response.payload}")
    return MessageWrapper(response.payload)

def get_messages_since(client: Client, bbs_callsign: str, since: datetime.datetime, get_text: bool = True, limit: int = None,
                 sort_by: str = 'date', reverse: bool = False, search: str = None, get_attachments: bool = True,
                 source: str = 'received') -> list[MessageWrapper]:
    req = Request.blank()
    req.path = "message"
    req.method = Request.Method.GET

    # put vars together
    req.set_var('since', to_date_digits(since))

    source = source.lower().strip()
    if source not in ['sent', 'received', 'all']:
        raise ValueError("Source variable must be ['sent', 'received', 'all']")
    req.set_var('source', source)

    req.set_var('limit', limit)
    req.set_var('fetch_text', get_text)
    req.set_var('reverse', reverse)

    if sort_by.strip().lower() not in ['date', 'from', 'to']:
        raise ValueError("sort_by must be in ['date', 'from', 'to']")
    req.set_var('sort', sort_by)

    if type(search) is str:
        req.set_var('search', search)

    response = client.send_receive_callsign(req, bbs_callsign)
    if response.status_code != 200:
        raise RuntimeError(f"GET message failed: {response.status_code}: {response.payload}")
    msg_list = []
    for m in response.payload:
        msg_list.append(MessageWrapper(m))
    return msg_list

def get_messages(client: Client, bbs_callsign: str, get_text: bool = True, limit: int = None,
                 sort_by: str = 'date', reverse: bool = True, search: str = None, get_attachments: bool = True,
                 source: str = 'received') -> list[MessageWrapper]:

    req = Request.blank()
    req.path = "message"
    req.method = Request.Method.GET

    # put vars together

    source = source.lower().strip()
    if source not in ['sent', 'received', 'all']:
        raise ValueError("Source variable must be ['sent', 'received', 'all']")
    req.set_var('source', source)

    req.set_var('limit', limit)
    req.set_var('fetch_text', get_text)
    req.set_var('reverse', reverse)

    if sort_by.strip().lower() not in ['date', 'from', 'to']:
        raise ValueError("sort_by must be in ['date', 'from', 'to']")
    req.set_var('sort', sort_by)

    if type(search) is str:
        req.set_var('search', search)

    response = client.send_receive_callsign(req, bbs_callsign)
    if response.status_code != 200:
        raise RuntimeError(f"GET message failed: {response.status_code}: {response.payload}")
    msg_list = []
    for m in response.payload:
        msg_list.append(MessageWrapper(m))
    return msg_list
