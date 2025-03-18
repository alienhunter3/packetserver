import os
import sys
import os.path
from email.policy import default

import click
from packetserver.client.cli.util import exit_client, format_list_dicts
from copy import deepcopy
from uuid import UUID
from packetserver.client.messages import *

@click.group()
@click.pass_context
def message(ctx):
    """Send, search, and filter messages to and from other users on the BBS system."""
    pass

@click.command()
@click.argument("recipients", type=str)
@click.argument("body", type=str)
@click.option("--body-filename", '-f', is_flag=True, default=False, help="Treat body argument as a filename to read body text from. '-' to read from stdin.")
@click.option("--attachment", "-A", multiple=True, default=[],
              help="Files to attach to message in form '[<t|b>:]<filename>' use 't' for text (default), 'b' to interpret file as binary data.")
@click.pass_context
def send(ctx, recipients, body, body_filename, attachment):
    """Send a message to one or more recipients.

        <recipients> should be a comma-separated list of recipients to send the message to

        <body> should be either body text, or a filename (or '-' for stdin) to read body text from
    """
    client = ctx.obj['client']
    bbs = ctx.obj['bbs']

    recips = [x.strip() for x in recipients.split(",") if x.strip() != ""]

    if len(recips) == 0:
        click.echo("You must specify at least one recipient.", err=True)
        exit_client(ctx.obj, 89)

    attachments = []
    for a in attachment:
        is_text = True
        filename = a
        if len(a) > 1:
            if a[1] == ":":
                filename = a[2:]
                if a[0].lower() == "b":
                    is_text = False
        try:
            attachments.append(attachment_from_file(filename, binary=not is_text))
        except Exception as e:
            click.echo(str(e), err=True)
            exit_client(ctx.obj, 89)

    if len(attachments) == 0:
        attachments = None

    if body_filename:
        if body == "-":
            body_text = sys.stdin.read()
        else:
            if not os.path.isfile(body):
                click.echo(f"{body} is not a file that can be read for body text.", err=True)
                exit_client(ctx.obj, 92)
                sys.exit(92)
            try:
                body_text = open(body, "r").read()
            except:
                click.echo(f"{body} is not a file that can be read for body text.", err=True)
                exit_client(ctx.obj, 92)
                sys.exit(92)
    else:
        body_text = body

    try:
        resp = send_message(client, bbs, body_text, recips, attachments=attachments)
        click.echo(f"Message received by server: {resp}")
        exit_client(ctx.obj, 0)
    except Exception as e:
        click.echo(f"Error sending message: {str(e)}", err=True)
        exit_client(ctx.obj, 53)

message.add_command(send)



