import pe.app
from packetserver.common import Response, Message, Request, PacketServerConnection, send_response, send_blank_response
from packetserver.server.constants import default_server_config
from packetserver.server.users import User
from copy import deepcopy
import ax25
from pathlib import Path
import ZODB, ZODB.FileStorage
from BTrees.OOBTree import OOBTree
from persistent.mapping import PersistentMapping
from persistent.list import PersistentList
from packetserver.server.requests import standard_handlers
import logging
import signal
import time
from msgpack.exceptions import OutOfData
from typing import Callable, Self, Union
from traceback import  format_exc
from os import linesep

def init_bulletins(root: PersistentMapping):
    if 'bulletins' not in root:
        root['bulletins'] = PersistentList()
    if 'bulletin_counter' not in root:
        root['bulletin_counter'] = 0

class Server:
    def __init__(self, pe_server: str, port: int, server_callsign: str, data_dir: str = None, zeo: bool = True):
        if not ax25.Address.valid_call(server_callsign):
            raise ValueError(f"Provided callsign '{server_callsign}' is invalid.")
        self.callsign = server_callsign
        self.pe_server = pe_server
        self.pe_port = port
        self.handlers = deepcopy(standard_handlers)
        self.zeo_addr = None
        self.zeo_stop = None
        self.zeo = zeo
        if data_dir:
            data_path = Path(data_dir)
        else:
            data_path = Path.home().joinpath(".packetserver")
        if data_path.is_dir():
            if data_path.joinpath("data.zopedb").exists():
                if not data_path.joinpath("data.zopedb").is_file():
                    raise FileExistsError("data.zopedb exists as non-file in specified path")
            self.home_dir = data_path
        else:
            if data_path.exists():
                raise FileExistsError(f"Non-Directory path '{data_dir}' already exists.")
            else:
                data_path.mkdir()
                self.home_dir = data_path
        self.storage = ZODB.FileStorage.FileStorage(self.data_file)
        self.db = ZODB.DB(self.storage)
        with self.db.transaction() as conn:
            if 'config' not in conn.root():
                logging.debug("no config, writing blank default config")
                conn.root.config = PersistentMapping(deepcopy(default_server_config))
                conn.root.config['blacklist'] = PersistentList()
            if 'SYSTEM' not in conn.root.config['blacklist']:
                logging.debug("Adding 'SYSTEM' to blacklist in case someone feels like violating FCC rules.")
                conn.root.config['blacklist'].append('SYSTEM')
            if 'users' not in conn.root():
                logging.debug("users missing, creating bucket")
                conn.root.users = PersistentMapping()
            if 'SYSTEM' not in conn.root.users:
                logging.debug("Creating system user for first time.")
                User('SYSTEM', hidden=True, enabled=False).write_new(conn.root())
            if 'objects' not in conn.root():
                logging.debug("objects bucket missing, creating")
                conn.root.objects = OOBTree()
            init_bulletins(conn.root())
        self.app = pe.app.Application()
        PacketServerConnection.receive_subscribers.append(lambda x: self.server_receiver(x))
        PacketServerConnection.connection_subscribers.append(lambda x: self.server_connection_bouncer(x))
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)
        self.db.close()
        self.storage.close()


    @property
    def data_file(self) -> str:
        return str(Path(self.home_dir).joinpath('data.zopedb'))

    def server_connection_bouncer(self, conn: PacketServerConnection):
        logging.debug("new connection bouncer checking user status")
        # blacklist check
        blacklisted = False
        base = ax25.Address(conn.remote_callsign).call
        with self.db.transaction() as storage:
            if 'blacklist' in storage.root.config:
                bl = storage.root.config['blacklist']
                logging.debug(f"A blacklist exists: {bl}")
                logging.debug(f"Checking callsign {base.upper()}")
                if base.upper() in bl:
                    logging.debug(f"Connection from blacklisted callsign {base}")
                    conn.closing = True
                    blacklisted = True

            # user object check
            if base in storage.root.users:
                logging.debug(f"User {base} exists in db.")
                u = storage.root.users[base]
                u.seen()
            else:
                logging.info(f"Creating new user {base}")
                u = User(base.upper().strip())
                u.write_new(storage.root())
        if blacklisted:
            count = 0
            while count < 10:
                time.sleep(.5)
                if conn.state.name == "CONNECTED":
                    break
            conn.close()

    def handle_request(self, req: Request, conn: PacketServerConnection):
        """Handles a proper request by handing off to the appropriate function depending on method and Path."""
        logging.debug(f"asked to handle request: {req}")
        if conn.closing:
            logging.debug("Connection marked as closing. Ignoring it.")
            return
        req_root_path = req.path.split("/")[0]
        if req_root_path in self.handlers:
            logging.debug(f"found handler for req {req}")
            self.handlers[req_root_path](req, conn, self.db)
            return
        logging.warning(f"unhandled request found: {req}")
        send_blank_response(conn, req, status_code=404)

    def process_incoming_data(self, connection: PacketServerConnection):
        """Handles incoming data."""
        logging.debug("Running process_incoming_data on connection")
        with connection.data_lock:
            logging.debug("Data lock acquired")
            while True:
                try:
                    msg = Message.partial_unpack(connection.data.unpack())
                    logging.debug(f"parsed a Message from data received")
                except OutOfData:
                    logging.debug("no complete message yet, done until more data arrives")
                    break
                except ValueError:
                    connection.send_data(b"BAD REQUEST. COULD NOT PARSE INCOMING DATA AS PACKETSERVER MESSAGE")
                try:
                    request = Request(msg)
                    logging.debug(f"parsed Message into request {request}")
                except ValueError:
                    connection.send_data(b"BAD REQUEST. DID NOT RECEIVE A REQUEST MESSAGE.")
                logging.debug(f"attempting to handle request {request}")
                self.handle_request(request, connection)
                logging.debug("request handled")

    def server_receiver(self, conn: PacketServerConnection):
        logging.debug("running server receiver")
        try:
            self.process_incoming_data(conn)
        except Exception:
            logging.debug(f"Unhandled exception while processing incoming data:\n{format_exc()}")

    def register_path_handler(self, path_root: str, fn: Callable):
        self.handlers[path_root.strip().lower()] = fn

    def start(self):
        if not self.zeo:
            self.storage = ZODB.FileStorage.FileStorage(self.data_file)
            self.db = ZODB.DB(self.storage)
        else:
            import ZEO
            address, stop = ZEO.server(path=self.data_file)
            self.zeo_addr = address
            self.zeo_stop = stop
            self.db = ZEO.DB(self.zeo_addr)
            logging.info(f"Starting ZEO server with address {self.zeo_addr}")
            try:
                zeo_address_file = str(self.home_dir.joinpath("zeo-address.txt"))
                open(zeo_address_file, 'w').write(f"{self.zeo_addr[0]}:{self.zeo_addr[1]}{linesep}")
                logging.info(f"Wrote ZEO server info to '{zeo_address_file}'")
            except:
                logging.warning(f"Couldn't write ZEO server info to '{zeo_address_file}'\n{format_exc()}")
        self.app.start(self.pe_server, self.pe_port)
        self.app.register_callsigns(self.callsign)

    def exit_gracefully(self, signum, frame):
        self.stop()

    def stop(self):
        cm = self.app._engine._active_handler._handlers[1]._connection_map
        for key in cm._connections.keys():
            cm._connections[key].close()
        self.app.stop()
        self.storage.close()
        self.db.close()
        if self.zeo:
            logging.info("Stopping ZEO.")
            self.zeo_stop()
