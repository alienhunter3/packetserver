import re
import datetime
import tempfile
import tarfile
from typing import Union, Iterable, Tuple, Optional
import os.path
from io import BytesIO
import random
import string

def email_valid(email: str) -> bool:
    """Taken from https://www.geeksforgeeks.org/check-if-email-address-valid-or-not-in-python/"""
    regex = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b'
    if re.fullmatch(regex, email):
        return True
    else:
        return False

def to_date_digits(index: datetime.datetime) -> str:
    return f"{str(index.year).zfill(4)}{str(index.month).zfill(2)}{str(index.day).zfill(2)}{str(index.hour).zfill(2)}{str(index.minute).zfill(2)}{str(index.second).zfill(2)}"

def from_date_digits(index: str) -> datetime:
    ind = str(index)
    if not ind.isdigit():
        raise ValueError("Received invalid date digit string, containing non-digit chars.")
    if len(ind) < 4:
        raise ValueError("Received invalid date digit string, needs to at least by four digits for a year")
    year = int(ind[:4])
    month = 1
    day = 1
    hour = 0
    minute = 0
    second = 0
    if len(ind) >= 6:
        month = int(ind[4:6])

    if len(ind) >= 8:
        day = int(ind[6:8])

    if len(ind) >= 10:
        hour = int(ind[8:10])

    if len(ind) >= 12:
        minute = int(ind[10:12])

    if len(ind) >= 14:
        second = int(ind[12:14])

    return datetime.datetime(year, month, day ,hour, minute, second)

def tar_bytes(file: Union[str, Iterable]) -> bytes:
    """Creates a tar archive in a temporary file with the specified files at root level.
    Returns the bytes of the archive."""
    files = []
    if type(file) is str:
        files.append(file)
    else:
        for i in file:
            files.append(str(i))

    with tempfile.TemporaryFile() as temp:
        tar_obj = tarfile.TarFile(fileobj=temp, mode="w")
        for i in files:
            tar_obj.add(i, arcname=os.path.basename(i))
        tar_obj.close()
        temp.seek(0)
        return temp.read()

def bytes_to_tar_bytes(name: str, data: bytes) -> bytes:
    """Creates a tar archive with a single file of name <name> with <data> bytes as the contents"""
    with tempfile.TemporaryFile() as temp:
        tar_obj = tarfile.TarFile(fileobj=temp, mode="w")
        bio = BytesIO(data)
        tar_info = tarfile.TarInfo(name=name)
        tar_info.size = len(data)
        tar_obj.addfile(tar_info, bio)
        tar_obj.close()
        temp.seek(0)
        return temp.read()

def extract_tar_bytes(tarfile_bytes: bytes) -> Tuple[str, bytes]:
    """Takes the bytes of a tarfile, and returns the name and bytes of the first file in the archive."""
    out_bytes = b''
    bio = BytesIO(tarfile_bytes)
    tar_obj = tarfile.TarFile(fileobj=bio, mode="r")
    members = tar_obj.getmembers()
    for i in range(0, len(members)):
        if members[i].isfile():
            return members[i].name, tar_obj.extractfile(members[i]).read()
    raise FileNotFoundError("No files found to extract from archive")

def random_string(length=8) -> str:
    rand_str = ''.join(random.choices(string.ascii_letters + string.digits, k=length))
    return rand_str

