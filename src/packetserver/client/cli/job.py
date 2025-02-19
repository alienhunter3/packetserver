"""CLI client for dealing with jobs."""
import os

import click
from persistent.mapping import default
from packetserver.client import Client
from packetserver.client.jobs import JobSession
import datetime
from packetserver.client.cli.util import exit_client

@click.group()
@click.pass_context
def job(ctx):
    """Runs commands on the BBS server if jobs are enabled on it."""
    pass

@click.command()
@click.pass_context
def start():
    """Start a job on the BBS server."""
    pass

@click.command()
@click.pass_context
def get():
    """Retrieve a job"""
    pass

@click.command()
@click.option("--transcript", "-T", default="", help="File to write command transcript to if desired.")
@click.pass_context
def quick_session(ctx, transcript):
    """Start a session to submit multiple commands and receive responses immediately"""
    session_transcript = []
    client = ctx.obj['client']
    bbs = ctx.obj['bbs']
    js = JobSession(client, bbs, stutter=2)
    db_enabled = True
    while True:
        cmd = click.prompt("CMD", prompt_suffix=" >")
        cmd = cmd.strip()
        session_transcript.append((datetime.datetime.now(),"c",cmd))
        next_db = False
        if db_enabled:
            next_db = True
        db_enabled = False
        if cmd == "":
            continue
        if cmd == "/exit":
            break
        elif cmd == "/db":
            click.echo("DB requested for next command.")
            db_enabled = True
        else:
            try:
                job_result = js.send_quick(['bash', '-c', cmd], db=next_db)
                output = job_result.output_str + "\n" + "Errors: " + job_result.errors_str
                session_transcript.append((datetime.datetime.now(), "r", output))
                click.echo(output)
            except Exception as e:
                session_transcript.append((datetime.datetime.now(), "e", e))
                click.echo(f"ERROR! {str(e)}", err=True)
                continue
    try:
        if transcript.strip() != "":
            with open(transcript.strip(), 'w') as tran_file:
                for l in session_transcript:
                    tran_file.write(f"{l[1]}:{l[0].isoformat()}: {l[2]}{os.linesep}")
    finally:
        exit_client(ctx.obj, 0)


job.add_command(quick_session)