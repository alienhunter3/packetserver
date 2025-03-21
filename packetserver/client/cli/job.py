"""CLI client for dealing with jobs."""
import os
import os.path
import json
import click
import traceback
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
@click.argument("cmd", nargs=-1)
@click.option('--bash', '-B', is_flag=True, default=False, help="Run command with /bin/bash -c {}")
@click.option('--quick', '-q', is_flag=True, default=False, help="Wait for fast job results in the response.")
@click.option("--database", "-D", is_flag=True, default=False, help="Request copy of user db for job.")
@click.option("--env", '-e', multiple=True, default=[], help="'<key>=<val>' pairs for environment of job.")
@click.option("--file", '-F', multiple=True, default=[], help="Upload given file to sit in job directory.")
@click.option("--output-format", "-f", default="list", help="Print data as table[default], list, or JSON",
              type=click.Choice(['table', 'json', 'list'], case_sensitive=False))
@click.option("--save-copy", "-C", is_flag=True, default=False, help="Save a full copy of each job to fs.")
@click.pass_context
def start(ctx, bash, quick, database, env, file, cmd, output_format, save_copy):
    """Start a job on the BBS server with '$packcli job start [opts] -- <CMD> <ARGS>'"""
    client = ctx.obj['client']
    bbs = ctx.obj['bbs']
    environ = {}
    files = {}
    for i in env:
        split = i.find("=")
        if (split == -1) or ((split + 1) >= len(i)):
            exit_client(ctx.obj, 4, message=f"'{i}' is invalid env string")
        key = i[:split]
        val = i[split + 1:]
        environ[key] = val

    for f in file:
        if not os.path.isfile(f):
            exit_client(ctx.obj, 5, message=f"{f} doesn't exit.")
        files[f] = open(f,'rb').read()

    if len(environ) == 0:
        environ = None

    if len(files) == 0:
        files = None

    if bash:
        cmd = ['/bin/bash', '-c', ' '.join(cmd)]
    else:
        cmd = list(cmd)

    save_dir = os.path.join(ctx.obj['directory'], 'job_cache')
    if save_copy:
        if not os.path.exists(save_dir):
            os.mkdir(save_dir)
    try:
        if quick:
            j = send_job_quick(client, bbs, cmd, db=database, env=environ, files=files)
            dicts_out = []
            d = j.to_dict(json=True)
            if save_copy:
                file_path = os.path.join(save_dir, f"job-{j.id}.json")
                json.dump(d, open(file_path, 'w'))
                d['saved_path'] = file_path
            d['artifacts'] = ",".join([x[0] for x in d['artifacts']])
            del d['output_bytes']
            dicts_out.append(d)
            exit_client(ctx.obj, 0, message=format_list_dicts(dicts_out, output_format=output_format))
        else:
            resp = send_job(client, bbs, cmd, db=database, env=environ, files=files)
            exit_client(ctx.obj, 0, message=resp)
    except Exception as e:
        exit_client(ctx.obj, 40, message=f"Couldn't queue job: {str(e)}")


@click.command()
@click.argument('job_id', required=False, type=int, default=None)
@click.option("--all-jobs", "-A", is_flag=True, default=False, help="Get all of your jobs.")
@click.option("--id-only", "-I", is_flag=True, default=False, help="Only retrieve list of job ids.")
@click.option("--save-copy", "-C", is_flag=True, default=False, help="Save a full copy of each job to fs.")
@click.option("--no-data", '-n', is_flag=True, default=False,
              help="Don't fetch job result data, just metadata.")
@click.option("--output-format", "-f", default="list", help="Print data as table[default], list, or JSON",
              type=click.Choice(['table', 'json', 'list'], case_sensitive=False))
@click.pass_context
def get(ctx, job_id, all_jobs, no_data, id_only, save_copy, output_format):
    """Retrieve your jobs. Pass either '-a' or a job_id."""

    fetch_data = not no_data

    if (job_id is None) and not all_jobs:
        exit_client(ctx.obj, 3, message="You must either supply a job id, or --all-jobs")

    if all_jobs and (job_id is not None):
       exit_client(ctx.obj, 3, message="Can't use --all and specify a job_id.")

    if job_id is not None and id_only:
        exit_client(ctx.obj, 3, message="Can't use --id-only and specify a job_id. You already know it.")

    if save_copy and id_only:
        exit_client(ctx.obj, 3, message="Can't use --id-only and save_copy. There's no data to save.")

    client = ctx.obj['client']
    try:
        if all_jobs:
            jobs_out = get_user_jobs(client, ctx.obj['bbs'], get_data=fetch_data, id_only=id_only)
        else:
            jobs_out = [get_job_id(client,ctx.obj['bbs'], job_id, get_data=fetch_data)]

        if id_only:
            output = ",".join([str(x) for x in jobs_out])
            if output_format == "json":
                output = json.dumps([x for x in jobs_out])
            exit_client(ctx.obj, 0, message=output)
        else:
            save_dir = os.path.join(ctx.obj['directory'], 'job_cache')
            if save_copy:
                if not os.path.exists(save_dir):
                    os.mkdir(save_dir)
            dicts_out = []
            for j in jobs_out:
                d = j.to_dict(json=True)
                if save_copy:
                    file_path = os.path.join(save_dir, f"job-{j.id}.json")
                    json.dump(d, open(file_path, 'w'))
                    d['saved_path'] = file_path
                d['artifacts'] = ",".join([x[0] for x in d['artifacts']])
                del d['output_bytes']
                dicts_out.append(d)
            exit_client(ctx.obj, 0, message=format_list_dicts(dicts_out, output_format=output_format))
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
job.add_command(get)
job.add_command(start)