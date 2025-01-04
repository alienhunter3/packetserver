"""Module for handling requests as they arrive to connection objects and servers."""

from msgpack.exceptions import OutOfData
from packetserver.common import Message, Request, Response, PacketServerConnection
from .bulletin import bulletin_root_handler
import logging
from typing import Union

def send_404(conn: PacketServerConnection, payload: Union[bytes, bytearray, str, dict] = ""):
    response_404 = Response.blank()
    response_404.status_code = 404
    response_404.payload = payload
    if conn.state.name == "CONNECTED":
        conn.send_data(response_404.pack())

def handle_root_get(req: Request, conn: PacketServerConnection,
                    server: 'packetserver.server.Server'):
    logging.debug(f"Received request: {req}")
    response = Response.blank()
    response.compression = Message.CompressionType.BZIP2
    operator = ""
    motd = ""
    with server.db.transaction() as storage:
        if 'motd' in storage.root.config:
            motd = storage.root.config['motd']
        if 'operator' in storage.root.config:
            operator = storage.root.config['operator']

    response.payload = {
        'operator': operator,
        'motd': motd
    }

    if conn.state.name == "CONNECTED" and not conn.closing:
        logging.debug(f"sending response: {response}, {response.compression}, {response.payload}")
        conn.send_data(response.pack())
        logging.debug("response sent successfully")

def root_root_handler(req: Request, conn: PacketServerConnection,
                    server: 'packetserver.server.Server'):
    logging.debug(f"{req} got to root_root_handler")
    if req.method is Request.Method.GET:
        handle_root_get(req, conn, server)
    else:
        logging.warning(f"unhandled request found: {req}")
        response_404 = Response.blank()
        response_404.status_code = 404
        if (conn.state.name == "CONNECTED") and not conn.closing:
            conn.send_data(response_404.pack())
            logging.debug(f"Sent 404 in response to {req}")

standard_handlers = {
    "": root_root_handler,
    "bulletin": bulletin_root_handler
}

def handle_request(req: Request, conn: PacketServerConnection,
                   server: 'packetserver.server.Server'):
    """Handles a proper request by handing off to the appropriate function depending on method and Path."""
    logging.debug(f"asked to handle request: {req}")
    if conn.closing:
        logging.debug("Connection marked as closing. Ignoring it.")
        return
    req_root_path = req.path.split("/")[0]
    if req_root_path in server.handlers:
        logging.debug(f"found handler for req {req}")
        server.handlers[req_root_path](req, conn, server)
        return
    logging.warning(f"unhandled request found: {req}")
    response_404 = Response.blank()
    response_404.status_code = 404
    if conn.state.name == "CONNECTED":
        conn.send_data(response_404.pack())
        logging.debug(f"Sent 404 in response to {req}")

def process_incoming_data(connection: 'packetserver.common.PacketServerConnection',
                          server: 'packetserver.server.Server'):
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
                r = Response.blank()
                r.status_code = 400
                r.payload = "BAD REQUEST. COULD NOT PARSE INCOMING DATA AS PACKETSERVER MESSAGE"
                connection.send_data(r.pack())
                connection.send_data(b"BAD REQUEST. COULD NOT PARSE INCOMING DATA AS PACKETSERVER MESSAGE")
            try:
                request = Request(msg)
                logging.debug(f"parsed Message into request {request}")
            except ValueError:
                r = Response.blank()
                r.status_code = 400
                r.payload = "BAD REQUEST. DID NOT RECEIVE A REQUEST MESSAGE."
                connection.send_data(r.pack())
                connection.send_data(b"BAD REQUEST. DID NOT RECEIVE A REQUEST MESSAGE.")
            logging.debug(f"attempting to handle request {request}")
            handle_request(request, connection, server)
            logging.debug("request handled")