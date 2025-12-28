FROM debian

USER root

RUN apt-get update && apt-get install -y elinks whois wget python3 knot-dnsutils python3-requests\
	openssh-client curl inetutils-ping nmap aria2 git less jq 7zip p7zip-full p7zip unzip zip yq rsync ddgr bzip2\
	&& apt-get clean && rm -rf /var/lib/apt/lists/* 

RUN mkdir -p /root/bin

COPY root_scripts/* /root/bin/

RUN chmod 700 /root/bin/*
