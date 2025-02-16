import datetime
import pe.app
from ZEO.asyncio.server import new_connection

from packetserver.common import Response, Message, Request, PacketServerConnection, send_response, send_blank_response
import ax25
import logging
import signal
import time
from threading import Lock
from msgpack.exceptions import OutOfData
from typing import Callable, Self, Union, Optional
from traceback import  format_exc
from os import linesep
from shutil import rmtree
from threading import Thread

class Client:
    def __init__(self, pe_server: str, port: int, client_callsign: str, keep_log=False):
        if not ax25.Address.valid_call(client_callsign):
            raise ValueError(f"Provided callsign '{client_callsign}' is invalid.")
        self.pe_server = pe_server
        self.pe_port = port
        self.callsign = client_callsign
        self.app = pe.app.Application()
        self.started = False
        self._connection_locks = {}
        self.lock_locker = Lock()
        self.keep_log = keep_log
        self.request_log = []
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    def exit_gracefully(self, signum, frame):
        self.stop()

    @property
    def connections(self) -> dict:
        if not self.started:
            return {}
        else:
            return self.app._engine._active_handler._handlers[1]._connection_map._connections

    def connection_exists(self, callsign: str):
        if not ax25.Address.valid_call(callsign):
            raise ValueError("Must supply a valid callsign.")
        callsign = callsign.upper().strip()
        for key in self.connections.keys():
            if key.split(":")[1] == callsign:
                return True
        return False

    def connection_callsign(self, callsign: str):
        if not ax25.Address.valid_call(callsign):
            raise ValueError("Must supply a valid callsign.")
        callsign = callsign.upper().strip()
        for key in self.connections.keys():
            if key.split(":")[1] == callsign:
                return self.connections[key]
        return None

    def connection_for(self, callsign: str):
        if not ax25.Address.valid_call(callsign):
            raise ValueError("Must supply a valid callsign.")
        callsign = callsign.upper().strip()
        if self.connection_exists(callsign):
            return self.connection_callsign(callsign)
        else:
            return self.new_connection(callsign)

    def stop(self):
        self.started = False
        self.clear_connections()
        self.app.stop()
        self.connection_map = None

    def start(self):
        self.app.start(self.pe_server, self.pe_port)
        self.app.register_callsigns(self.callsign)
        self.connection_map = self.app._engine._active_handler._handlers[1]._connection_map
        self.started = True

    def clear_connections(self):
        cm = self.app._engine._active_handler._handlers[1]._connection_map
        for key in cm._connections.keys():
            cm._connections[key].close()

    def new_connection(self, dest: str) -> PacketServerConnection:
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

        conn =  self.app.open_connection(0, self.callsign, dest.upper())
        while conn.state.name != "CONNECTED":
            if conn.state.name in ['DISCONNECTED', 'DISCONNECTING']:
                raise RuntimeError("Connection disconnected unexpectedly.")
            time.sleep(.1)
        logging.debug(f"Connection to {dest} ready.")
        logging.debug("Allowing connection to stabilize for 8 seconds")
        time.sleep(8)
        return conn

    def send_and_receive(self, req: Request, conn: PacketServerConnection, timeout: int = 300) -> Optional[Response]:
        if conn.state.name != "CONNECTED":
            raise RuntimeError("Connection is not connected.")
        logging.debug(f"Sending request {req}")
        dest = conn.remote_callsign.upper()
        with self.lock_locker:
            if dest not in self._connection_locks:
                self._connection_locks[dest] = Lock()
        with self._connection_locks[dest]:
            conn.send_data(req.pack())
            cutoff_date = datetime.datetime.now() + datetime.timedelta(seconds=timeout)
            logging.debug(f"{datetime.datetime.now()}: Request timeout date is {cutoff_date}")
            while datetime.datetime.now() < cutoff_date:
                if conn.state.name != "CONNECTED":
                    logging.error(f"Connection {conn} disconnected.")
                    if self.keep_log:
                        self.request_log.append((req,None))
                    return None
                try:
                    unpacked = conn.data.unpack()
                except:
                    time.sleep(.1)
                    continue
                msg = Message.partial_unpack(unpacked)
                resp =  Response(msg)
                if self.keep_log:
                    self.request_log.append((req, resp))
                return resp
            logging.warning(f"{datetime.datetime.now()}: Request {req} timed out.")
            self.request_log.append((req, None))
            return None

    def send_receive_callsign(self, req: Request, callsign: str, timeout: int = 300) -> Optional[Response]:
        return self.send_and_receive(req, self.connection_for(callsign), timeout=timeout)

    def single_connect_send_receive(self, dest: str, req: Request, timeout: int = 300) -> Optional[Response]:
        conn = self.new_connection(dest)
        logging.debug("Waiting for connection to be ready.")
        cutoff_date = datetime.datetime.now() + datetime.timedelta(seconds=timeout)

        while (datetime.datetime.now() < cutoff_date) and (conn.state.name != "CONNECTED"):
            if conn.state.name in ["DISCONNECTED", "DISCONNECTING"]:
                logging.error(f"Connection {conn} disconnected.")
                return None

        remaining_time = int((cutoff_date - datetime.datetime.now()).total_seconds()) + 1
        if remaining_time <= 0:
            logging.debug("Connection attempt timed out.")
            conn.close()
            return None
        response = self.send_and_receive(req, conn, timeout=int(remaining_time))
        conn.close()
        return response
