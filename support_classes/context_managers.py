from contextlib import contextmanager
import cv2
from typing import Any
import numpy as np
from pygame.surface import Surface
from pygame.surfarray import array3d
import pygame.camera as camera

from support_classes.settings_interface import Settings, read_settings

__USE_PYGAME = False

def initialise_pygame():
    camera.init(backend="_camera (MSMF)")

@contextmanager
def open_video_device(index: int):
    if __USE_PYGAME:
        all_cams = camera.list_cameras()
        cam = camera.Camera(all_cams[index])
        try:
            cam.start()
            yield cam
        finally:
            cam.stop()
    else:
        cap = cv2.VideoCapture(index)
        settings = read_settings(Settings.AUTO_EXPOSURE,Settings.EXPOSURE_TIME)
        if not settings[Settings.AUTO_EXPOSURE]:
            cap.set(cv2.CAP_PROP_AUTO_EXPOSURE,0)
            cap.set(cv2.CAP_PROP_EXPOSURE,settings[Settings.EXPOSURE_TIME])    
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
            if isinstance(vc,camera.Camera):
                surf = vc.get_image()
                cap = pygame_to_cv2(surf)
                return cap
            is_retrieved, cap = vc.read()
            if not is_retrieved:
                raise CaptureException("Image not retrieved")
        return cap
    raise TypeError("Capture argument must be int or str")

def pygame_to_cv2(surf: Surface) -> np.ndarray:
    img = array3d(surf)
    img = img.transpose([1, 0, 2])
    img = cv2.cvtColor(img,cv2.COLOR_RGB2BGR)
    return img

class CaptureException(BaseException):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)