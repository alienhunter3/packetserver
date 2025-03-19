from tabulate import tabulate
import json
import click
from packetserver.client import Client
import sys
import ZODB
from persistent.mapping import PersistentMapping
import datetime

def format_list_dicts(dicts: list[dict], output_format: str = "table") -> str:
    if output_format == "table":
        return tabulate(dicts, headers="keys")

    elif output_format == "json":
        return json.dumps(dicts, indent=2)

    elif output_format == "list":
        output = ""
        for i in dicts:
            t = []
            for key in i:
                t.append([str(key), str(i[key])])
            output = output + tabulate(t) + "\n"
        return output
    else:
        raise ValueError("Unsupported format type.")

def write_request_log(db: ZODB.DB, client: Client):
    with db.transaction() as db_trans:
        if not 'request_log' in db_trans.root():
            db_trans['request_log'] = PersistentMapping()
        now = datetime.datetime.now()
        db_trans['request_log'][now.isoformat()] = client.request_log



def exit_client(context: dict, return_code: int, message=""):
    client = context['client']
    db = context['db']
    client.stop()

    if context['keep_log']:
        write_request_log(db, client)

    db.close()
    client.stop()
    if return_code == 0:
        is_err = False
    else:
        is_err = True
    if message.strip() != "":
        click.echo(message, err=is_err)
    sys.exit(return_code)

unit_seconds ={
    'h': 3600,
    'm': 60,
    's': 1,
    'd': 86400
}