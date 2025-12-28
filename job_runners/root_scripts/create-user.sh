#!/bin/bash

useradd -m -s /bin/bash "$1"
mkdir -p "/home/$1/.packetserver/artifacts"
mkdir -p "/home/$1/.packetserver/objects"
