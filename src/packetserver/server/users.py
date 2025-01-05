"""Module containing code related to users."""

import ax25
import persistent
import persistent.list
from persistent.mapping import PersistentMapping
import datetime
from typing import Self,Union,Optional
from packetserver.common import PacketServerConnection, Request, Response, Message, send_response, send_blank_response
import ZODB
import logging
import uuid
from uuid import UUID

class User(persistent.Persistent):
    def __init__(self, username: str, enabled: bool = True, hidden: bool = False, bio: str = "", status: str = ""):
        self._username = username.upper().strip()
        self.enabled = enabled
        self.hidden = hidden
        self.created_at = datetime.datetime.now(datetime.UTC)
        self.last_seen = self.created_at
        self._uuid = None
        if len(bio) > 4000:
            self._bio = bio[:4000]
        else:
            self._bio = bio
        if len(status) > 300:
            self._status = status[:300]
        else:
            self._status = status

    def write_new(self, db_root: PersistentMapping):
        all_uuids = [db_root['users'][x].uuid for x in db_root['users']]
        self._uuid = uuid.uuid4()
        while self.uuid in all_uuids:
            self._uuid = uuid.uuid4()
        logging.debug(f"Creating new user account {self.username} - {self.uuid}")
        if self.username not in db_root['users']:
            db_root['users'][self.username] = self

    @property
    def uuid(self):
        return self._uuid

    @classmethod
    def get_user_by_username(cls, username: str, db_root: PersistentMapping) -> Self:
        try:
            if username.upper().strip() in db_root['users']:
                return db_root['users'][username.upper().strip()]
        except Exception:
            return None
        return None

    @classmethod
    def get_user_by_uuid(cls, user_uuid: Union[UUID, bytes, int, str], db_root: PersistentMapping) -> Self:
        try:
            if type(uuid) is uuid.UUID:
                uid = user_uuid
            elif type(uuid) is bytes:
                uid = uuid.UUID(bytes=user_uuid)
            elif type(uuid) is int:
                uid = uuid.UUID(int=user_uuid)
            else:
                uid = uuid.UUID(str(user_uuid))
            for user in db_root['users']:
                if uid == db_root['users'][user].uuid:
                    return db_root['users'][user].uuid
        except Exception:
            return None
        return None

    @classmethod
    def get_all_users(cls, db_root: PersistentMapping, limit: int = None) -> list:
        all_users = sorted(db_root['users'].values(), key=lambda user: user.username)
        if not limit:
            return all_users
        else:
            if len(all_users) < limit:
                return all_users
            else:
                return all_users[:limit]

    def seen(self):
        self.last_seen = datetime.datetime.now(datetime.UTC)

    @property
    def username(self) -> str:
        return self._username.upper().strip()

    @property
    def bio(self) -> str:
        return self._bio

    @bio.setter
    def bio(self, bio: str):
        if len(bio) > 4000:
            self._bio = bio[:4000]
        else:
            self._bio = bio

    @property
    def status(self) -> str:
        return self._status

    @status.setter
    def status(self, status: str):
        if len(status) > 300:
            self._status = status[:300]
        else:
            self._status = status

    def to_safe_dict(self) -> dict:
        return {
            "username": self.username,
            "status": self.status,
            "bio": self.bio,
            "last_seen": self.last_seen.isoformat(),
            "created_at": self.created_at.isoformat()
        }

def handle_user_get(req: Request, conn: PacketServerConnection, db: ZODB.DB):
    sp = req.path.split("/")
    logging.debug("handle_user_get working")
    user = None
    user_var = req.vars.get('username')
    response = Response.blank()
    response.status_code = 404
    limit = None
    if 'limit' in req.vars:
        try:
            limit = int(req.vars['limit'])
        except ValueError:
            pass
    with db.transaction() as db:
        if len(sp) > 1:
            logging.debug(f"trying to get the username from the path {sp[1].strip().upper()}")
            user = User.get_user_by_username(sp[1].strip().upper(), db.root())
            logging.debug(f"user holds: {user}")
            if user and not user.hidden:
                response.status_code = 200
                response.payload = user.to_safe_dict()
            else:
                if user_var:
                    user = User.get_user_by_username(user_var.upper().strip(), db.root())
                    if user and not user.hidden:
                        response.status_code = 200
                        response.payload = user.to_safe_dict()
        else:
            if user_var:
                user = User.get_user_by_username(user_var.upper().strip(), db.root())
                if user and not user.hidden:
                    response.status_code = 200
                    response.payload = user.to_safe_dict()
            else:
                response.status_code = 200
                response.payload = [x.to_safe_dict() for x in User.get_all_users(db.root(), limit=limit) if not x.hidden]
    send_response(conn, response, req)

def handle_user_update(req: Request, conn: PacketServerConnection, db: ZODB.DB): # TODO
    pass

def user_root_handler(req: Request, conn: PacketServerConnection, db: ZODB.DB):
    logging.debug(f"{req} being processed by user_root_handler")
    if req.method is Request.Method.GET:
        handle_user_get(req, conn, db)
    else:
        send_blank_response(conn, req, status_code=404)
