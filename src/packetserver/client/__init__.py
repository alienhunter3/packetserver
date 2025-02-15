import datetime
import pe.app
from ZEO.asyncio.server import new_connection

from packetserver.common import Response, Message, Request, PacketServerConnection, send_response, send_blank_response
import ax25
import logging
import signal
import time
from msgpack.exceptions import OutOfData
from typing import Callable, Self, Union, Optional
from traceback import  format_exc
from os import linesep
from shutil import rmtree
from threading import Thread

class Client:
    def __init__(self, pe_server: str, port: int, client_callsign: str):
        if not ax25.Address.valid_call(client_callsign):
            raise ValueError(f"Provided callsign '{client_callsign}' is invalid.")
        self.pe_server = pe_server
        self.pe_port = port
        self.callsign = client_callsign
        self.app = pe.app.Application()
        self.started = False
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    def exit_gracefully(self, signum, frame):
        self.stop()

    def stop(self):
        self.started = False
        self.clear_connections()
        self.app.stop()

    def start(self):
        self.app.start(self.pe_server, self.pe_port)
        self.app.register_callsigns(self.callsign)
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
        conn =  self.app.open_connection(0, self.callsign, dest)
        while conn.state.name != "CONNECTED":
            if conn.state.name in ['DISCONNECTED', 'DISCONNECTING']:
                raise RuntimeError("Connection disconnected unexpectedly.")
            time.sleep(.1)
        logging.debug("Allowing connection to stabilize for 10 seconds")
        time.sleep(10)
        return conn

    def send_and_receive(self, req: Request, conn: PacketServerConnection, timeout: int = 300) -> Optional[Response]:
        if conn.state.name != "CONNECTED":
            raise RuntimeError("Connection is not connected.")
        logging.debug(f"Sending request {req}")
        conn.send_data(req.pack())
        cutoff_date = datetime.datetime.now() + datetime.timedelta(seconds=timeout)
        while datetime.datetime.now() < cutoff_date:
            if conn.state.name != "CONNECTED":
                logging.error(f"Connection {conn} disconnected.")
                return None
            try:
                unpacked = conn.data.unpack()
            except:
                time.sleep(.1)
                continue
            msg = Message.partial_unpack(unpacked)
            return Response(msg)
        return None

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
