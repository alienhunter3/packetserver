from copy import deepcopy

from fastapi import Depends
from typing import Annotated, Generator
from os.path import isfile

import ZEO
import ZODB
import json
from ZODB.Connection import Connection
import transaction
import logging

from .config import Settings  # assuming Settings has zeo_file: str
from ..common.util import convert_from_persistent

settings = Settings()

# Global shared DB instance (created once)
_db: ZODB.DB | None = None

def _get_zeo_address(zeo_address_file: str) -> tuple[str, int]:
    if not isfile(zeo_address_file):
        raise FileNotFoundError(f"ZEO address file not found: '{zeo_address_file}'")

    contents = open(zeo_address_file, 'r').read().strip().split(":")
    if len(contents) != 2:
        raise ValueError(f"Invalid ZEO address format in {zeo_address_file}")

    host = contents[0]
    try:
        port = int(contents[1])
    except ValueError:
        raise ValueError(f"Invalid port in ZEO address file: {zeo_address_file}")

    return host, port

def init_db() -> ZODB.DB:
    """Call this on app startup to create the shared DB instance."""
    global _db
    if _db is not None:
        return _db

    host, port = _get_zeo_address(settings.zeo_file)
    _db = ZEO.DB((host, port))
    return _db

def get_db() -> ZODB.DB:
    """Dependency for the shared DB instance (e.g., for class methods needing DB)."""
    if _db is None:
        raise RuntimeError("Database not initialized – call init_db() on startup")
    return _db

#def get_connection() -> Generator[Connection, None, None]:
#    """Per-request dependency: yields an open Connection, closes on exit."""
#    db = get_db()
#    conn = db.open()
#    try:
#        yield conn
#    finally:
#        #print("not closing connection")
#        #conn.close()
#        pass

# Optional: per-request transaction (if you want automatic commit/abort)
def get_transaction_manager():
    return transaction.manager

# Annotated dependencies for routers
DbDependency = Annotated[ZODB.DB, Depends(get_db)]
#ConnectionDependency = Annotated[Connection, Depends(get_connection)]

def get_server_config_from_db(db: DbDependency) -> dict:
    with db.transaction() as conn:
        db_config = convert_from_persistent(conn.root.config)
        if type(db_config) is not dict:
            raise RuntimeError("The config property is not a dict.")
        db_config['server_callsign'] = conn.root.server_callsign
        return db_config