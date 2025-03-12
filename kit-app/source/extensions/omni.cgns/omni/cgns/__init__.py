from ._cgns import *
from functools import lru_cache

@lru_cache()
def get_interface() -> ICgns:
    """Returns cached :class:` omni.cgns.ICgns` interface"""
    return acquire_cgns_interface()
