import pe.app
from ..common import PacketServerConnection
from .constants import default_server_config
from copy import deepcopy
import ax25
from pathlib import Path
import ZODB, ZODB.FileStorage
from BTrees.OOBTree import OOBTree
from .requests import process_incoming_data
from .requests import standard_handlers


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
            self.home_dir = data_dir
        else:
            if data_path.exists():
                raise FileExistsError(f"Non-Directory path '{data_dir}' already exists.")
            else:
                data_path.mkdir()
                self.home_dir = data_dir
        self.storage = ZODB.FileStorage.FileStorage(self.data_file)
        self.db = ZODB.DB(self.storage)
        with self.db.transaction() as conn:
            if 'config' not in conn.root():
                conn.root.config = deepcopy(default_server_config)
            if 'users' not in conn.root():
                conn.root.users = OOBTree()
        self.app = pe.app.Application()
        PacketServerConnection.receive_subscribers.append(lambda x: self.server_receiver(x))


    @property
    def data_file(self) -> str:
        return str(Path(self.home_dir).joinpath('data.zopedb'))

    def server_receiver(self, conn: PacketServerConnection):
        process_incoming_data(conn, self)

    def start(self):
        self.app.start(self.pe_server, self.pe_port)
        self.app.register_callsigns(self.callsign)

    def stop(self):
        self.app.stop()