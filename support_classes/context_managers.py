from contextlib import contextmanager
import cv2
from typing import Any
import numpy as np

@contextmanager
def open_video_device(index: int):
    cap = cv2.VideoCapture(index)
    try:
        yield cap
    finally:
        cap.release()

@contextmanager
def open_cv2_window(name: str):
    try:
        cv2.namedWindow(name)
        yield name
    finally:
        cv2.destroyWindow(name)

def capture(arg0: Any) -> np.array:
    if isinstance(arg0,str):
        cap = cv2.imread(arg0)
        return cap
    if isinstance(arg0,int):
        with open_video_device(arg0) as vc:
            is_retrieved, cap = vc.read()
        if not is_retrieved:
            raise CaptureException("Image not retrieved")
        return cap
    raise TypeError("Capture argument must be int or str")

class CaptureException(BaseException):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)