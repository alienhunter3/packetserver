"""BBS private message system"""
import ax25
import persistent
import persistent.list
from persistent.mapping import PersistentMapping
import datetime
from typing import Self,Union,Optional,Iterable,Sequence
from packetserver.common import PacketServerConnection, Request, Response, send_response, send_blank_response
from packetserver.common import Message as PacketMessage
from packetserver.common.constants import yes_values, no_values
from packetserver.common.util import from_date_digits, to_date_digits
import ZODB
import logging
import uuid
from uuid import UUID
from packetserver.common.util import email_valid
from packetserver.server.objects import Object
from packetserver.server.users import User
from BTrees.OOBTree import TreeSet
from packetserver.server.users import User, user_authorized
from traceback import format_exc
from collections import namedtuple
import re

since_regex = """^message\\/since\\/(\\d+)$"""

def mailbox_create(username: str, db_root: PersistentMapping):
    un = username.upper().strip()
    u = User.get_user_by_username(un, db_root)
    if u is None:
        raise KeyError(f"Username {username} does not exist.")
    if not u.enabled:
        raise KeyError(f"Username {username} does not exist.")
    if un not in db_root['messages']:
        db_root['messages'][un] = persistent.list.PersistentList()


def global_unique_message_uuid(db_root: PersistentMapping) -> UUID:
    if "message_uuids" not in db_root:
        db_root['message_uuids'] = TreeSet()
        logging.debug("Created message_uuid set for global message ids.")
    uid = uuid.uuid4()
    while uid in db_root['message_uuids']:
        uid = uuid.uuid4()
    return uid

class Attachment:
    """Name and data that is sent with a message."""
    def __init__(self, name: str, data: Union[bytes,bytearray,str]):
        self._name = ""
        self._data = b""
        self._binary = True
        self.data = data
        self.name = name

    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, name: str):
        if name.strip() != self._name:
            if len(name.strip()) > 300:
                raise ValueError("Object names must be no more than 300 characters.")
            self._name = name.strip()

    @property
    def binary(self):
        return self._binary

    @property
    def data(self) -> Union[str,bytes]:
        if self.binary:
            return self._data
        else:
            return self._data.decode()

    @data.setter
    def data(self, data: Union[bytes,bytearray,str]):
        if type(data) in (bytes,bytearray):
            if bytes(data) != self._data:
                self._data = bytes(data)
                self._binary = True
        else:
            if str(data).encode() != self._data:
                self._data = str(data).encode()
                self._binary = False

    @property
    def size(self) -> int:
        return len(self.data)

    def copy(self):
        return Attachment(self.name, self.data)

    @classmethod
    def from_dict(cls, attachment: dict):
        name = attachment.get("name")
        data = attachment.get("data")
        return Attachment(name, data)

    def to_dict(self, include_data: bool = True):
        d = {
                "name": self.name,
                "binary": self.binary,
                "size_bytes": self.size,
                "data": b''
            }
        if include_data:
            d['data'] = self.data
        return d

class ObjectAttachment(Attachment):
    def __init__(self, name: str, obj: Object):
        self.object = obj
        super().__init__(name, "")

    @property
    def size(self) -> int:
        return self.object.size

    @property
    def data(self) -> Union[str,bytes]:
        return self.object.data

    @property
    def binary(self) -> bool:
        return self.object.binary


class MessageTextTooLongError(Exception):
    """Raised when the message text exceeds the length allowed in the server config."""
    pass

class MessageAlreadySentError(Exception):
    """Raised when the message text exceeds the length allowed in the server config."""
    pass

class Message(persistent.Persistent):
    def __init__(self, text: str, msg_to: Optional[Iterable[str]]= None, msg_from: Optional[str] = None,
                 attachments: Optional[Iterable[Attachment]] = None):
        self.retrieved = False
        self.sent_at = datetime.datetime.now(datetime.UTC)
        self.text = text
        self.attachments = ()
        self.msg_to = (None,)
        self.msg_from = None
        self.msg_id = uuid.uuid4()
        self.msg_delivered = False
        if msg_to:
            if type(msg_to) is str:
                msg_to = msg_to.upper().strip()
                self.msg_to = (msg_to,)
            else:
                msg_to_tmp = []
                for i in msg_to:
                    i = str(i).strip().upper()
                    if i == "ALL":
                        msg_to_tmp = ["ALL"]
                        break
                    else:
                        msg_to_tmp.append(i)
                self.msg_to = tuple(msg_to_tmp)
        if msg_from:
            self.msg_from = str(msg_from).upper().strip()

        if attachments:
            attch = []
            for i in attachments:
                if type(i) is Attachment:
                    attch.append(i)
                elif type(i) is dict:
                    attch.append(Attachment.from_dict(i))
                elif not isinstance(i,Attachment):
                    attch.append(Attachment("",str(i)))
                else:
                    attch.append(i)
            self.attachments = tuple(attch)
    def __repr__(self):
        return f"<Message: ID: {self.msg_id}, Sent: {self.msg_delivered}>"

    def to_dict(self, get_text: bool = True, get_attachments: bool = True) -> dict:
        attachments = []
        for attachment in self.attachments:
            attachments.append(attachment.to_dict(include_data=get_attachments))
        d = {
                "attachments": attachments,
                "to": self.msg_to,
                "from": self.msg_from,
                "id": str(self.msg_id),
                "sent_at": self.sent_at.isoformat(),
                "text": ""
            }
        if get_text:
            d['text'] = self.text
        
        return d

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        return Message(data['text'],msg_to=data.get('to'), attachments=data.get("attachments"))

    def send(self, db: ZODB.DB) -> tuple:
        if self.msg_delivered:
            raise MessageAlreadySentError("Cannot send a private message that has already been sent.")
        if self.msg_from is None:
            raise ValueError("Message sender (message_from) cannot be None.")
        new_attachments = []
        for i in self.attachments:
            if isinstance(i,ObjectAttachment):
                logging.debug("Skpping object attachments for now. Resolve db queries for them at send time.")
                # new_attachments.append(Attachment(i.name, i.data)) TODO send object attachments
                pass
            else:
                new_attachments.append(i)
        send_counter = 0
        recipients = []
        failed = []
        to_all = False
        with db.transaction() as db:
            mailbox_create(self.msg_from, db.root())
            self.msg_id = global_unique_message_uuid(db.root())
            for recipient in self.msg_to:
                recipient = recipient.upper().strip()
                if recipient is None:
                    continue
                if recipient == "ALL":
                    recipients = [x for x in db.root.users if db.root.users[x].enabled]
                    to_all = True
                    break
                recipients.append(recipient)
            if self.msg_from.upper().strip() in recipients:
                recipients.remove(self.msg_from.upper().strip())
                send_counter = send_counter + 1
            for recipient in recipients:
                msg = Message(self.text, recipient, self.msg_from, attachments=[x.copy() for x in new_attachments])
                try:
                    mailbox_create(recipient, db.root())
                    msg.msg_delivered = True
                    msg.sent_at = datetime.datetime.now(datetime.UTC)
                    if to_all:
                        msg.msg_to = 'ALL'
                    db.root.messages[recipient].append(msg)
                    send_counter = send_counter + 1
                except:
                    logging.error(f"Error sending message to {recipient}:\n{format_exc()}")
                    failed.append(recipient)
        self.msg_delivered = True
        self.attachments = [x.copy() for x in new_attachments]
        db.root.messages[self.msg_from.upper().strip()].append(msg)
        return send_counter, failed, self.msg_id

DisplayOptions = namedtuple('DisplayOptions', ['get_text', 'limit', 'sort_by', 'reverse', 'search',
                                               'get_attachments', 'sent_received_all'])

def parse_display_options(req: Request) -> DisplayOptions:
    logging.debug(f"Parsing request vars for message get: {req.vars}")
    sent_received_all = "received"
    d = req.vars.get("source")
    if type(d) is str:
        d.lower().strip()
    if d == "sent":
        sent_received_all = "sent"
    elif d == "all":
        sent_received_all = "all"

    limit = req.vars.get('limit')
    try:
        limit = int(limit)
    except:
        limit = None

    d = req.vars.get('fetch_text')
    if type(d) is str:
        d.lower().strip()
    if d in no_values:
        get_text = False
    else:
        get_text = True

    d = req.vars.get('fetch_attachments')
    logging.debug(f"Parsing fetch_attachment var: {d}")
    if type(d) is str:
        d.lower().strip()
    if d in yes_values:
        logging.debug("fetch_attachment is yes")
        get_attachments = True
    else:
        get_attachments = False
        logging.debug("fetch_attachment is no")

    r = req.vars.get('reverse')
    if type(r) is str:
        r.lower().strip()
    if r in yes_values:
        reverse = True
    else:
        reverse = False

    sort = req.vars.get('sort')
    sort_by = "date"
    if type(sort) is str:
        sort = sort.lower().strip()
        if sort == "from":
            sort_by = "from"
        elif sort == "to":
            sort_by = "to"

    s = req.vars.get('search')
    search = None
    if type(s) is str:
       s = s.lower()
    if s:
        search = str(s).lower()

    return DisplayOptions(get_text, limit, sort_by, reverse, search, get_attachments, sent_received_all)

def handle_messages_since(req: Request, conn: PacketServerConnection, db: ZODB.DB):
    if req.method is not Request.Method.GET:
        send_blank_response(conn, req, 400, "method not implemented")
        logging.warning(f"Received req with wrong message for path {req.path}.")
        return
    try:
        since_date = from_date_digits(req.vars['since'])
    except ValueError as v:
        send_blank_response(conn, req, 400, "invalid date string")
        return
    except:
        send_blank_response(conn, req, 500, "unknown error")
        logging.error(f"Unhandled exception: {format_exc()}")
        return
    opts = parse_display_options(req)
    username = ax25.Address(conn.remote_callsign).call.upper().strip()
    msg_return = []
    with db.transaction() as db:
        mailbox_create(username, db.root())
        mb = db.root.messages[username]
        new_mb = [msg for msg in mb if msg.sent_at >= since_date]
        if opts.search:
            messages = [msg for msg in new_mb if (opts.search in msg.text.lower()) or (opts.search in msg.msg_to[0].lower())
                        or (opts.search in msg.msg_from.lower())]
        else:
            messages = [msg for msg in mb]

        if opts.sort_by == "from":
            messages.sort(key=lambda x: x.msg_from, reverse=opts.reverse)
        elif opts.sort_by == "to":
            messages.sort(key=lambda x: x.msg_to, reverse=opts.reverse)
        else:
            messages.sort(key=lambda x: x.sent_at, reverse=opts.reverse)

        for i in range(0, len(messages)):
            if opts.limit and (len(msg_return) >= opts.limit):
                break

            msg = messages[i]
            msg.retrieved = True
            msg_return.append(msg.to_dict(get_text=opts.get_text, get_attachments=opts.get_attachments))

    response = Response.blank()
    response.status_code = 200
    response.payload = msg_return
    send_response(conn, response, req)

def handle_message_get_id(req: Request, conn: PacketServerConnection, db: ZODB.DB):
    uuid_val = req.vars['id']
    obj_uuid = None
    try:
        if type(uuid_val) is bytes:
            obj_uuid = UUID(bytes=uuid_val)
        elif type(uuid_val) is int:
            obj_uuid = UUID(int=uuid_val)
        elif type(uuid_val) is str:
            obj_uuid = UUID(uuid_val)
    except:
        pass
    if obj_uuid is None:
        send_blank_response(conn, req, 400)
        return
    opts = parse_display_options(req)
    username = ax25.Address(conn.remote_callsign).call.upper().strip()
    msg = None
    with db.transaction() as db:
        mailbox_create(username, db.root())
        for m in db.root.messages[username]:
            if m.msg_id == obj_uuid:
                msg = m
                break
    if msg is None:
        send_blank_response(conn, req, status_code=404)
        return
    else:
        send_blank_response(conn, req,
                            payload=msg.to_dict(get_text=opts.get_text, get_attachments=opts.get_attachments))

def handle_message_get(req: Request, conn: PacketServerConnection, db: ZODB.DB):
    if 'id' in req.vars:
        return handle_message_get_id(req, conn, db)

    if 'since' in req.vars:
        return handle_messages_since(req, conn, db)

    opts = parse_display_options(req)
    username = ax25.Address(conn.remote_callsign).call.upper().strip() 
    msg_return = []
    with db.transaction() as db:
        mailbox_create(username, db.root())
        mb = db.root.messages[username]
        if opts.search:
            messages = [msg for msg in mb if (opts.search in msg.text.lower()) or (opts.search in msg.msg_to[0].lower())
                        or (opts.search in msg.msg_from.lower())]
        else:
            messages = [msg for msg in mb]

        if opts.sort_by == "from":
            messages.sort(key=lambda x: x.msg_from, reverse=opts.reverse)
        elif opts.sort_by == "to":
            messages.sort(key=lambda x: x.msg_to, reverse=opts.reverse)
        else:
            messages.sort(key=lambda x: x.sent_at, reverse=opts.reverse)

        for i in range(0, len(messages)):
            if opts.limit and (len(msg_return) >= opts.limit):
                break

            msg = messages[i]
            msg.retrieved = True
            msg_return.append(msg.to_dict(get_text=opts.get_text, get_attachments=opts.get_attachments))

    response = Response.blank()
    response.status_code = 200
    response.payload = msg_return
    send_response(conn, response, req)

def handle_message_post(req: Request, conn: PacketServerConnection, db: ZODB.DB):
    username = ax25.Address(conn.remote_callsign).call.upper().strip()
    try:
        msg = Message.from_dict(req.payload)
    except:
        send_blank_response(conn, req, status_code=400)
        logging.warning(f"User '{username}' attempted to post message with invalid payload: {req.payload}")
        return
    msg.msg_from = username
    try:
        send_counter, failed, msg_id = msg.send(db)
    except:
        send_blank_response(conn, req, status_code=500)
        logging.error(f"Error while attempting to send message:\n{format_exc()}")
        return

    send_blank_response(conn, req, status_code=201, payload={
        "successes": send_counter,
        "failed": failed,
        'msg_id': msg_id})

def message_root_handler(req: Request, conn: PacketServerConnection, db: ZODB.DB):
    logging.debug(f"{req} being processed by message_root_handler")
    if not user_authorized(conn, db):
        logging.debug(f"user {conn.remote_callsign} not authorized")
        send_blank_response(conn, req, status_code=401)
        return
    logging.debug("user is authorized")
    if req.method is Request.Method.GET:
        handle_message_get(req, conn, db)
    elif req.method is Request.Method.POST:
        handle_message_post(req, conn, db)
    else:
        send_blank_response(conn, req, status_code=404)



