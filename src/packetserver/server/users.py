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
from packetserver.common.util import email_valid

class User(persistent.Persistent):
    def __init__(self, username: str, enabled: bool = True, hidden: bool = False, bio: str = "", status: str = "",
                 email: str = None, location: str = "", socials: list[str] = None):
        self._username = username.upper().strip()
        self.enabled = enabled
        self.hidden = hidden
        self.created_at = datetime.datetime.now(datetime.UTC)
        self.last_seen = self.created_at
        self._email = ""
        if email:
            self.email = email
        self._location = ""
        self.location = location
        self._socials = []
        if socials:
            self.socials = socials
        self._uuid = None
        self.bio = bio
        self._status = ""
        self.status = status

    def write_new(self, db_root: PersistentMapping):
        all_uuids = [db_root['users'][x].uuid for x in db_root['users']]
        self._uuid = uuid.uuid4()
        while self.uuid in all_uuids:
            self._uuid = uuid.uuid4()
        logging.debug(f"Creating new user account {self.username} - {self.uuid}")
        if self.username not in db_root['users']:
            db_root['users'][self.username] = self

    @property
    def location(self) -> str:
        return self._location

    @location.setter
    def location(self, location: str):
        if len(location) > 1000:
            self._location = location[:1000]
        else:
            self._location = location

    @property
    def email(self) -> str:
        return self._email

    @email.setter
    def email(self, email: str):
        if email_valid(email.strip().lower()):
            self._email = email.strip().lower()
        else:
            raise ValueError(f"Invalid e-mail given: {email}")

    @property
    def socials(self) -> list[str]:
        return []

    @socials.setter
    def socials(self, socials: list[str]):
        for social in socials:
            if len(social) > 300:
                social = social[:300]
            self._socials.append(social)

    def add_social(self, social: str):
        if len(social) > 300:
            social = social[:300]
        self._socials.append(social)

    def remove_social(self, social: str):
        self.socials.remove(social)

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

    @classmethod
    def is_authorized(cls, username: str, db_root: PersistentMapping) -> bool:
        user = User.get_user_by_username(username, db_root)
        if user:
            if user.enabled:
                return True
        return False

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
            "socials": self.socials,
            "email": self.email,
            "location": self.location,
            "last_seen": self.last_seen.isoformat(),
            "created_at": self.created_at.isoformat()
        }

    def __repr__(self):
        return f"<User: {self.username} - {self.uuid}>"

def user_authorized(conn: PacketServerConnection, db: ZODB.DB) -> bool:
    username = ax25.Address(conn.remote_callsign).call
    logging.debug(f"Running authcheck for user {username}")
    result = False
    with db.transaction() as db:
        result = User.is_authorized(username, db.root())
        logging.debug(f"User is authorized? {result}")
    return result

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
    if not user_authorized(conn, db):
        logging.debug(f"user {conn.remote_callsign} not authorized")
        send_blank_response(conn, req, status_code=401)
        return
    logging.debug("user is authorized")
    if req.method is Request.Method.GET:
        handle_user_get(req, conn, db)
    else:
        send_blank_response(conn, req, status_code=404)
