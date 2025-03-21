import click
from packetserver.client.bulletins import (get_bulletins_recent, get_bulletin_by_id, delete_bulletin_by_id,
                                           post_bulletin, BulletinWrapper)
from packetserver.client.cli.util import exit_client, format_list_dicts
from copy import deepcopy
import datetime
import sys
import os.path

@click.group()
@click.pass_context
def bulletin(ctx):
    """List, create, and delete bulletins on the BBS."""
    pass


@click.command()
@click.argument("subject", type=str)
@click.argument("body", type=str)
@click.option('--from-file', '-f', is_flag=True, default=False,
              help="Get body text from specified file or stdin ('-').")
@click.pass_context
def post(ctx, subject, body, from_file):
    """Post a bulletin with a subject and body text."""
    client = ctx.obj['client']
    bbs = ctx.obj['bbs']
    if subject.strip() == "":
        exit_client(ctx.obj, 1, message="Can't have empty subject.")

    text = ""
    if from_file:
        if body.strip() == "-":
            text = sys.stdin.read()
        else:
            if not os.path.isfile(body):
                exit_client(ctx.obj, 2, message=f"file {body} does not exist.")
            text = open(body, 'r').read()
    else:
        text = body

    try:
        bid = post_bulletin(client, bbs, subject, text)
        exit_client(ctx.obj,0, message=f"Created bulletin #{bid}!")
    except Exception as e:
        exit_client(ctx.obj, 4, message=str(e))


@click.command()
@click.option('--number', '-n', type=int, default=0, help="Number of bulletins to retrieve; default all.")
@click.option("--only-subject", '-S', is_flag=True, default=False, help="If set, don't retrieve body text.")
@click.option("--output-format", "-f", default="table", help="Print data as table[default], list, or JSON",
              type=click.Choice(['table', 'json', 'list'], case_sensitive=False))
@click.pass_context
def list_bulletin(ctx, number, only_subject, output_format):
    """List recent bulletins."""
    client = ctx.obj['client']
    bbs = ctx.obj['bbs']
    if number == 0:
        number = None

    try:
        bulletins = get_bulletins_recent(client, bbs, limit=number, only_subject=only_subject)
        bulletin_dicts = [b.to_dict(json=True) for b in bulletins]
        exit_client(ctx.obj, 0, message=format_list_dicts(bulletin_dicts, output_format=output_format))
    except Exception as e:
        exit_client(ctx.obj, 2, message=str(e))


@click.command()
@click.argument("bid", metavar="<BULLETIN ID>", type=int)
@click.option("--only-subject", '-S', is_flag=True, default=False, help="If set, don't retrieve body text.")
@click.option("--output-format", "-f", default="table", help="Print data as table[default], list, or JSON",
              type=click.Choice(['table', 'json', 'list'], case_sensitive=False))
@click.pass_context
def get(ctx, bid, only_subject, output_format):
    """Fetch the bulletin specified by bulletin ID."""
    client = ctx.obj['client']
    bbs = ctx.obj['bbs']

    try:
        bulletins = [get_bulletin_by_id(client, bbs, bid, only_subject=only_subject)]
        bulletin_dicts = [b.to_dict(json=True) for b in bulletins]
        exit_client(ctx.obj, 0, message=format_list_dicts(bulletin_dicts, output_format=output_format))
    except Exception as e:
        exit_client(ctx.obj, 2, message=str(e))


@click.command()
@click.argument("bid", metavar="<BULLETIN ID>", type=int)
@click.pass_context
def delete(ctx, bid):
    """Delete the bulletin (that you authored) specified with bulletin id."""
    client = ctx.obj['client']
    bbs = ctx.obj['bbs']

    try:
        delete_bulletin_by_id(client, bbs, bid)
        exit_client(ctx.obj, 0)
    except Exception as e:
        exit_client(ctx.obj, 2, message=str(e))


bulletin.add_command(post)
bulletin.add_command(list_bulletin, name = "list")
bulletin.add_command(get)
bulletin.add_command(delete)
