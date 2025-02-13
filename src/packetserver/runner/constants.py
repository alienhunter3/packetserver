from packetserver.common.util import multi_bytes_to_tar_bytes

container_setup_script = """#!/bin/bash
useradd -m -s /bin/bash "$PACKETSERVER_USER" -u 1000
mkdir -p "/home/${PACKETSERVER_USER}/.packetserver/artifacts"
mkdir -p /artifact_output
chown -R $PACKETSERVER_USER "/home/$PACKETSERVER_USER"
"""

job_setup_script = """#!/bin/bash
chmod 444 /user-db.json.gz
chown -R $PACKETSERVER_USER "/home/$PACKETSERVER_USER"
mkdir -p "/home/$PACKETSERVER_USER/.packetserver/artifacts/$PACKETSERVER_JOBID"
"""

job_end_script = """#!/bin/bash
PACKETSERVER_ARTIFACT_DIR="/home/$PACKETSERVER_USER/.packetserver/artifacts/$PACKETSERVER_JOBID"
PACKETSERVER_ARTIFACT_TAR="/artifact_output/${PACKETSERVER_JOBID}.tar"
cwd=$(pwd)
if [ $(find "$PACKETSERVER_ARTIFACT_DIR" | wc -l) -gt "1" ]; then
    cd $PACKETSERVER_ARTIFACT_DIR
    tar -cf ${PACKETSERVER_ARTIFACT_TAR} .
fi
rm -rf ${PACKETSERVER_ARTIFACT_DIR}
"""
