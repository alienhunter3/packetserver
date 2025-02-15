from packetserver.common.util import multi_bytes_to_tar_bytes

container_setup_script = """#!/bin/bash
set -e
echo "Place holder for now."
"""

container_run_script = """#!/bin/bash
set -e
echo "Creating user ${PACKETSERVER_USER}"
useradd -m -s /bin/bash "${PACKETSERVER_USER}" -u 1000
echo "Creating directories."
mkdir -pv "/home/${PACKETSERVER_USER}/.packetserver"
mkdir -pv /artifact_output
chown -Rv ${PACKETSERVER_USER} "/home/${PACKETSERVER_USER}"
echo
echo "Looping. Waiting for /root/ENDNOW to exist before stopping."
while ! [ -f "/root/ENDNOW" ]; do
    sleep 1
done
echo "Ending now.."
"""

job_setup_script = """#!/bin/bash
set -e
PACKETSERVER_JOB_DIR="/home/${PACKETSERVER_USER}/.packetserver/${PACKETSERVER_JOBID}"
mkdir -pv "${PACKETSERVER_JOB_DIR}/artifacts"
chown ${PACKETSERVER_USER} "/home/${PACKETSERVER_USER}"
chown -R ${PACKETSERVER_USER} "${PACKETSERVER_JOB_DIR}"
"""

job_end_script = """#!/bin/bash
set -e
PACKETSERVER_JOB_DIR="/home/$PACKETSERVER_USER/.packetserver/${PACKETSERVER_JOBID}"
PACKETSERVER_ARTIFACT_DIR="${PACKETSERVER_JOB_DIR}/artifacts"
PACKETSERVER_ARTIFACT_TAR="/artifact_output/${PACKETSERVER_JOBID}.tar.gz"
tar -czvf "${PACKETSERVER_ARTIFACT_TAR}" -C "${PACKETSERVER_ARTIFACT_DIR}" .
rm -rfv "${PACKETSERVER_JOB_DIR}"
"""

podman_bash_start = """ echo 'waiting for /root/scripts/container_run_script.sh to exist'
while ! [ -f '/root/scripts/container_run_script.sh' ]; do
    sleep .1
done
echo 'entering /root/scripts/container_run_script.sh ...'
bash /root/scripts/container_run_script.sh
"""
podman_run_command = ["bash", "-c", podman_bash_start]