"""CLI client for dealing with jobs."""
import os

import click
from persistent.mapping import default
from packetserver.client import Client
from packetserver.client.jobs import JobSession, get_job_id, get_user_jobs, send_job, send_job_quick, JobWrapper
import datetime
from packetserver.client.cli.util import exit_client, format_list_dicts

@click.group()
@click.pass_context
def job(ctx):
    """Runs commands on the BBS server if jobs are enabled on it."""
    pass

@click.command()
@click.pass_context
def start(ctx):
    """Start a job on the BBS server."""
    pass


@click.command()
@click.argument('job_id', required=False, type=int)
@click.option("--all-jobs", "-a", is_flag=True, default=False, help="Get all of your jobs.")
@click.option("--no-data", '-n', is_flag=True, default=True,
              help="Don't fetch job result data, just metadata.")
@click.pass_context
def get(ctx, job_id, all_jobs, no_data): # TODO decide what to do with output and artifacts in a cli tool force full JSON?
    """Retrieve your jobs. Pass either '-a' or a job_id."""

    fetch_data = not no_data
    if job_id is None:
        job_id = ""
    job_id = job_id.strip()
    if all_jobs and (job_id != ""):
        click.echo("Can't use --all and specify a job_id.")

    client = ctx.obj['client']
    try:
        if all_jobs:
            jobs_out = get_user_jobs(client, ctx.obj['bbs'], get_data=fetch_data)
        else:
            jobs_out = [get_job_id(client,ctx.obj['bbs'], get_data=fetch_data)]
        dicts_out = []
        for j in jobs_out:
            pass

    except Exception as e:
        click.echo(str(e), err=True)
        exit_client(ctx.obj, 1)




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
        elif cmd in ["/h", "/?", '/H', "/help", "/HELP"]:
            click.echo("""Enter a command to run in a container, or enter one of the following special commands:
            '/h' | '/?' to get this help message
            '/exit' | '/q' to exit
            '/db' to have the remote job put a copy of your user's server db (messages/objects/etc) in a json file
                in the remote container in the working directory.
            """)
        elif cmd in ["/exit", '/q', '/quit']:
            break
        elif cmd == "/db":
            click.echo("DB requested for next command.")
            db_enabled = True
        else:
            try:
                job_result = js.send_quick(['bash', '-c', cmd], db=next_db)
                output = job_result.output_str + "\n"
                if job_result.errors_str != "":
                    output = output + "Errors: " + job_result.errors_str
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