import ZODB
import json
import gzip
import base64
from io import BytesIO

def get_user_db(username: str, db: ZODB.DB) -> dict:
    udb = {
        "objects": {},
        "messages": [],
        "user": {},
        "bulletins": [],
        "jobs": []
    }
    username = username.strip().upper()
    with db.transaction() as db_conn:
        user = db_conn.root.users[username]
        udb['user'] = user.to_safe_dict()
        for o in user.object_uuids:
            if type(o.data) is bytes:
                o.data = base64.b64encode(o.data).decode()
            else:
                o.data = base64.b64encode(o.data.encode()).decode()
            udb['objects'][o] = db_conn.root.objects[o].to_dict()
        for m in db_conn.root.messages[username]:
            for a in m.attachments:
                if type(a.data) is bytes:
                    a.data = base64.b64encode(a.data).decode()
                else:
                    a.data = base64.b64encode(a.data.encode()).decode()
            udb['messages'].append(m.to_dict())
        for b in db_conn.root.bulletins:
            udb['bulletins'].append(b.to_dict())

        # TODO pack jobs into output

    return udb

def get_user_db_json(username: str, db: ZODB.DB, gzip_output=True) -> bytes:
    udb = get_user_db(username, db)
    j = json.dumps(udb).encode()
    if gzip_output:
        return gzip.compress(j)
    else:
        return j
