import persistent
import persistent.list
from persistent.mapping import PersistentMapping
import datetime
from typing import Self,Union,Optional
from packetserver.common import PacketServerConnection, Request, Response, Message
from packetserver.server import Server
from packetserver.server.requests import send_404
import ZODB
import logging

def init_bulletins(root: PersistentMapping):
    if 'bulletins' not in root:
        root['bulletins'] = persistent.list.PersistentList()
    if 'bulletin_counter' not in root:
        root['bulletin_counter'] = 0

def get_new_bulletin_id(root: PersistentMapping) -> int:
    if 'bulletin_counter' not in root:
        root['bulletin_counter'] = 1
        return 0
    else:
        current = root['bulletin_counter']
        root['bulletin_counter'] = current + 1
        return current

class Bulletin(persistent.Persistent):
    @classmethod
    def get_bulletin_by_id(cls, bid: int, db_root: PersistentMapping) -> Optional[Self]:
        for bull in db_root['bulletins']:
            if bull.id == bid:
                return bull
        return None

    def __init__(self, author: str, subject: str, text: str):
        self.author = author
        self.subject = subject
        self.body = text
        self.created_at = None
        self.updated_at = None
        self.id = None

    @classmethod
    def from_dict(cls, bulletin_dict: dict) -> Self:
        return Bulletin(bulletin_dict['author'], bulletin_dict['subject'], bulletin_dict['body'])

    def write_new(self, db_root: PersistentMapping):
        if self.id is None:
            self.id = get_new_bulletin_id(db_root)
            self.created_at = datetime.datetime.now(datetime.UTC)
            self.updated_at = datetime.datetime.now(datetime.UTC)
            db_root['bulletins'].append(self)

    def update_subject(self, new_text: str):
        self.subject = new_text
        self.updated_at = datetime.datetime.now(datetime.UTC)

    def update_body(self, new_text: str):
        self.body = new_text
        self.updated_at = datetime.datetime.now(datetime.UTC)

    def to_dict(self):
        return {
            "id": self.id,
            "author": self.author,
            "subject": self.subject,
            "body": self.body,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }

def handle_bulletin_get(req: Request, conn: PacketServerConnection, server: Server):
    response = Response.blank()
    with server.db.transaction() as db:
        pass
    return response

def handle_bulletin_post(req: Request, conn: PacketServerConnection, server: Server):
    response = Response.blank()
    with server.db.transaction() as db:
        pass
    return response

def handle_bulletin_update(req: Request, conn: PacketServerConnection, server: Server):
    response = Response.blank()
    with server.db.transaction() as db:
        pass
    return response

def handle_bulletin_delete(req: Request, conn: PacketServerConnection, server: Server):
    response = Response.blank()
    with server.db.transaction() as db:
        pass
    return response

def bulletin_root_handler(req: Request, conn: PacketServerConnection, server: Server):
    logging.debug(f"{req} being processed by bulletin_root_handler")
    if req.method is Request.Method.GET:
        handle_bulletin_get(req, conn, server)
    else:
        send_404(conn)
