import os
import sys
import os.path
from email.policy import default

import click
from zodbpickle.pickle_3 import FALSE

from packetserver.client.cli.util import exit_client, format_list_dicts, unit_seconds
from copy import deepcopy
from uuid import UUID
import datetime
import re
import json
from packetserver.client.messages import *

rel_date = '^-(\\d+)([dhms])$'

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


@click.command()
@click.option("--number", "-n", type=int, default=0,help="Retrieve the first N messages matching filters/sort. 0 for all.")
@click.option('--sent', '-S', is_flag=True, default=False, help="Include sent messages in results.")
@click.option("--not-received", "-R", is_flag=True, default=False, help="Don't include received messages.")
@click.option("--ascending", "-A", is_flag=True, default=False, help="Show older/smaller results first after sorting.")
@click.option("--no-attachments", "-N", is_flag=True, default=False, help="Don't fetch attachment data.")
@click.option("--uuid", "-u", type=str, default=None, help="If specified, ignore other filters and retrieve only messages matching uuid.")
@click.option("--since-date", "-d", type=str, default=None, help="Only include messages since date (iso format), or '-<num><unit Mdyhms>' ex: -5d")
@click.option("--output-format", "-f", default="table", help="Print data as table[default], list, or JSON",
              type=click.Choice(['table', 'json', 'list'], case_sensitive=False))
@click.option("--save-copy", "-C", is_flag=True, default=False, help="Save a full copy of each message to fs.")
@click.option("--search", "-F", type=str, default="", help="Return only messages containing search string.")
@click.option("--no-text", "-T", is_flag=True, default=False, help="Don't return the message text.")
@click.option("--sort-by", "-B", default="date", help="Choose to sort by 'date', 'from', or 'to'",
              type=click.Choice(['date', 'from', 'to'], case_sensitive=False))
@click.pass_context
def get(ctx, number, sent, not_received, ascending, no_attachments, uuid, since_date, output_format, save_copy,
        search, no_text, sort_by):
    client = ctx.obj['client']
    bbs = ctx.obj['bbs']
    messages = []
    get_attach = not no_attachments
    get_text = not no_text
    reverse = not ascending
    if uuid is not None:
        try:
            uuid = UUID(uuid)
        except:
            exit_client(ctx.obj, 52, message="Must provide a valid UUID.")

    if type(search) is str and (search.strip() == ""):
        search = None
    if not_received:
        if sent:
            source='sent'
        else:
            exit_client(ctx.obj, 23, "Can't exclude both sent and received messages.")
    else:
        if sent:
            source='all'
        else:
            source='received'

    if number == 0:
        limit = None
    else:
        limit = number

    if since_date is not None:
        if len(since_date) < 3:
            exit_client(ctx.obj, 41, "Invalid date specification.")

        if since_date[0] == "-":
            m = re.match(rel_date, since_date)
            if m is None:
                exit_client(ctx.obj, 41, "Invalid date specification.")
            else:
                unit = m.group(2).lower()
                multiplier = int(m.group(1))
                if unit not in unit_seconds:
                    exit_client(ctx.obj, 41, "Invalid date specification.")
                total_seconds = int(multiplier * unit_seconds[unit])
                cutoff_date = datetime.datetime.now() - datetime.timedelta(seconds=total_seconds)
        else:
            try:
                cutoff_date = datetime.datetime.fromisoformat(since_date)
            except:
                exit_client(ctx.obj, 41, "Invalid date specification.")

    if type(uuid) is UUID:
        try:
            messages.append(get_message_uuid(client, bbs, uuid, get_attachments=get_attach))
        except Exception as e:
            exit_client(ctx.obj, 40, message=f"Couldn't get message specified: {str(e)}")
    elif since_date is not None:
        try:
            messages = get_messages_since(client, bbs, cutoff_date, get_text=get_text, limit=limit, sort_by=sort_by,
                                          reverse=reverse, search=search, get_attachments=get_attach, source=source)
        except Exception as e:
            exit_client(ctx.obj, 40, message=f"Couldn't fetch messages: {str(e)}")
    else:
        try:
            messages = get_messages(client, bbs, get_text=get_text, limit=limit, sort_by=sort_by, reverse=reverse,
                                search=search, get_attachments=get_attach, source=source)
        except Exception as e:
            exit_client(ctx.obj, 40, message=f"Couldn't fetch messages: {str(e)}")

    save_dir = os.path.join(ctx.obj['directory'], 'message_cache')
    if save_copy:
        if not os.path.isdir(save_dir):
            os.mkdir(save_dir)

    message_display = []
    for msg in messages:
        json_filename = f"{msg.sent.strftime("%Y%m%d%H%M%s")}-{msg.from_user}.json"
        json_path = os.path.join(save_dir, json_filename)
        if save_copy:
            json.dump(msg.to_dict(json=True), open(json_path, 'w'))
        d = {
            'from': msg.from_user,
            'to': ",".join(msg.to_users),
            'id': str(msg.msg_id),
            'text': msg.text,
            'sent_at': msg.sent.isoformat(),
            'attachments': "",
        }
        if len(msg.attachments) > 0:
            d['attachments'] = ",".join([a.name for a in msg.attachments])

        if save_copy:
            d['saved_path'] = json_path
        message_display.append(d)
    exit_client(ctx.obj, 0, format_list_dicts(message_display, output_format=output_format))




message.add_command(get)
message.add_command(send)



