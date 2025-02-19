import click
from packetserver.client.cli.config import get_config, default_app_dir, config_path
from packetserver.client.cli.constants import DEFAULT_DB_FILE
from packetserver.client import Client
from packetserver.common.constants import yes_values
from packetserver.client.cli.util import format_list_dicts
import ZODB
import ZODB.FileStorage
import ax25
import sys
import os
import os.path
from pathlib import Path
from packetserver.client import Client
from packetserver.client import users
from packetserver.client.users import get_user_by_username, UserWrapper

VERSION="0.1.0-alpha"



@click.group()
@click.option('--conf', default=config_path(), help='path to configfile')
@click.option('--server', '-s', default='', help="server radio callsign to connect to (required)")
@click.option('--agwpe', '-a', default='', help="AGWPE TNC server address to connect to (config file)")
@click.option('--port', '-p', default=0, help="AGWPE TNC server port to connect to (config file)")
@click.option('--callsign', '-c', default='', help="radio callsign[+ssid] of this client station (config file)")
@click.version_option(VERSION,"--version", "-v")
@click.pass_context
def cli(ctx, conf, server, agwpe, port, callsign):
    """Command line interface for the PacketServer client and server API."""
    ctx.ensure_object(dict)
    cfg = get_config(config_file_path=conf)

    if callsign.strip() != '':
        ctx.obj['callsign'] = callsign.strip().upper()
    else:
        if 'callsign' in cfg['cli']:
            ctx.obj['callsign'] = cfg['cli']['callsign']
        else:
            raise ValueError("You must provide client station's callsign.")

    if not ax25.Address.valid_call(ctx.obj['callsign']):
        raise ValueError(f"Provided client callsign '{ctx.obj['callsign']}' is invalid.")

    if server.strip() != '':
        ctx.obj['server'] = server.strip().upper()
    else:
        if 'server' in cfg['cli']:
            ctx.obj['server'] = cfg['cli']['server']
        else:
            raise ValueError("Remote BBS server callsign must be specified.")

    if not ax25.Address.valid_call(ctx.obj['server']):
        raise ValueError(f"Provided remote server callsign '{ctx.obj['server']}' is invalid.")

    if agwpe.strip() != '':
        ctx.obj['agwpe_server'] = agwpe.strip()
    else:
        if 'agwpe_server' in cfg['cli']:
            ctx.obj['agwpe_server'] = cfg['cli']['agwpe_server']
        else:
            ctx.obj['agwpe_server'] = 'localhost'

    if port != 0:
        ctx.obj['port'] = port
    else:
        if 'port' in cfg['cli']:
            ctx.obj['port'] = int(cfg['cli']['port'])
        else:
            ctx.obj['port'] = 8000

    storage = ZODB.FileStorage.FileStorage(os.path.join(cfg['cli']['directory'], DEFAULT_DB_FILE))
    db = ZODB.DB(storage)
    client = Client(ctx.obj['agwpe_server'], ctx.obj['port'], ctx.obj['callsign'], keep_log=True)
    ctx.obj['client'] = client
    ctx.obj['CONFIG'] = cfg
    ctx.obj['bbs'] = server
    ctx.obj['db'] = db

@click.command()
@click.argument('username', required=False, default='', help="the username (CALLSIGN) to lookup on the bbs")
@click.option('--list-users', '-l', is_flag=True, default=False, help="If set, downloads list of all users.")
@click.option("--output-format", "-f", default="table", help="Print data as table[default], list, or JSON",
              type=click.Choice(['table', 'json', 'list'], case_sensitive=False))
@click.pass_context
def user(ctx, list_users, output_format, username):
    """Query users on the BBS."""
    client = ctx.obj['client']
    # validate args
    if list_users and (username.strip() != ""):
        raise ValueError("Can't specify a username while listing all users.")

    if not list_users and (username.strip() == ""):
        raise ValueError("Must provide either a username or --list-users flag.")

    output_objects = []
    if list_users:
        output_objects = users.get_users(client, ctx.obj['bbs'])
    else:
        output_objects.append(users.get_user_by_username(client, ctx.obj['bbs'], username))

    click.echo(format_list_dicts([x.pretty_dict() for x in output_objects], output_format=output_format.lower()))

cli.add_command(user)

if __name__ == '__main__':
    cli()
