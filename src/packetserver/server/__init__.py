import pe.app
import packetserver.common
from packetserver.server.constants import default_server_config
from copy import deepcopy
import ax25
from pathlib import Path
import ZODB, ZODB.FileStorage
from BTrees.OOBTree import OOBTree
from persistent.mapping import PersistentMapping
from persistent.list import PersistentList
from packetserver.server.requests import process_incoming_data
from packetserver.server.requests import standard_handlers
import logging
import signal
import time


class Server:
    def __init__(self, pe_server: str, port: int, server_callsign: str, data_dir: str = None):
        if not ax25.Address.valid_call(server_callsign):
            raise ValueError(f"Provided callsign '{server_callsign}' is invalid.")
        self.callsign = server_callsign
        self.pe_server = pe_server
        self.pe_port = port
        self.handlers = deepcopy(standard_handlers)
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
                conn.root.config = PersistentMapping(deepcopy(default_server_config))
                conn.root.config['blacklist'] = PersistentList()
            if 'users' not in conn.root():
                conn.root.users = OOBTree()
        self.app = pe.app.Application()
        packetserver.common.PacketServerConnection.receive_subscribers.append(lambda x: self.server_receiver(x))
        packetserver.common.PacketServerConnection.connection_subscribers.append(lambda x: self.server_connection_bouncer(x))
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)


    @property
    def data_file(self) -> str:
        return str(Path(self.home_dir).joinpath('data.zopedb'))

    def server_connection_bouncer(self, conn: packetserver.common.PacketServerConnection):
        logging.debug("new connection bouncer checking for blacklist")
        # blacklist check
        blacklisted = False
        with self.db.transaction() as storage:
            if 'blacklist' in storage.root.config:
                bl = storage.root.config['blacklist']
                logging.debug(f"A blacklist exists: {bl}")
                base = ax25.Address(conn.remote_callsign).call
                logging.debug(f"Checking callsign {base.upper()}")
                if base.upper() in bl:
                    logging.debug(f"Connection from blacklisted callsign {base}")
                    conn.closing = True
                    blacklisted = True
        if blacklisted:
            count = 0
            while count < 10:
                time.sleep(.5)
                if conn.state.name == "CONNECTED":
                    break
            conn.close()

    def server_receiver(self, conn: packetserver.common.PacketServerConnection):
        logging.debug("running server receiver")
        process_incoming_data(conn, self)

    def start(self):
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
