This whole project is still a major WIP. Details to follow.

Basically, this is supposed to be a modernized BBS for radio,
but with clients and servers exchanging binary messages 
(which can be compressed automatically) rather than human-typed text.

Right now, it will use ax25 connected sessions through AGWPE, 
though I may add an unconnected protocol using UI later on..

Features completed:

- Object CRUD operations
- Podman containerized job orchestrator
- automatic compression for all RF communication

Features in-progress and working to some extent:

- Send and searching messages to/from other users
- object storage/retrieval
- running user-defined scripts or shell commands on the server in containers with podman/docker
- Posting, retrieving, and editing public bulletins
- Partial Python client wrapper library for the RF 'API'

I'm considering several other features like:

- Useful documentation of any variety..
- RF beacon
- administration over RF
- possibly a cron system (again in containers for safety)
- maybe an e-mail or an sms gateway (though clever user uploaded scripts could do this instead)
- maybe APRS integration through APRS-IS
- Kubernetes or possibly simple shell job execution.

I may also add a TCP/IP interface to this later, since that shouldn't be too difficult. We'll see.

I'm envisioning using a couple of python CLI clients with this for now, or possibly an android or 
PC GUI, assuming an AGWPE TNC is available on the network.
