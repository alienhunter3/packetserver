import click
from packetserver.client.cli.config import get_config, default_app_dir, config_path
from packetserver.client.cli.constants import DEFAULT_DB_FILE
import ZODB
import ZODB.FileStorage
import sys
import os
import os.path
from pathlib import Path
from packetserver.client import Client
from packetserver.client.users import get_user_by_username, UserWrapper

VERSION="0.1.0-alpha"



@click.group()
@click.option('--conf', default=config_path(), help='path to configfile')
@click.option('--server', '-s', default='', help="server radio callsign to connect to (required)")
@click.option('--agwpe', '-a', default='localhost', help="AGWPE TNC server address to connect to (config file)")
@click.option('--port', '-p', default=8000, help="AGWPE TNC server port to connect to (config file)")
@click.option('--callsign', '-c', default='', help="radio callsign[+ssid] of this client station (config file)")
@click.version_option(VERSION,"--version", "-v")
@click.pass_context
def cli(ctx, conf, server, agwpe, port, callsign):
    """Command line interface for the PacketServer client and server API."""
    cfg = get_config(config_file_path=conf)
    storage = ZODB.FileStorage.FileStorage(os.path.join(cfg['cli']['directory'], DEFAULT_DB_FILE))
    db = ZODB.DB(storage)
    ctx.ensure_object(dict)
    ctx.obj['CONFIG'] = cfg
    ctx.obj['bbs'] = server
    ctx.obj['db'] = db

@click.command()
@click.option('--username', '-u', default='', help="the username (CALLSIGN) to lookup on the bbs")
@click.pass_context
def user(ctx):
    """Query users on the BBS and customize personal settings."""
    pass

cli.add_command(user)

if __name__ == '__main__':
    cli()
