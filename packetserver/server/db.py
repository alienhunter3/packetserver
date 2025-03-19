import ZODB
import json
import gzip
import base64
from io import BytesIO
from uuid import UUID

def get_user_db(username: str, db: ZODB.DB) -> dict:
    udb = {
        "objects": [],
        "messages": [],
        "user": {},
        "bulletins": [],
        "jobs": []
    }
    username = username.strip().upper()
    with (db.transaction() as db_conn):
        user = db_conn.root.users[username]
        udb['user'] = user.to_safe_dict()
        for o in user.object_uuids:
            obj = {}
            tmp = db_conn.root.objects[o].to_dict()

            obj['name'] = tmp['name']
            obj['private'] = tmp['private']
            obj['uuid'] = str(UUID(bytes=tmp['uuid_bytes']))
            obj['created_at'] = tmp['created_at']
            obj['modified_at'] = tmp['modified_at']

            if type(tmp['data']) is bytes:
                obj['data'] = base64.b64encode(tmp['data']).decode()
            else:
                obj['data'] = str(tmp['data'])

            udb['objects'].append(obj)

        if user in db_conn.root.messages:
            for m in db_conn.root.messages[username]:
                for a in m.attachments:
                    if type(a.data) is bytes:
                        a.data = base64.b64encode(a.data).decode()
                    else:
                        a.data = base64.b64encode(a.data.encode()).decode()
                udb['messages'].append(m.to_dict())
        for b in db_conn.root.bulletins:
            udb['bulletins'].append(b.to_dict())

        if username in db_conn.root.user_jobs:
            for jid in db_conn.root.user_jobs[username]:
                udb['jobs'].append(db_conn.root.jobs[jid].to_dict(binary_safe=True))

    return udb

def get_user_db_json(username: str, db: ZODB.DB, gzip_output=True) -> bytes:
    udb = get_user_db(username, db)
    j = json.dumps(udb).encode()
    if gzip_output:
        return gzip.compress(j)
    else:
        return j
