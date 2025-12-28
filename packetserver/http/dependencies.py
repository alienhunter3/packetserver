# packetserver/http/dependencies.py
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from .auth import HttpUser
from .database import DbDependency

security = HTTPBasic()


async def get_current_http_user(db: DbDependency, credentials: HTTPBasicCredentials = Depends(security)):
    """
    Authenticate via Basic Auth using HttpUser from ZODB.
    Injected by the standalone runner (get_db_connection available).
    """
    with db.transaction() as conn:
        root = conn.root()

        http_users = root.get("httpUsers")
        if http_users is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
                headers={"WWW-Authenticate": "Basic"},
            )

        user: HttpUser | None = http_users.get(credentials.username.upper())

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
                headers={"WWW-Authenticate": "Basic"},
            )

        if not user.http_enabled:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="HTTP access disabled for this user",
            )

        if not user.verify_password(credentials.password):
            user.record_login_failure()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
                headers={"WWW-Authenticate": "Basic"},
            )

        user.record_login_success()
        return user