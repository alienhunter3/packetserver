# packetserver/http/auth.py
from persistent import Persistent
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
import time

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

        # New fields
        self._enabled = True  # HTTP access enabled by default
        # rf_enabled is a @property – no direct storage needed

    # ------------------------------------------------------------------
    # Simple enabled flag (admin can disable HTTP login entirely)
    # ------------------------------------------------------------------
    @property
    def enabled(self) -> bool:
        return getattr(self, '_enabled', True)

    @enabled.setter
    def enabled(self, value: bool):
        self._enabled = bool(value)
        self._p_changed = True

    # ------------------------------------------------------------------
    # rf_enabled property – tied directly to the main server's blacklist
    # ------------------------------------------------------------------
    @property
    def rf_enabled(self) -> bool:
        """
        True if the callsign is NOT in the global blacklist.
        This allows HTTP users to act as RF gateways only if explicitly allowed.
        """
        from ZODB import DB  # deferred import to avoid circular issues
        # We'll get the db from the transaction in most contexts
        # But for safety, we'll reach into the current connection's root
        import transaction
        try:
            root = transaction.get().db().root()
            blacklist = root.get('config', {}).get('blacklist', [])
            return self.username not in blacklist
        except Exception:
            # If we're outside a transaction (e.g. during tests), default safe
            return False

    @rf_enabled.setter
    def rf_enabled(self, allow: bool):
        """
        Enable/disable RF gateway capability by adding/removing from the global blacklist.
        Only allows enabling if the username is a valid AX.25 callsign.
        """
        import transaction
        from packetserver.utils import is_valid_ax25_callsign  # assuming you have this helper

        root = transaction.get().db().root()
        config = root.setdefault('config', PersistentMapping())
        blacklist = config.setdefault('blacklist', PersistentList())

        upper_name = self.username

        if allow:
            # Trying to enable RF access
            if not is_valid_ax25_callsign(upper_name):
                raise ValueError(f"{upper_name} is not a valid AX.25 callsign – cannot enable RF access")

            if upper_name in blacklist:
                blacklist.remove(upper_name)
                config['blacklist'] = blacklist
                self._p_changed = True
        else:
            # Disable RF access
            if upper_name not in blacklist:
                blacklist.append(upper_name)
                config['blacklist'] = blacklist
                self._p_changed = True

        # Ensure changes are marked
        root._p_changed = True
        config._p_changed = True

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