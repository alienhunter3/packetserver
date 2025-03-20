import click
import ZODB, ZODB.FileStorage
import ZEO
import json
import os
import os.path
import sys
from persistent.mapping import PersistentMapping
from persistent.list import PersistentList
from pathlib import Path
from packetserver.common.util import convert_from_persistent, convert_to_persistent



@click.group()
@click.option("--database", "-d", type=str, default="",
              help="DATABASE is either the path to the database file, or a tcp host:port string to a zeo server that is running."
              )
@click.option("--zeo", "-z", is_flag=True, default=False, help="<database> is a zeo address:port string.")
@click.pass_context
def config(ctx, database, zeo):
    """Dump or set the packetserver configuration."""

    ctx.ensure_object(dict)
    if zeo:
        if database is None:
            raise ValueError("Database must be at least a port to a zeo server, or an address:port string.")
        spl = database.split(":")
        if len(spl) == 1:
            host = 'localhost'
            port = int(spl[0])
        else:
            host = spl[0]
            port = int(spl[1])
        db = ZEO.DB((host, port))
    else:
        if type(database) is str and (database != "") :
            data_file = Path(database)
        else:
            data_file = Path.home().joinpath(".packetserver").joinpath("data.zopedb")
        if not data_file.is_file():
                raise FileExistsError(f"Database file {str(data_file)} is not a file, or it doesn't exit.")

        storage = ZODB.FileStorage.FileStorage(str(data_file))
        db = ZODB.DB(storage)

    ctx.obj['db'] = db


@click.command()
@click.pass_context
def dump(ctx):
    with ctx.obj['db'].transaction() as conn:
        click.echo(json.dumps(convert_from_persistent(conn.root.config), indent=2))

@click.command()
@click.option("--json-data", "-j", type=str, required=True, help="Filename to json or '-' for stdin.")
@click.pass_context
def load(ctx, json_data):
    if json_data == "-":
        data = json.load(sys.stdin)
    else:
        data = json.load(open(json_data, 'r'))

    with ctx.obj['db'].transaction() as conn:
        conn.root.config = convert_to_persistent(data)

config.add_command(dump)
config.add_command(load)

if __name__ == '__main__':
    config()
