import ax25
import persistent
import persistent.list
from persistent.mapping import PersistentMapping
import datetime
from typing import Self,Union,Optional
from packetserver.common import PacketServerConnection, Request, Response, Message, send_response, send_blank_response
import ZODB
import logging

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

    @classmethod
    def get_recent_bulletins(cls, db_root: PersistentMapping, limit: int = None) -> list:
        all_bulletins = sorted(db_root['bulletins'], key=lambda bulletin: bulletin.updated_at, reverse=True)
        if not limit:
            return all_bulletins
        else:
            if len(all_bulletins) < limit:
                return all_bulletins
            else:
                return all_bulletins[:limit]

    def __init__(self, author: str, subject: str, text: str):
        self.author = author
        self.subject = subject
        self.body = text
        self.created_at = datetime.datetime.now(datetime.UTC)
        self.updated_at = datetime.datetime.now(datetime.UTC)
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


def handle_bulletin_get(req: Request, conn: PacketServerConnection, db: ZODB.DB):
    response = Response.blank()
    sp = req.path.split("/")
    logging.debug(f"bulletin get path: {sp}")
    bid = None
    limit = None
    if 'limit' in req.vars:
        try:
            limit = int(req.vars['limit'])
        except ValueError:
            pass
    if 'id' in req.vars:
        try:
            bid = int(req.vars['id'])
        except ValueError:
            pass
    if len(sp) > 1:
        logging.debug(f"checking path for bulletin id")
        try:
            logging.debug(f"{sp[1]}")
            bid = int(sp[1].strip())
        except ValueError:
            pass
    logging.debug(f"bid is {bid}")

    with db.transaction() as db:
        if bid is not None:
            logging.debug(f"retrieving bulletin: {bid}")
            bull = Bulletin.get_bulletin_by_id(bid, db.root())
            if bull:
                response.payload = bull.to_dict()
                response.status_code = 200
            else:
                response.status_code = 404
        else:
            logging.debug(f"retrieving all bulletins")
            bulls = Bulletin.get_recent_bulletins(db.root(), limit=limit)
            response.payload = [bulletin.to_dict() for bulletin in bulls]
            response.status_code = 200

    send_response(conn, response, req)

def handle_bulletin_post(req: Request, conn: PacketServerConnection, db: ZODB.DB):
    author = ax25.Address(conn.remote_callsign).call
    if type(req.payload) is not dict:
        send_blank_response(conn, req, 400, payload="Include dict in payload with subject and body")
    if 'subject' not in req.payload:
        send_blank_response(conn, req, 400, payload="Include dict in payload with subject and body")
    if 'body' not in req.payload:
        send_blank_response(conn, req, 400, payload="Include dict in payload with subject and body")
    b = Bulletin(author, str(req.payload['subject']), str(req.payload['body']))
    response = Response.blank()
    with db.transaction() as db:
        b.write_new(db.root())
    send_blank_response(conn, req, status_code=201)

def handle_bulletin_update(req: Request, conn: PacketServerConnection, db: ZODB.DB): # TODO
    response = Response.blank()
    with db.transaction() as db:
        pass
    send_response(conn, response, req)

def handle_bulletin_delete(req: Request, conn: PacketServerConnection, db: ZODB.DB): # TODO
    response = Response.blank()
    with db.transaction() as db:
        pass
    send_response(conn, response, req)

def bulletin_root_handler(req: Request, conn: PacketServerConnection, db: ZODB.DB):
    logging.debug(f"{req} being processed by bulletin_root_handler")
    if req.method is Request.Method.GET:
        handle_bulletin_get(req, conn, db)
    elif req.method is Request.Method.POST:
        handle_bulletin_post(req, conn, db)
    else:
        send_blank_response(conn, req, status_code=404)
