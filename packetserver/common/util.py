import re
import datetime
import tempfile
import tarfile
from typing import Union, Iterable, Tuple, Optional, IO
import os.path
from io import BytesIO, BufferedReader
import random
import string
from persistent.mapping import PersistentMapping
from persistent.list import PersistentList

# Pre-compiled regex for performance
_AX25_CALLSIGN_REGEX = re.compile(
    r'^[A-Z0-9]{1,6}(-[0-9]{1,2})?$'
)

# Regex for base callsign only (no SSID)
_BASE_CALLSIGN_REGEX = re.compile(r'^[A-Z][A-Z0-9]{0,5}$')

def email_valid(email: str) -> bool:
    """Taken from https://www.geeksforgeeks.org/check-if-email-address-valid-or-not-in-python/"""
    regex = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b'
    if re.fullmatch(regex, email):
        return True
    else:
        return False

def to_date_digits(index: datetime.datetime) -> str:
    return f"{str(index.year).zfill(4)}{str(index.month).zfill(2)}{str(index.day).zfill(2)}{str(index.hour).zfill(2)}{str(index.minute).zfill(2)}{str(index.second).zfill(2)}"

def from_date_digits(index: str, tz: datetime.timezone = datetime.UTC) -> datetime:
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

    return datetime.datetime(year, month, day ,hour, minute, second, tzinfo=tz)

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

def bytes_tar_has_files(data: Union[bytes, IO]):
    if type(data) is bytes:
        bio = BytesIO(data)
    else:
        bio = data
    tar_obj = tarfile.TarFile(fileobj=bio, mode="r")
    files = [m for m in tar_obj.getmembers() if m.isfile()]
    if len(files) > 0:
        return True
    else:
        return False

def multi_bytes_to_tar_bytes(objects: dict) -> bytes:
    """Creates a tar archive with a single file of name <name> with <data> bytes as the contents"""
    with tempfile.TemporaryFile() as temp:
        tar_obj = tarfile.TarFile(fileobj=temp, mode="w")
        for name in objects:
            data = bytes(objects[name])
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


class TarFileExtractor(object):
    """Generator created from file like object pointing to tar data"""
    def __init__(self, fileobj: IO):
        self.fileobj = fileobj
        try:
            self.tar_file = tarfile.TarFile(fileobj=self.fileobj)
            self._raw_members = [m for m in self.tar_file.getmembers() if m.isfile()]
        except:
            self._raw_members = []
        self._count = 0

    def __iter__(self):
        return self

    # Python 3 compatibility
    def __next__(self):
        return self.next()

    def next(self) -> Tuple[str, IO]:
        if (self._count + 1) > len(self._raw_members):
            raise StopIteration()
        else:
            member = self._raw_members[self._count]
            name = member.name
            if type(name) is bytes:
                name = name.decode()
            name = str(name)
            self._count = self._count + 1
            return os.path.basename(name), self.tar_file.extractfile(member)

def convert_to_persistent(data: Union[list,dict]):
    if isinstance(data, dict):
        persistent_dict = PersistentMapping()
        for key, value in data.items():
            persistent_dict[key] = convert_to_persistent(value)
        return persistent_dict
    elif isinstance(data, list):
        return PersistentList([convert_to_persistent(item) for item in data])
    else:
        return data

def convert_from_persistent(data):
    if isinstance(data, PersistentMapping):
        nonpersistent_dict = {}
        for key, value in data.items():
            nonpersistent_dict[key] = convert_from_persistent(value)
        return nonpersistent_dict
    elif isinstance(data, PersistentList):
        return [convert_from_persistent(item) for item in data]
    else:
        return data

def is_valid_ax25_callsign(callsign: str) -> bool:
    """
    Validate an AX.25 callsign (with optional SSID).

    Rules:
    - Base: 1-6 uppercase alphanumeric, must start with letter (A-Z)
    - Optional: single '-' followed by 1-2 digits (0-15)
    - No spaces, lowercase, or other characters

    Examples:
        W1AW       → True
        W1AW-1     → True
        W1AW-15    → True
        1A2BCD     → False (starts with digit)
        w1aw       → False (lowercase)
        W1AW-     → False (no SSID digits)
        W1AW--1    → False (double dash)
        W1AW-16    → False (SSID >15)
    """
    if not callsign:
        return False
    callsign = callsign.strip().upper()
    if not _AX25_CALLSIGN_REGEX.match(callsign):
        return False

    # Extra check: base must start with letter (not digit)
    base = callsign.split('-')[0]
    if not base[0].isalpha():
        return False

    # If SSID present, ensure 0-15
    if '-' in callsign:
        ssid_str = callsign.split('-')[1]
        if int(ssid_str) > 15:
            return False

    return True

def is_valid_base_ax25_callsign(base_call: str) -> bool:
    """
    Validate an AX.25 **base** callsign (without SSID).

    Rules:
    - 1–6 characters total
    - Must start with an uppercase letter (A–Z)
    - Remaining characters: uppercase letters A–Z or digits 0–9
    - No hyphen, no SSID, no other characters

    Examples:
        W1AW     → True
        M0XYZ    → True
        K9ABC    → True (6 chars)
        1ABC     → False (starts with digit)
        W1AW-    → False (has hyphen)
        W1AW-1   → False (has SSID)
        w1aw     → False (lowercase)
        A        → True (single letter)
        ABC1234  → False (7 chars)

    Use this when you specifically need the base portion (e.g., before adding SSID).
    """
    if not base_call:
        return False
    base_call = base_call.strip().upper()
    return bool(_BASE_CALLSIGN_REGEX.match(base_call))