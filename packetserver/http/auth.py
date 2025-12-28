# packetserver/http/auth.py
import ax25
import transaction
from persistent import Persistent
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
import time
from persistent.mapping import PersistentMapping
from persistent.list import PersistentList
from packetserver.common.util import is_valid_ax25_callsign
from .database import DbDependency
from typing import Union
from ZODB.Connection import Connection

ph = PasswordHasher()


class HttpUser(Persistent):
    """
    Persistent object for HTTP API users.
    Separate from server.users.User to avoid privilege bleed.
    """

    def __init__(self, username: str, password: str):
        self.username = username.upper()  # stored uppercase like regular users
        self.password_hash = ph.hash(password)
        self.created_at = time.time()
        self.last_login = None
        self.failed_attempts = 0

        # Check to make sure we're not storing a SSID
        if is_valid_ax25_callsign(self.username):
            base = ax25.Address(self.username).call
            if base.upper() != self.username:
                raise ValueError(f"'{self.username}' is a callsign with an SSID appended. Please use base callsign.")

        # New fields
        self._enabled = True  # HTTP access enabled by default
        # rf_enabled is a @property – no direct storage needed

    # ------------------------------------------------------------------
    # Simple enabled flag (admin can disable HTTP login entirely)
    # ------------------------------------------------------------------
    @property
    def http_enabled(self) -> bool:
        return getattr(self, '_enabled', True)

    @http_enabled.setter
    def http_enabled(self, value: bool):
        self._enabled = bool(value)
        self._p_changed = True

    #
    # rf enabled checks..
    #

    def is_rf_enabled(self, db: Union[DbDependency,Connection]) -> bool:
        """
        Check if RF gateway is enabled (i.e., callsign NOT in global blacklist).
        Requires an open ZODB connection.
        """
        if type(db) is Connection:
            root = db.root()
            blacklist = root.get('config', {}).get('blacklist', [])
            return self.username not in blacklist
        with db.transaction() as conn:
            root = conn.root()
            blacklist = root.get('config', {}).get('blacklist', [])
            return self.username not in blacklist

    def set_rf_enabled(self, db: DbDependency, allow: bool):
        """
        Enable/disable RF gateway by adding/removing from global blacklist.
        Requires an open ZODB connection (inside a transaction).
        Only allows enabling if the username is a valid AX.25 callsign.
        """
        from packetserver.common.util import is_valid_ax25_callsign  # our validator
        with db.transaction() as conn:
            root = conn.root()
            config = root.setdefault('config', PersistentMapping())
            blacklist = config.setdefault('blacklist', PersistentList())

            upper_name = self.username

            if allow:
                if not is_valid_ax25_callsign(upper_name):
                    raise ValueError(f"{upper_name} is not a valid AX.25 callsign – cannot enable RF access")
                if upper_name in blacklist:
                    blacklist.remove(upper_name)
                    blacklist._p_changed = True
            else:
                if upper_name not in blacklist:
                    blacklist.append(upper_name)
                    blacklist._p_changed = True

            config._p_changed = True
            root._p_changed = True
            transaction.commit()

    # ------------------------------------------------------------------
    # Password handling (unchanged)
    # ------------------------------------------------------------------
    def verify_password(self, password: str) -> bool:
        try:
            ph.verify(self.password_hash, password)
            if ph.check_needs_rehash(self.password_hash):
                self.password_hash = ph.hash(password)
            return True
        except VerifyMismatchError:
            return False

    def record_login_success(self):
        self.last_login = time.time()
        self.failed_attempts = 0
        self._p_changed = True

    def record_login_failure(self):
        self.failed_attempts += 1
        self._p_changed = True