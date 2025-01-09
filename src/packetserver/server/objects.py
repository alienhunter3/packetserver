"""Server object storage system."""
from copy import deepcopy

import persistent
import ax25
import persistent.list
from persistent.mapping import PersistentMapping
import datetime
from typing import Self,Union,Optional
from packetserver.common import PacketServerConnection, Request, Response, Message, send_response, send_blank_response
import ZODB
import logging
import uuid
from uuid import UUID
from packetserver.server.users import User, user_authorized
from collections import namedtuple
from traceback import format_exc
import base64

class Object(persistent.Persistent):
    def __init__(self, name: str = "", data: Union[bytes,bytearray,str] = None):
        self.private = False
        self._binary = False
        self._data = b''
        self._name = ""
        self._owner = None
        if data:
            self.data = data
        if name:
            self._name = name
        self._uuid = None
        self.created_at = datetime.datetime.now(datetime.UTC)
        self.modified_at = datetime.datetime.now(datetime.UTC)


    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, name: str):
        if name.strip() != self._name:
            if len(name.strip()) > 300:
                raise ValueError("Object names must be no more than 300 characters.")
            self._name = name.strip()
            self.touch()

    def touch(self):
        self.modified_at = datetime.datetime.now(datetime.UTC)

    @property
    def size(self) -> int:
        return len(self.data)

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
                self.touch()
        else:
            if str(data).encode() != self._data:
                self._data = str(data).encode()
                self._binary = False
                self.touch()

    @property
    def owner(self) -> Optional[UUID]:
        return self._owner

    @owner.setter
    def owner(self, owner_uuid: UUID):
        if owner_uuid:
            if type(owner_uuid) is UUID:
                self._owner = owner_uuid
                self.touch()
            else:
                raise ValueError("Owner must be a UUID")
        else:
            self._owner = None
            self.touch()

    def chown(self, username: str, db: ZODB.DB):
        logging.debug(f"chowning object {self} to user {username}")
        un = username.strip().upper()
        old_owner_uuid = self._owner
        with db.transaction() as db:
            user = User.get_user_by_username(username, db.root())
            old_owner = User.get_user_by_uuid(old_owner_uuid, db.root())
            if user:
                logging.debug(f"new owner user exists: {user}")
                db.root.objects[self.uuid].owner = user.uuid
                if old_owner_uuid:
                    if old_owner:
                        old_owner.remove_obj_uuid(self.uuid)
                logging.debug("adding object uuid to user objects set")
                user.add_obj_uuid(self.uuid)
                logging.debug(f"user objects now: {user.object_uuids}")
            else:
                raise KeyError(f"User '{un}' not found.")

    @classmethod
    def get_object_by_uuid(cls, obj: UUID, db_root: PersistentMapping):
        return db_root['objects'].get(obj)

    @classmethod
    def get_objects_by_username(cls, username: str, db: ZODB.DB) -> list[Self]:
        un = username.strip().upper()
        objs = []
        with db.transaction() as db:
            user = User.get_user_by_username(username, db.root())
            if user:
                uuids = user.object_uuids
                for u in uuids:
                    try:
                        obj = cls.get_object_by_uuid(u, db)
                        if obj:
                            objs.append(obj)
                    except:
                        pass
        return objs

    @property
    def uuid(self) -> Optional[UUID]:
        return self._uuid

    def write_new(self, db: ZODB.DB) -> UUID:
        if self.uuid:
            raise KeyError("Object already has UUID. Manually clear it to write it again.")
        self._uuid = uuid.uuid4()
        with db.transaction() as db:
            while self.uuid in db.root.objects:
                self._uuid = uuid.uuid4()
            db.root.objects[self.uuid] = self
            self.touch()
        return self.uuid

    def to_dict(self, include_data: bool = True) -> dict:
        data = b''
        if include_data:
            data = self.data
        if self.uuid:
            uuid_bytes = self.uuid.bytes
        else:
            uuid_bytes = None

        return {
            "name": self.name,
            "uuid_bytes": uuid_bytes,
            "size_bytes": self.size,
            "binary": self.binary,
            "private": self.private,
            "created_at": self.created_at.isoformat(),
            "modified_at": self.modified_at.isoformat(),
            "includes_data": include_data,
            "data": data
        }

    @classmethod
    def from_dict(cls, obj: dict) -> Self:
        o = Object(name=obj['name'])
        if obj['uuid_bytes']:
            o._uuid = UUID(bytes=obj['uuid_bytes'])
        o.private = obj['private']
        o.data = obj['data']
        o._binary = obj['binary']
        return o

    def authorized_write(self, username: str, db: ZODB.DB):
        un = username.strip().upper()
        with db.transaction() as db:
            user = User.get_user_by_username(username, db.root())
            if user:
                if user.uuid == self.owner:
                    return True
            else:
                return False

    def authorized_get(self, username: str, db: ZODB.DB):
        if not self.private:
            return True
        un = username.strip().upper()
        with db.transaction() as db:
            user = User.get_user_by_username(username, db.root())
            if user:
                if user.uuid == self.owner:
                    return True
            else:
                return False

    def __repr__(self):
        return f"<Object: '{self.name}', {self.size}b, {self.uuid}>"

DisplayOptions = namedtuple('DisplayOptions', ['get_data', 'limit', 'sort_by', 'reverse', 'search'])

def parse_display_options(req: Request) -> DisplayOptions:
    limit = req.vars.get('limit')
    try:
        limit = int(limit)
    except:
        limit = None

    d = req.vars.get('fetch')
    if type(d) is str:
        d.lower().strip()
    if d in [1, 'y', True, 'yes', 'true', 't']:
        get_data = True
    else:
        get_data = False

    r = req.vars.get('reverse')
    if type(r) is str:
        r.lower().strip()
    if r in [1, 'y', True, 'yes', 'true', 't']:
        reverse = True
    else:
        reverse = False

    sort = req.vars.get('sort')
    sort_by = "name"
    if type(sort) is str:
        sort = sort.lower().strip()
        if sort == "date":
            sort_by = "date"
        elif sort == "size":
            sort_by = "size"

    s = req.vars.get('search')
    search = None
    if type(s) is str:
       s = s.lower()
    if s:
        search = str(s)

    return DisplayOptions(get_data, limit, sort_by, reverse, search)

def object_display_filter(source: list[Object], opts: DisplayOptions) -> list[dict]:
    if opts.search:
        objs = [x for x in source if str(opts.search) in x.name.lower()]
    else:
        objs = deepcopy(source)

    if opts.sort_by == "size":
        objs.sort(key=lambda x: x.size, reverse=opts.reverse)

    elif opts.sort_by == "date":
        objs.sort(key=lambda x: x.modified_at, reverse=opts.reverse)
    else:
        objs.sort(key=lambda x: x.name, reverse=opts.reverse)

    if opts.limit:
        if len(objs) >= opts.limit:
            objs = objs[:opts.limit]

    return [o.to_dict(include_data=opts.get_data) for o in objs]

def handle_get_no_path(req: Request, conn: PacketServerConnection, db: ZODB.DB):
    opts = parse_display_options(req)
    logging.debug(f"Handling a GET 'object' request: {opts}")
    response = Response.blank()
    response.status_code = 404
    username = ax25.Address(conn.remote_callsign).call.upper().strip()
    with db.transaction() as db:
        user = User.get_user_by_username(username, db.root())
        if not user:
            send_blank_response(conn, req, status_code=500, payload="Unknown user account problem")
            return
        if 'uuid' in req.vars:
            logging.debug(f"uuid req.var: {req.vars['uuid']}")
            uid = req.vars['uuid']
            if type(uid) is bytes:
                obj = Object.get_object_by_uuid(UUID(bytes=uid), db.root())
                if obj:
                    if not obj.owner == user.uuid:
                        if not obj.private:
                            send_blank_response(conn, req, status_code=401)
                            return
                    if opts.get_data:
                        response.payload = obj.to_dict()
                        response.status_code = 200
                    else:
                        response.payload = obj.to_dict(include_data=False)
                        response.status_code = 200
        else:
            uuids = user.object_uuids
            objs = []
            logging.debug(f"No uuid var, all user object_uuids: {uuids}")
            for i in uuids:
                obj = Object.get_object_by_uuid(i, db.root())
                logging.debug(f"Checking {obj}")
                if not obj.private:
                    logging.debug("object not private")
                    objs.append(obj)
                else:
                    logging.debug("object private")
                    if obj.uuid == user.uuid:
                        logging.debug("user uuid matches object uuid")
                        objs.append(obj)
            response.payload = object_display_filter(objs, opts)
            logging.debug(f"object payload: {response.payload}")
            response.status_code = 200

        send_response(conn, response, req)

def handle_object_get(req: Request, conn: PacketServerConnection, db: ZODB.DB):
    # Case: User searching their own objects -> list
    # or passes specific UUID as var -> Object
    handle_get_no_path(req, conn, db)


def handle_object_post(req: Request, conn: PacketServerConnection, db: ZODB.DB):
    if type(req.payload) is not dict:
        send_blank_response(conn, req, 400, payload="object payload must be 'dict'")

    try:
        obj = Object.from_dict(req.payload)
    except:
        logging.debug(f"Error parsing new object:\n{format_exc()}")
        send_blank_response(conn, req, status_code=400)
        retur
    logging.debug(f"writing new object: {obj}")
    obj.write_new(db)
    with db.transaction() as db_conn:
        logging.debug(f"looking up new object")
        new_obj = Object.get_object_by_uuid(obj.uuid, db_conn.root())
    username = ax25.Address(conn.remote_callsign).call.upper().strip()
    logging.debug("chowning new object")
    new_obj.chown(username, db)
    send_blank_response(conn, req, status_code=201, payload=str(obj.uuid))

def handle_object_update(req: Request, conn: PacketServerConnection, db: ZODB.DB):
    username = ax25.Address(conn.remote_callsign).call.upper().strip()
    if type(req.payload) is not dict:
        send_blank_response(conn, req, status_code=400)
        return
    if 'uuid' in req.vars:
        uid = req.vars['uuid']
        if type(uid) is bytes:
            u_obj = UUID(bytes=uid)
        elif type(uid) is int:
            u_obj = UUID(int=uid)
        else:
            try:
                u_obj = UUID(str(uid))
            except ValueError:
                send_blank_response(conn, req, status_code=400)
        new_name = req.payload.get("name")
        new_data = req.payload.get("data")
        if new_data:
            if type(new_data) not in (bytes, bytearray, str):
                send_blank_response(conn, req, status_code=400)
                return
        with db.transaction() as db:
            obj = Object.get_object_by_uuid(uid, db.root())
            user = User.get_user_by_username(username, db.root())
            if user.uuid != obj.owner:
                send_blank_response(conn, req, status_code=401)
                return
            if obj is None:
                send_blank_response(conn, req, status_code=404)
                return
            if new_name:
                obj.name = new_name
            if new_data:
                obj.data = new_data
            send_blank_response(conn, req, status_code=200)
    else:
        send_blank_response(conn, req, status_code=400)
        return

def handle_object_delete(req: Request, conn: PacketServerConnection, db: ZODB.DB):
    username = ax25.Address(conn.remote_callsign).call.upper().strip()
    if 'uuid' in req.vars:
        uid = req.vars['uuid']
        if type(uid) is bytes:
            u_obj = UUID(bytes=uid)
        elif type(uid) is int:
            u_obj = UUID(int=uid)
        else:
            try:
                u_obj = UUID(str(uid))
            except ValueError:
                send_blank_response(conn, req, status_code=400)
        with db.transaction() as db:
            obj = Object.get_object_by_uuid(uid, db.root())
            user = User.get_user_by_username(username, db.root())
            if user.uuid != obj.owner:
                send_blank_response(conn, req, status_code=401)
                return
            if obj is None:
                send_blank_response(conn, req, status_code=404)
                return
            try:
                user.remove_obj_uuid(uid)
                del db.root.objects[uid]
            except:
                send_blank_response(conn, req, status_code=500)
                logging.error(f"Error handling delete:\n{format_exc()}")
            send_blank_response(conn, req, status_code=200)
    else:
        send_blank_response(conn, req, status_code=400)
        return

def object_root_handler(req: Request, conn: PacketServerConnection, db: ZODB.DB):
    logging.debug(f"{req} being processed by user_root_handler")
    if not user_authorized(conn, db):
        logging.debug(f"user {conn.remote_callsign} not authorized")
        send_blank_response(conn, req, status_code=401)
        return
    logging.debug("user is authorized")
    if req.method is Request.Method.GET:
        handle_object_get(req, conn, db)
    elif req.method is Request.Method.POST:
        handle_object_post(req, conn, db)
    elif req.method is Request.Method.UPDATE:
        handle_object_update(req, conn, db)
    elif req.method is Request.Method.DELETE:
        handle_object_delete(req, conn, db)
    else:
        send_blank_response(conn, req, status_code=404)
