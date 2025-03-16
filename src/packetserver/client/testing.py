import os.path
import time
from typing import Union

from packetserver.common import Request, PacketServerConnection
from packetserver.common.testing import SimpleDirectoryConnection
from packetserver.client import Client
import ax25
from threading import Lock
import logging
import os.path
from shutil import rmtree

class TestClient(Client):
    def __init__(self, conn_dir: str, callsign: str, keep_log: bool = True):
        super().__init__('', 0, callsign, keep_log=keep_log)
        self._connections = {}
        if not os.path.isdir(conn_dir):
            raise NotADirectoryError(f"Conn dir {conn_dir} does not exist.")
        self._connection_directory = os.path.abspath(conn_dir)

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

        conn_dir = os.path.join(self._connection_directory, f"{self.callsign.upper()}--{dest.upper()}")
        if not os.path.isdir(conn_dir):
            os.mkdir(conn_dir)
        conn = SimpleDirectoryConnection.create_directory_connection(self.callsign, conn_dir)
        self.connections[f"{dest.upper()}:{self.callsign.upper()}"] = conn
        logging.debug(f"Connection to {dest} ready.")
        return conn

    def receive(self, req: Request, conn: Union[PacketServerConnection,SimpleDirectoryConnection], timeout: int = 300):
        if type(conn) is SimpleDirectoryConnection:
            conn.check_for_data()
        return super().receive(req, conn, timeout=timeout)

    def clear_connections(self):
        closing = [x for x in self.connections]
        for key in closing:
            conn = self.connections[key]
            conn.closing = True
            conn.check_closed()
            while os.path.exists(conn.directory):
                try:
                    rmtree(conn.directory)
                except:
                    time.sleep(.5)
                    pass

    def start(self): # TODO
        pass

    def stop(self): # TODO
        pass