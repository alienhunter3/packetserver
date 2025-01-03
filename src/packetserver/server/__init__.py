import pe
from ..common import PacketServerConnection
import ax25
from pathlib import Path
import ZODB, transaction, ZODB.FileStorage

class Server:
    def __init__(self, pe_server: str, port: int, server_callsign: str, data_dir: str = None):
        if not ax25.Address.valid_call(server_callsign):
            raise ValueError(f"Provided callsign '{server_callsign}' is invalid.")
        self.callsign = server_callsign
        self.pe_server = pe_server
        self.pe_port = port
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


    @property
    def data_file(self) -> str:
        return str(Path(self.home_dir).joinpath('data.zopedb'))


    def server_receiver(self, conn: PacketServerConnection):
        pass
    pass