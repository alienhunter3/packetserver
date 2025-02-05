import re
import datetime

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