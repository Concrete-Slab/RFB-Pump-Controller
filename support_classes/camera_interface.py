from contextlib import contextmanager
from numpy import ndarray
from .settings_interface import DEFAULT_SETTINGS, Settings, read_settings,CaptureBackend,CAMERA_SETTINGS, CV2_BACKENDS
import cv2
from pygame.surface import Surface
from pygame.surfarray import array3d
import pygame.camera as camera
from abc import ABC, abstractmethod
from typing import Callable
import platform
import time

class Capture(ABC):
    @staticmethod
    def SUPPORTED_INTERFACES() -> list[str]:
        return list(INTERFACES.keys())

    @staticmethod
    def from_settings():
        params = read_settings(*CAMERA_SETTINGS)
        interface = params[Settings.CAMERA_INTERFACE_MODULE]
        if interface in INTERFACES.keys():
            capfun = INTERFACES[interface]
        else:
            capfun = list(INTERFACES.values())[0]
        cap = capfun(params[Settings.VIDEO_DEVICE],params[Settings.AUTO_EXPOSURE],params[Settings.EXPOSURE_TIME],params[Settings.CAMERA_BACKEND])
        return cap

    def __init__(self,device_id: int, 
                 auto_exposure: bool = DEFAULT_SETTINGS[Settings.AUTO_EXPOSURE], 
                 exposure_time: int = DEFAULT_SETTINGS[Settings.EXPOSURE_TIME],
                 backend: CaptureBackend = DEFAULT_SETTINGS[Settings.CAMERA_BACKEND],
                 **kwargs) -> None:
        self._id = device_id
        self._auto_exposure = auto_exposure
        self._exposure_time = exposure_time

    @abstractmethod
    def get_image(self) -> ndarray:
        pass
    @abstractmethod
    def open(self) -> None:
        pass
    @abstractmethod
    def close(self) -> None:
        pass
    @classmethod
    @abstractmethod
    def get_cameras(cls,**kwargs) -> list[str]|None:
        pass
    @classmethod
    @abstractmethod
    def get_backends(cls) -> list[CaptureBackend]:
        pass

SetupFunction = Callable[[int,bool,int,str],Capture]

def __setup_cv2(vd_num: int,auto_exposure: bool,exposure_time: int, backend: str) -> Capture:
    actual_backend = backend if backend in CV2Capture.get_backends() else CaptureBackend.ANY
    return CV2Capture(vd_num if vd_num >= 0 else 0,auto_exposure=auto_exposure,exposure_time=exposure_time,backend=actual_backend)


def __setup_pygame(vd_num: int,auto_exposure: bool,exposure_time: int, backend: str) -> Capture:
    actual_backend = backend if backend in PygameCapture.get_backends() else CaptureBackend.ANY
    lst_devices = PygameCapture.get_cameras(backend=actual_backend)
    actual_device = vd_num if (vd_num < len(lst_devices) and vd_num >= 0) else 0
    return PygameCapture(actual_device,auto_exposure=auto_exposure,exposure_time=exposure_time,backend=actual_backend)

INTERFACES = {
        "OpenCV": __setup_cv2,
        "Pygame": __setup_pygame
    }

class CV2Capture(Capture):
    def __init__(self, device_id, auto_exposure=DEFAULT_SETTINGS[Settings.AUTO_EXPOSURE], exposure_time=DEFAULT_SETTINGS[Settings.EXPOSURE_TIME], backend = DEFAULT_SETTINGS[Settings.CAMERA_BACKEND], **kwargs) -> None:
        super().__init__(device_id, auto_exposure, exposure_time, **kwargs)
        self.__instance: cv2.VideoCapture|None = None
        self.__backend = backend if backend in self.get_backends() else CaptureBackend.ANY
        self.__cv2_backend = _backend_to_cv2(self.__backend)
    
    def open(self) -> None:
        try:
            self.__instance = cv2.VideoCapture(self._id,self.__cv2_backend)
            if not self._auto_exposure:
                self.__instance.set(cv2.CAP_PROP_AUTO_EXPOSURE,0)
                self.__instance.set(cv2.CAP_PROP_EXPOSURE,self._exposure_time)
        except:
            raise CaptureException("Could not initialise cv2.VideoCapture")
    
    def close(self) -> None:
        if self.__instance:
            self.__instance.release()

    def get_image(self) -> ndarray:
        is_capture = False
        if self.__instance:
            is_capture, img = self.__instance.read()
        if not is_capture:
            raise CaptureException("Image not retrieved from cv2.VideoCapture.read()")
        return img

    @classmethod
    def get_cameras(cls,**kwargs) -> list[str]|None:
        return None
    @classmethod
    def get_backends(cls) -> list[CaptureBackend]:
        universal_backends = [CaptureBackend.ANY,CaptureBackend.CV2_QT]
        sysname = platform.system()
        match sysname:
            case "Windows":
                return [*universal_backends,CaptureBackend.CV2_DSHOW,CaptureBackend.CV2_MSMF,CaptureBackend.CV2_VFW,CaptureBackend.CV2_WINRT]
            case "Linux":
                return [*universal_backends,CaptureBackend.CV2_V4L2]
            case _:
                return universal_backends
        
def _backend_to_cv2(be: CaptureBackend) -> int:
    match be:
        case CaptureBackend.ANY:
            return cv2.CAP_ANY
        case CaptureBackend.CV2_MSMF:
            return cv2.CAP_MSMF
        case CaptureBackend.CV2_V4L2:
            return cv2.CAP_V4L2
        case CaptureBackend.CV2_VFW:
            return cv2.CAP_VFW
        case CaptureBackend.CV2_WINRT:
            return cv2.CAP_WINRT
        case CaptureBackend.CV2_DSHOW:
            return cv2.CAP_DSHOW
        case CaptureBackend.CV2_QT:
            return cv2.CAP_QT
        case _:
            return CaptureBackend.ANY
        

class PygameCapture(Capture):

    __recent_camera_list = []
    __recent_backend = None

    def __init__(self, device_id, auto_exposure=DEFAULT_SETTINGS[Settings.AUTO_EXPOSURE], exposure_time=DEFAULT_SETTINGS[Settings.EXPOSURE_TIME], backend = DEFAULT_SETTINGS[Settings.CAMERA_BACKEND], **kwargs) -> None:
        super().__init__(device_id, auto_exposure, exposure_time, **kwargs)
        self.__backend = backend if backend in self.get_backends() else CaptureBackend.ANY
        self.__pygame_backend = _backend_to_pygame(backend)
        try:
            camera.quit()
            camera.init(self.__pygame_backend)
            if self.__pygame_backend == "OpenCV":
                self.__instance = camera.Camera(device_id,_backend_to_cv2(self.__backend))
            elif self.__pygame_backend == "_camera (msmf)":
                all_cameras = self.get_cameras(backend=self.__backend)
                device_name = all_cameras[device_id] if (device_id>=0 and device_id<len(all_cameras)) else all_cameras[0]
                self.__instance = camera.Camera(device_name)
            else:
                self.__instance = camera.Camera(device_id)
        except:
            raise CaptureException("Could not initialise pygame.camera.Camera()")

    @classmethod
    def get_backends(cls) -> list[CaptureBackend]:
        cv2_backends = CV2Capture.get_backends()
        sysname = platform.system()
        match sysname:
            case "Windows":
                return [*cv2_backends,CaptureBackend.PYGAME_WINDOWS_NATIVE,CaptureBackend.PYGAME_VIDEOCAPTURE]
            case "Linux":
                return [*cv2_backends,CaptureBackend.PYGAME_LINUX_NATIVE]
            case _:
                return cv2_backends

    @classmethod
    def get_cameras(cls,force_newlist = False,backend: CaptureBackend|None=None) -> list[str]:
        new_backend = _backend_to_pygame(backend)
        old_backend = _backend_to_pygame(cls.__recent_backend)
        same_backend = (new_backend is not None and old_backend is not None and new_backend == old_backend) or (new_backend is None and old_backend is None)
        
        if not same_backend:
            camera.quit()
            camera.init(backend=new_backend)
            recalculate = True
        elif force_newlist or cls.__recent_camera_list == []:
            recalculate = True
        else: 
            recalculate = False
        
        if recalculate:
            try:
                cls.__recent_camera_list =  list(map(str,camera.list_cameras()))
                cls.__recent_backend = backend
            except RuntimeError:
                camera.quit()
                camera.init(backend= new_backend)
                return cls.get_cameras(force_newlist=force_newlist)
        return cls.__recent_camera_list
    
    @classmethod
    def validate_device(cls,device: int|str,backend: CaptureBackend):
        if backend not in cls.get_backends():
            return False
        camera_list = cls.get_cameras(backend=backend)
        if isinstance(device,str):
            return device in camera_list
        if isinstance(device,int):
            return (device>=0 and device<len(camera_list))

    def open(self) -> None:
        try:
            self.__instance.start()
            time.sleep(0.5)
        except:
            raise CaptureException("Failed to start pygame camera")

    def close(self) -> None:
        self.__instance.stop()

    def get_image(self) -> ndarray:
        try:
            surf = self.__instance.get_image()
            img = PygameCapture.pygame_to_cv2(surf)
            return img
        except:
            raise CaptureException("Failed to take image")

    @staticmethod
    def pygame_to_cv2(surf: Surface) -> ndarray:
        img = array3d(surf)
        img = img.transpose([1, 0, 2])
        img = cv2.cvtColor(img,cv2.COLOR_RGB2BGR)
        return img

def _backend_to_pygame(be: CaptureBackend) -> str|None:
    if be == CaptureBackend.PYGAME_LINUX_NATIVE:
        return "_camera (v4l2)"
    elif be == CaptureBackend.PYGAME_WINDOWS_NATIVE:
        return "_camera (msmf)"
    elif be == CaptureBackend.PYGAME_VIDEOCAPTURE:
        return "videocapture"
    elif be in CV2_BACKENDS:
        return "OpenCV"
    # base case, or if CaptureBackend.ANY is passed
    return None

class CaptureException(BaseException):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)

@contextmanager
def open_video_device(cap: Capture,**kwargs):
    try:
        cap.open()
        yield cap
    finally:
        cap.close()

@contextmanager
def open_cv2_window(name: str):
    try:
        cv2.namedWindow(name)
        yield name
    finally:
        cv2.destroyWindow(name)

def capture(arg0: Capture|str) -> ndarray:
    if isinstance(arg0,str):
        img = cv2.imread(arg0)
        return img
    if isinstance(arg0,Capture):
        with open_video_device(arg0) as vc:
            img = vc.get_image()
        return img
    raise TypeError("Capture argument must be Capture or str")
