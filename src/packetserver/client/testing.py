from typing import Union

from packetserver.common import Request, PacketServerConnection
from packetserver.common.testing import SimpleDirectoryConnection
from packetserver.client import Client
import ax25

class TestClient(Client):
    def __init__(self, conn_dir: str, callsign: str, keep_log: bool = True):
        super().__init__('', 0, callsign, keep_log=keep_log)
        self._connections = {}

    @property
    def connections(self) -> dict:
        return self._connections

    def connection_exists(self, callsign: str):
        if not ax25.Address.valid_call(callsign):
            raise ValueError("Must supply a valid callsign.")
        callsign = callsign.upper().strip()
        for key in self.connections.keys():
            if key.split(":")[1] == callsign:
                return True
        return False

    def new_connection(self, dest: str) -> SimpleDirectoryConnection:
        if not self.started:
            raise RuntimeError("Must start client before creating connections.")
        if not ax25.Address.valid_call(dest):
            raise ValueError(f"Provided destination callsign '{dest}' is invalid.")
        with self.lock_locker:
            if dest.upper() not in self._connection_locks:
                self._connection_locks[dest.upper()] = Lock()
        with self._connection_locks[dest.upper()]:
            conn = self.connection_callsign(dest.upper())
            if conn is not None:
                return conn

    def connection_for(self, callsign: str):
        if not ax25.Address.valid_call(callsign):
            raise ValueError("Must supply a valid callsign.")
        callsign = callsign.upper().strip()
        if self.connection_exists(callsign):
            return self.connection_callsign(callsign)
        else:
            return self.new_connection(callsign)

    def receive(self, req: Request, conn: Union[PacketServerConnection,SimpleDirectoryConnection], timeout: int = 300):
        if type(conn) is SimpleDirectoryConnection:
            conn.check_for_data()
        return super().receive(req, conn, timeout=timeout)

    def clear_connections(self):
        if self.app._engine is not None:
            cm = self.app._engine._active_handler._handlers[1]._connection_map
            for key in cm._connections.keys():
                cm._connections[key].close()

    def start(self):
        pass

    def stop(self):
        pass