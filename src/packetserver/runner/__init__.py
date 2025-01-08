"""Package runs arbitrary commands/jobs via different mechanisms."""
from typing import Union,Optional,Iterable,Self

class Runner:
    """Abstract class to take arguments and run a job and track the status and results."""
    def __init__(self, args: Iterable[str], ):
        pass
