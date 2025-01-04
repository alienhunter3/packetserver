"""Module for handling requests as they arrive to connection objects and servers."""

from . import PacketServerConnection
from . import Server
from msgpack.exceptions import OutOfData
from ..common import Message, Request, Response

def handle_root_get(req: Request, conn: PacketServerConnection, server: Server):
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

    if conn.state.name == "CONNECTED":
        conn.send_data(response.pack())

standard_handlers = {
    "": {
        "GET": handle_root_get
    }
}

def handle_request(req: Request, conn: PacketServerConnection, server: Server):
    """Handles a proper request by handing off to the appropriate function depending on method and Path."""
    if req.path in server.handlers:
        if req.method.name in server.handlers[req.path]:
            server.handlers[req.path][req.method.name](req, conn, server)
            return
    response_404 = Response.blank()
    response_404.status_code = 404
    if conn.state.name == "CONNECTED":
        conn.send_data(response_404.pack())

def process_incoming_data(connection: PacketServerConnection, server: Server):
    """Handles incoming data."""
    with connection.data_lock:
        while True:
            try:
                msg = Message.partial_unpack(connection.data.unpack())
            except OutOfData:
                break
            except ValueError:
                r = Response.blank()
                r.status_code = 400
                r.payload = "BAD REQUEST. COULD NOT PARSE INCOMING DATA AS PACKETSERVER MESSAGE"
                connection.send_data(r.pack())
                connection.send_data(b"BAD REQUEST. COULD NOT PARSE INCOMING DATA AS PACKETSERVER MESSAGE")

            try:
                request = Request(msg)
            except ValueError:
                r = Response.blank()
                r.status_code = 400
                r.payload = "BAD REQUEST. DID NOT RECEIVE A REQUEST MESSAGE."
                connection.send_data(r.pack())
                connection.send_data(b"BAD REQUEST. DID NOT RECEIVE A REQUEST MESSAGE.")
