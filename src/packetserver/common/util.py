import re

def email_valid(email: str) -> bool:
    """Taken from https://www.geeksforgeeks.org/check-if-email-address-valid-or-not-in-python/"""
    regex = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b'
    if re.fullmatch(regex, email):
        return True
    else:
        return False
