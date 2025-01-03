This whole project is still a major WIP. Details to follow.

Basically, this is supposed to be a modernized BBS for radio,
but with clients and servers exchanging binary messages 
(which can be compressed automatically) rather than human-typed text.

I'm planning several features like:

- automatic compression for all RF communication
- messages for other users
- RF beacon
- administration over RF
- object storage/retrieval
- running user-scripts scripts or shell commands on the server in containers with podman/docker
- possibly a cron system (again in containers for safety)
- maybe an e-mail or an sms gateway (though clever user uploaded scripts could do this instead)
- maybe APRS integration through APRS-IS

I may also add a TCP/IP interface to this later, since that shouldn't be too difficult. We'll see.

I'm envisioning using a couple of python CLI clients with this for now, or possibly an android or 
PC GUI, assuming an AGWPE TNC is available on the network.
