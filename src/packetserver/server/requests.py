"""Module for handling requests as they arrive to connection objects and servers."""

from msgpack.exceptions import OutOfData
from packetserver.common import Message, Request, Response, PacketServerConnection, send_response, send_blank_response
from .bulletin import bulletin_root_handler
from .users import user_root_handler
import logging
from typing import Union
import ZODB

def handle_root_get(req: Request, conn: PacketServerConnection,
                    db: ZODB.DB):
    logging.debug(f"Root get handler received request: {req}")
    response = Response.blank()
    response.compression = Message.CompressionType.BZIP2
    operator = ""
    motd = ""
    with db.transaction() as storage:
        if 'motd' in storage.root.config:
            motd = storage.root.config['motd']
        if 'operator' in storage.root.config:
            operator = storage.root.config['operator']

    response.payload = {
        'operator': operator,
        'motd': motd
    }

    send_response(conn, response, req)

def root_root_handler(req: Request, conn: PacketServerConnection,
                    db: ZODB.DB):
    logging.debug(f"{req} got to root_root_handler")
    if req.method is Request.Method.GET:
        handle_root_get(req, conn, db)
    else:
        logging.warning(f"unhandled request found: {req}")
        send_blank_response(conn, req, status_code=404)

standard_handlers = {
    "": root_root_handler,
    "bulletin": bulletin_root_handler,
    "user": user_root_handler
}


