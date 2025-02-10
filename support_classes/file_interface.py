import os
from pathlib import Path
from contextlib import contextmanager


LOCAL_DIRECTORY = Path().absolute().parent/"local"

def get_path(filepath: Path|str) -> Path:
    return LOCAL_DIRECTORY/filepath

@contextmanager
def open_local(filepath: Path|str, mode: str, *args, **kwargs):
    pth = get_path(filepath)
    if ("w" in mode or "a" in mode or "x" in mode) and not os.path.isdir(pth.parent):
        os.mkdir(pth.parent)
    with open(pth,mode,*args,**kwargs) as f:
        yield f
