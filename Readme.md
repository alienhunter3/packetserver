# PacketServer BBS

*DISCLAIMER* This whole project is still a major WIP.

*HUGE HUGE THANKS TO https://github.com/mfncooper* for providing the pyham_pe package 
that this uses to talk to the TNC

## Intro

Basically, this is supposed to be a modernized BBS for radio,
but with clients and servers exchanging binary messages 
(which can be compressed automatically) rather than human-typed text.

This compression is inherent to the protocol, and actually results in 
some pretty large transmission time savings when sending longer
messages back and forth!

The downside is that right now, this BBS system will be useless to someone
without the client library. You won't be able to just type in messages to the server.
I may add some kind of workaround for this.

Right now, it uses ax25 connected sessions through any TNC that can 
provide an AGWPE TNC, though I may add a restricted unconnected protocol using 
UI packets later on..

## Requirements

- A radio of some kind that can transmit on a band suitable for any kind of AX25 packet work.
- A way to connect the radio to a Linux machine (for hosting using the container orchestrator) or just anything that runs Python for the client. I recommend DigiRig.
- A TNC that provides an AGWPE interface. Direwolf works; there are others for different platforms.
- Recent Python (Python 3.11+.)
- A version of the pyham_pe package that fixes the minor bug with incoming connections. (https://github.com/alienhunter3/pyham_pe_bugfix_incoming_connections)


## Features completed:

- protocol using connected mode sessions to provide request/response architecture
- Object CRUD operations
- Server-side Podman containerized job orchestrator
- automatic compression for all RF communication
- Creating and retrieving bulletins
- Sending and receiving and searching messages to/from other users


## Features in-progress and working to some extent:

- corresponding Python client wrapper library for most elements of the server-side (RF) API (enough for basic usage anyway)
- Python CLI client supporting:
  - listing registered users on the server
  - setting and retrieving personal user profile details
  - uploading files as objects, searching objects on server, downloading object data
  - sending and retrieving messages to other users including attached arbitrary string and binary data
  - running basic scripts/commands as jobs on the server inside containers

## Planned features not yet implemented:

- client API and CLI capability to fully interact with the job system including getting artifacts back from jobs
- client API and CLI capability to set and retrieve bulletins
- editing public bulletins, once created
- client/server API capability to modify objects


## I'm considering several other features like:

- Useful documentation of any variety..
- RF beacon
- service administration over RF
- cli server administration tools
  - Right now, just edit the server's zope database with a python interpreter (included example scripts to help)
- possibly a cron system (again in containers for safety)
- maybe an e-mail or an sms gateway (though clever user uploaded scripts could do this instead)
- maybe APRS integration through APRS-IS
- Kubernetes or possibly simple shell job execution.


## Examples

### Main help dialog:
```commandline
(venv) [user@host]$ packcli
Usage: packcli [OPTIONS] COMMAND [ARGS]...

  Command line interface for the PacketServer client and server API.

Options:
  --conf TEXT          path to configfile
  -s, --server TEXT    server radio callsign to connect to (required)
  -a, --agwpe TEXT     AGWPE TNC server address to connect to (config file)
  -p, --port INTEGER   AGWPE TNC server port to connect to (config file)
  -c, --callsign TEXT  radio callsign[+ssid] of this client station (config
                       file)
  -k, --keep-log       Save local copy of request log after session ends?
  -v, --version        Show the version and exit.
  --help               Show this message and exit.

Commands:
  job           Runs commands on the BBS server if jobs are enabled on it.
  message       Send, search, and filter messages to and from other users...
  object        Manages objects stored on the BBS.
  query-server  Query the server for basic info.
  set           Set your user profile settings on the BBS.
  user          Query users on the BBS.
```

### Working with objects:
```commandline
(venv) [user@host]$ packcli object list
name               size_bytes  binary    private    created_at                        modified_at                       uuid
---------------  ------------  --------  ---------  --------------------------------  --------------------------------  ------------------------------------
testdb.txt            13        False     True       2025-03-16T22:26:05.049173+00:00  2025-03-16T22:26:05.051375+00:00  fbbd4527-a5f0-447f-9fc9-55b7b263c458

(venv) [user@host]$ packcli object upload-file 
Usage: packcli object upload-file [OPTIONS] FILE_PATH
Try 'packcli object upload-file --help' for help.

Error: Missing argument 'FILE_PATH'.

(venv) [user@host]$ packcli object upload-file /tmp/hello-world.txt 
35753577-21e3-4f64-8776-e3f86f1bb0e0

(venv) [user@host]$ packcli object list
name               size_bytes  binary    private    created_at                        modified_at                       uuid
---------------  ------------  --------  ---------  --------------------------------  --------------------------------  ------------------------------------
testdb.txt                 13  False     True       2025-03-16T22:26:05.049173+00:00  2025-03-16T22:26:05.051375+00:00  fbbd4527-a5f0-447f-9fc9-55b7b263c458
hello-world.txt            13  False     True       2025-03-19T02:25:41.501833+00:00  2025-03-19T02:25:41.503502+00:00  35753577-21e3-4f64-8776-e3f86f1bb0e0

(venv) packcli object get 35753577-21e3-4f64-8776-e3f86f1bb0e0
Hello world.

```

### Retrieving messages:
```commandline
(venv) [user@host]$ packcli message get 
from    to      id                                    text                             sent_at                           attachments
------  ------  ------------------------------------  -------------------------------  --------------------------------  -------------
KQ4PEC  KQ4PEC  df7493d7-5880-4c24-9e3c-1d3987a5203e  testing.. again with attachment  2025-03-18T03:41:36.597371+00:00  random.txt
KQ4PEC  KQ4PEC  e3056cdf-1f56-4790-8aef-dfea959bfa13  from stdin                       2025-03-18T03:40:36.051667+00:00
KQ4PEC  KQ4PEC  992c3e81-005a-49e2-81d7-8bf3026a2c46  testing.. again                  2025-03-18T03:40:05.025017+00:00
KQ4PEC  KQ4PEC  05684b13-40f8-40aa-ab7a-f50a3c22261e  testing.. 1.. 2.. 3              2025-03-18T03:39:50.510164+00:00
KQ4PEC  KQ4PEC  ad513075-e50f-4f84-8a87-a1217b43bef3  testing.. 1.. 2.. 3              2025-03-18T03:38:01.634498+00:00
```

### Listing users:
```commandline
(venv) [user@host]$ packcli user -l
username    status                 bio    socials    created                           last_seen                         email            location
----------  ---------------------  -----  ---------  --------------------------------  --------------------------------  ---------------  ----------
KQ4PEC      just happy to be here                    2025-03-16 04:29:52.044216+00:00  2025-03-19 02:22:21.413896+00:00  user@domain.com
```

### 

## Final Thoughts

I may also add a TCP/IP interface to this later, since that shouldn't be too difficult. We'll see.

I'm envisioning using a couple of python CLI clients with this for now, or possibly an android or 
PC GUI, assuming an AGWPE TNC is available on the network.
