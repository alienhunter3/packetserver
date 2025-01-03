import pe
from ..common import PacketServerConnection
import ax25
from configparser import ConfigParser
from pathlib import Path
import ZODB, transaction

class Server:
    def __init__(self, pe_server: str, port: int, server_callsign: str, data_dir: str = None):
        if not ax25.Address.valid_call(server_callsign):
            raise ValueError(f"Provided callsign '{server_callsign}' is invalid.")
        self.callsign = server_callsign
        self.pe_server = pe_server
        self.pe_port = port
        if data_dir:
            if Path.is_dir(data_dir):
                self.home_dir = data_dir


    def server_receiver(self, conn: PacketServerConnection):
        pass
    pass