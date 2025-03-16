import click
from packetserver.client.cli.config import get_config, default_app_dir, config_path
from packetserver.client.cli.constants import DEFAULT_DB_FILE
from packetserver.client import Client
from packetserver.common.constants import yes_values
from packetserver.common import Request, Response
from packetserver.client.cli.util import format_list_dicts, exit_client
from packetserver.client.cli.job import job
import ZODB
import ZODB.FileStorage
import ax25
import sys
import os
import json
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
@click.option('--keep-log', '-k', is_flag=True, default=False, help="Save local copy of request log after session ends?")
@click.version_option(VERSION,"--version", "-v")
@click.pass_context
def cli(ctx, conf, server, agwpe, port, callsign, keep_log):
    """Command line interface for the PacketServer client and server API."""
    ctx.ensure_object(dict)
    cfg = get_config(config_file_path=conf)

    ctx.obj['keep_log'] = False
    if keep_log:
        ctx.obj['keep_log'] = True
    else:
        if cfg['cli'].get('keep_log', fallback='n') in yes_values:
            ctx.obj['keep_log'] = True

    if callsign.strip() != '':
        ctx.obj['callsign'] = callsign.strip().upper()
    else:
        if 'callsign' in cfg['cli']:
            ctx.obj['callsign'] = cfg['cli']['callsign']
        else:
            ctx.obj['callsign'] = click.prompt('Please enter your station callsign (with ssid if needed)', type=str)

    if not ax25.Address.valid_call(ctx.obj['callsign']):
        click.echo(f"Provided client callsign '{ctx.obj['callsign']}' is invalid.", err=True)
        sys.exit(1)

    if server.strip() != '':
        ctx.obj['server'] = server.strip().upper()
    else:
        if 'server' in cfg['cli']:
            ctx.obj['server'] = cfg['cli']['server']
        else:
            ctx.obj['server'] = click.prompt('Please enter the bbs station callsign (with ssid if needed)', type=str)

    if not ax25.Address.valid_call(ctx.obj['server']):
        click.echo(f"Provided remote server callsign '{ctx.obj['server']}' is invalid.", err=True)
        sys.exit(1)

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
    if 'TEST_SERVER_DIR' in os.environ:
        from packetserver.client.testing import TestClient
        client = TestClient(os.environ['TEST_SERVER_DIR'], ctx.obj['callsign'])
    else:
        client = Client(ctx.obj['agwpe_server'], ctx.obj['port'], ctx.obj['callsign'], keep_log=ctx.obj['keep_log'])
    try:
        client.start()
    except Exception as e:
        click.echo(f"Error connecting to TNC: {str(e)}", err=True)
        sys.exit(1)

    ctx.obj['client'] = client
    ctx.obj['CONFIG'] = cfg
    ctx.obj['bbs'] = server
    ctx.obj['db'] = db

@click.command()
@click.pass_context
def query_server(ctx):
    """Query the server for basic info."""
    client = ctx.obj['client']
    req = Request.blank()
    req.path = ""
    req.method = Request.Method.GET
    resp = client.send_receive_callsign(req, ctx.obj['bbs'])
    if resp is None:
        click.echo(f"No response from {ctx.obj['bbs']}")
        exit_client(ctx.obj, 1)
    else:
        if resp.status_code != 200:
            exit_client(ctx.obj, 1, message=f"Error contacting server: {resp.payload}")
        else:
            click.echo(json.dumps(resp.payload, indent=2))
            exit_client(ctx.obj, 0)


@click.command()
@click.argument('username', required=False, default='')
@click.option('--list-users', '-l', is_flag=True, default=False, help="If set, downloads list of all users.")
@click.option("--output-format", "-f", default="table", help="Print data as table[default], list, or JSON",
              type=click.Choice(['table', 'json', 'list'], case_sensitive=False))
@click.pass_context
def user(ctx, list_users, output_format, username):
    """Query users on the BBS. Either listing multiple users or looking up information of USERNAME"""
    client = ctx.obj['client']
    # validate args
    if list_users and (username.strip() != ""):
        exit_client(ctx.obj,1, "Can't specify a username while listing all users.")

    if not list_users and (username.strip() == ""):
        exit_client(ctx.obj,1, message="Must provide either a username or --list-users flag.")

    output_objects = []
    try:
        if list_users:
            output_objects = users.get_users(client, ctx.obj['bbs'])
        else:
            output_objects.append(users.get_user_by_username(client, ctx.obj['bbs'], username))
    except Exception as e:
        exit_client(ctx.obj,1, str(e))
    finally:
        client.stop()

    click.echo(format_list_dicts([x.pretty_dict() for x in output_objects], output_format=output_format.lower()))
    exit_client(ctx.obj, 0)

cli.add_command(user)
cli.add_command(query_server)
cli.add_command(job, name='job')

if __name__ == '__main__':
    cli()
