# packetserver/http/routers/send.py
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, validator
from typing import List
from persistent.list import PersistentList
from persistent.mapping import PersistentMapping
from datetime import datetime
import transaction

from packetserver.http.dependencies import get_current_http_user
from packetserver.http.auth import HttpUser
from packetserver.server.messages import Message
from packetserver.common.util import is_valid_ax25_callsign
from packetserver.http.database import DbDependency

router = APIRouter(prefix="/api/v1", tags=["messages"])


class SendMessageRequest(BaseModel):
    to: List[str] = Field(..., description="List of recipient callsigns or ['ALL'] for bulletin")
    text: str = Field(..., min_length=1, description="Message body text")

    @validator("to")
    def validate_to(cls, v):
        if not v:
            raise ValueError("At least one recipient required")

        validated = []
        for call in v:
            call_upper = call.upper().strip()
            if not is_valid_ax25_callsign(call_upper):
                raise ValueError(f"Invalid AX.25 callsign: {call}")
            validated.append(call_upper)

        if len(validated) > 1 and "ALL" in validated:
            raise ValueError("'ALL' can only be used alone for bulletins")

        return validated


@router.post("/messages")
async def send_message(
    db: DbDependency,
    payload: SendMessageRequest,
    current_user: HttpUser = Depends(get_current_http_user)
):
    is_rf_enabled = current_user.is_rf_enabled(db)
    with db.transaction() as conn:
        root = conn.root()

        if not is_rf_enabled:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="RF gateway access required to send messages"
            )

        username = current_user.username

        users_dict = root.get('users', {})

        # Prepare recipients
        to_list = [c.upper() for c in payload.to]
        is_to_all = "ALL" in to_list

        if is_to_all:
            # Deliver to all registered users
            valid_recipients = list(users_dict.keys())
            failed_recipients = []
        else:
            # Private message validation
            valid_recipients = []
            failed_recipients = []
            for recip in to_list:
                if recip in users_dict:
                    valid_recipients.append(recip)
                else:
                    failed_recipients.append(recip)

            if not valid_recipients:
                raise HTTPException(
                    status_code=400,
                    detail=f"No valid recipients found. Failed: {', '.join(failed_recipients)}"
                )


        # Create message
        new_msg = Message(
            text=payload.text,
            msg_from=username,
            msg_to=tuple(valid_recipients),
            attachments=()
        )

        # Deliver to valid recipients + always sender (sent folder)
        messages_root = root.setdefault('messages', PersistentMapping())
        delivered_to = set()
        # Always give sender a copy in their mailbox (acts as Sent folder)
        sender_mailbox = messages_root.setdefault(username, PersistentList())
        sender_mailbox.append(new_msg)
        sender_mailbox._p_changed = True
        delivered_to.add(username)  # now accurate

        for recip in valid_recipients:
            mailbox = messages_root.setdefault(recip, PersistentList())
            mailbox.append(new_msg)
            mailbox._p_changed = True
            delivered_to.add(recip)

        messages_root._p_changed = True
        transaction.commit()

        response = {
            "status": "sent",
            "message_id": str(new_msg.msg_id),
            "from": username,
            "to": list(valid_recipients),
            "sent_at": new_msg.sent_at.isoformat() + "Z",
            "recipients_delivered": len(delivered_to)
        }

        if failed_recipients:
            response["warning"] = f"Some recipients not registered: {', '.join(failed_recipients)}"
            response["failed_recipients"] = failed_recipients

        return response