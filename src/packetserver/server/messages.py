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
import ZODB
import logging
import uuid
from uuid import UUID
from packetserver.common.util import email_valid
from packetserver.server.objects import Object
from BTrees.OOBTree import TreeSet
from packetserver.server.users import User, user_authorized
from traceback import format_exc
from collections import namedtuple


def mailbox_create(username: str, db_root: PersistentMapping):
    un = username.upper().strip()
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
    def __init__(self, text: str, msg_to: Optional[Iterable[str],str]= None, msg_from: Optional[str] = None,
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
                if not isinstance(i,Attachment):
                    attch.append(Attachment("",str(i)))
                else:
                    attch.append(i)
            self.attachments = tuple(attch)
    def __repr__(self):
        return f"<Message: ID: {self.msg_id}, Sent: {self.msg_delivered}>"

    def send(self, db: ZODB.DB) -> tuple:
        if self.msg_delivered:
            raise MessageAlreadySentError("Cannot send a private message that has already been sent.")
        if self.msg_from is None:
            raise ValueError("Message sender (message_from) cannot be None.")
        new_attachments = []
        for i in self.attachments:
            if isinstance(i,ObjectAttachment):
                new_attachments.append(Attachment(i.name, i.data))
            else:
                new_attachments.append(i)
        send_counter = 0
        recipients = []
        failed = []
        to_all = False
        with db.transaction() as db:
            for recipient in self.msg_to:
                recipient = recipient.upper().strip()
                if recipient is None:
                    continue
                if recipient == "ALL":
                    recipients = [x for x in db.root.users if db.root.users[x].enabled]
                    to_all = True
                    break
                recipients.append(recipient)
            for recipient in recipients:
                msg = Message(self.text, recipient, self.msg_from, attachments=[x.copy() for x in new_attachments])
                try:
                    mailbox_create(recipient, db.root())
                    msg.msg_id = global_unique_message_uuid(db.root())
                    msg.msg_delivered = True
                    msg.sent_at = datetime.datetime.now(datetime.UTC)
                    if to_all:
                        msg.msg_to = 'ALL'
                    db.root.messages[recipient].append(msg)
                    send_counter = send_counter + 1
                except:
                    logging.error(f"Error sending message to {recipient}:\n{format_exc()}")
                    failed.append(recipient)

        return send_counter, failed

DisplayOptions = namedtuple('DisplayOptions', ['get_text', 'limit', 'sort_by', 'reverse', 'search',
                                               'get_attachments', 'sent_received_all'])

def parse_display_options(req: Request) -> DisplayOptions:
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
    if type(d) is str:
        d.lower().strip()
    if d in yes_values:
        get_attachments = True
    else:
        get_attachments = False

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
        search = str(s)

    return DisplayOptions(get_text, limit, sort_by, reverse, search, get_attachments, sent_receive_all)


def handle_message_get(req: Request, conn: PacketServerConnection, db: ZODB.DB):
    opts = parse_display_options(req)
    

def object_root_handler(req: Request, conn: PacketServerConnection, db: ZODB.DB):
    logging.debug(f"{req} being processed by user_root_handler")
    if not user_authorized(conn, db):
        logging.debug(f"user {conn.remote_callsign} not authorized")
        send_blank_response(conn, req, status_code=401)
        return
    logging.debug("user is authorized")
    if req.method is Request.Method.GET:
        handle_message_get(req, conn, db)
    else:
        send_blank_response(conn, req, status_code=404)



