import os
import os.path
import click
from packetserver.client.objects import ObjectWrapper, post_object, post_file, get_user_objects, get_object_by_uuid
from packetserver.client.cli.util import exit_client, format_list_dicts
from copy import deepcopy
from uuid import UUID

@click.group()
@click.pass_context
def objects(ctx):
    """Manages objects stored on the BBS."""
    pass

@click.command()
@click.argument('file_path', required=True, type=str)
@click.option("--public", "-P", is_flag=True, default=False, help="Mark the object public for all users.")
@click.option("--binary", '-b', is_flag=True, default=False, help="Treat the file as binary instead of text.")
@click.option('--name', '-n', type=str, default=None, help="Name of object instead of source filename.")
@click.pass_context
def upload_file(ctx, file_path, public, name, binary):
    """Upload file to object store. Return the assigned UUID."""

    private = not public
    client = ctx.obj['client']
    if not os.path.isfile(file_path):
        click.echo(f"'{file_path}' is not a file.", err=True)
        exit_client(ctx.obj, 15)

    uuid = post_file(client, ctx.obj['bbs'], file_path, private=private, name=name, binary=binary)
    click.echo(str(uuid))
    exit_client(ctx.obj, 0)

@click.command()
@click.argument('uuid', required=True, type=str)
@click.pass_context
def get(ctx, uuid):
    """Get an object's data by its UUID."""
    client = ctx.obj['client']
    u = ""
    try:
        u = UUID(uuid)
    except ValueError as e:
        click.echo(f"'{uuid}' is not a valid UUID.", err=True)
        exit_client(ctx.obj, 13)

    try:
        obj = get_object_by_uuid(client, ctx.obj['bbs'], u, include_data=True)
        click.echo(obj.data, nl=False)
        exit_client(ctx.obj, 0)
    except Exception as e:
        click.echo(e, err=True)
        exit_client(ctx.obj, 19)


@click.command()
@click.option('--number', '-n', type=int, default=0, help="Number of objects to list. Default 0 for all.")
@click.option('--search', '-S', type=str, default=None, help="Search string to filter objects with.")
@click.option('--reverse', '-r', is_flag=True, default=False, help="Return results in reverse order.")
@click.option('--sort-by', '-B', default='date', help="Sort objects by size, date(default), or name",
              type=click.Choice(['size', 'name', 'date'], case_sensitive=False))
@click.option("--output-format", "-f", default="table", help="Print data as table[default], list, or JSON",
              type=click.Choice(['table', 'json', 'list'], case_sensitive=False))
@click.pass_context
def list_objects(ctx, number, search, reverse, sort_by, output_format):
    """Get a list of user objects without the data."""
    # def get_user_objects(client: Client, bbs_callsign: str, limit: int = 10, include_data: bool = True, search: str = None,
#                      reverse: bool = False, sort_date: bool = False, sort_name: bool = False, sort_size: bool = False)\
#         -> list[ObjectWrapper]:

    client = ctx.obj['client']
    sort_date = False
    sort_name = False
    sort_size = False

    if sort_by == "size":
        sort_size = True
    elif sort_by == "name":
        sort_name = True
    else:
        sort_date = True

    object_list = get_user_objects(client, ctx.obj['bbs'], limit=number, include_data=False, search=search,
                                   reverse=reverse, sort_date=sort_date, sort_name=sort_name, sort_size=sort_size)

    obj_dicts = []
    for x in object_list:
        d = deepcopy(x.obj_data)
        d['uuid'] = ""
        if 'uuid_bytes' in d:
            d['uuid'] = str(UUID(bytes=d['uuid_bytes']))
            del d['uuid_bytes']
        if 'data' in d:
            del d['data']
        if 'includes_data' in d:
            del d['includes_data']
        obj_dicts.append(d)

    click.echo(format_list_dicts(obj_dicts, output_format=output_format.lower()))
    exit_client(ctx.obj, 0)

objects.add_command(upload_file)
objects.add_command(list_objects, name='list')
objects.add_command(get)