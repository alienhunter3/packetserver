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

- A radio of some kind that can transmit on a band suitable for any AX25 packet encoding.
- A way to connect the radio to a Linux machine (for hosting using the container orchestrator) or just anything that runs Python for the client. I recommend DigiRig.
- A TNC that provides an AGWPE interface. Direwolf works; there are others for different platforms.
- Recent Python (Python 3.11+.)
- A fixed version of the pyham_pe package that will can properly identify incoming connections from outgoing. (https://github.com/alienhunter3/pyham_pe_bugfix_incoming_connections)


## Features completed:

- Object CRUD operations
- Podman containerized job orchestrator
- automatic compression for all RF communication

## Features in-progress and working to some extent:

- Send and searching messages to/from other users
- Posting, retrieving, and editing public bulletins
- Partial Python client wrapper library for the complete RF 'API'

## I'm considering several other features like:

- Useful documentation of any variety..
- RF beacon
- bbs administration over RF
- cli bbs administration tools
  - Right now, just edit the database with a python interpreter
- possibly a cron system (again in containers for safety)
- maybe an e-mail or an sms gateway (though clever user uploaded scripts could do this instead)
- maybe APRS integration through APRS-IS
- Kubernetes or possibly simple shell job execution.

## Final Thoughts

I may also add a TCP/IP interface to this later, since that shouldn't be too difficult. We'll see.

I'm envisioning using a couple of python CLI clients with this for now, or possibly an android or 
PC GUI, assuming an AGWPE TNC is available on the network.
