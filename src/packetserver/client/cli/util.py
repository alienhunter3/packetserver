from tabulate import tabulate
import json
import click
from packetserver.client import Client
import sys

def format_list_dicts(dicts: list[dict], output_format: str = "table"):
    if output_format == "table":
        return tabulate(dicts, headers="keys")

    elif output_format == "json":
        return json.dumps(dicts, indent=2)

    elif output_format == "list":
        output = "-------------\n"
        for i in dicts:
            t = []
            for key in i:
                t.append([str(key), str(i[key])])
            output = output + tabulate(t) + "-------------\n"

    else:
        raise ValueError("Unsupported format type.")

def exit_client(client: Client, return_code: int, message=""):
    client.stop()
    if return_code == 0:
        is_err = False
    else:
        is_err = True
    if message.strip() != "":
        click.echo(message, err=is_err)
    sys.exit(return_code)





