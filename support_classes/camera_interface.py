from contextlib import contextmanager
from pathlib import Path
import random
from numpy import ndarray
from .settings_interface import DEFAULT_SETTINGS, Settings, read_setting, read_settings,CaptureBackend,CAMERA_SETTINGS, CV2_BACKENDS
import cv2
import os,sys
# hides the "Hello from pygame" prompt in console
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
from pygame.surface import Surface
from pygame.surfarray import array3d
import pygame.camera as camera
from pygame import _camera_opencv
import pygame as pg
from abc import ABC, abstractmethod
from typing import Any, Callable
import platform
import time
from PIL import Image
import numpy as np

def _setup_cv2(vd_num: int,auto_exposure: bool,exposure_time: int, backend: str,scale_factor: float) -> "Capture":
    actual_backend = backend if backend in CV2Capture.get_backends() else CaptureBackend.ANY
    return CV2Capture(vd_num if vd_num >= 0 else 0,auto_exposure=auto_exposure,exposure_time=exposure_time,backend=actual_backend,scale_factor = scale_factor)
def _setup_pygame(vd_num: int,auto_exposure: bool,exposure_time: int, backend: str,scale_factor: float) -> "Capture":
    actual_backend = backend if backend in PygameCapture.get_backends() else CaptureBackend.ANY
    # lst_devices = PygameCapture.get_cameras(backend=actual_backend)
    # actual_device = vd_num if (vd_num < len(lst_devices) and vd_num >= 0) else 0
    actual_device = vd_num if vd_num > 0 else 0
    return PygameCapture(actual_device,auto_exposure=auto_exposure,exposure_time=exposure_time,backend=actual_backend,scale_factor = scale_factor)
def _setup_file(vd_num: int, auto_exposure: bool, exposure_time: int, backend: str, scale_factor: float) -> "Capture":
    default_directory = read_setting(Settings.FILECAPTURE_DIRECTORY)
    return FileCapture(default_directory,".png")

class Capture(ABC):

    __INTERFACES = {
        "OpenCV": _setup_cv2,
        "Pygame": _setup_pygame,
        "File": _setup_file,
    }

    @staticmethod
    def supported_interfaces(debug=False):
        return list(Capture.__INTERFACES.keys())

    @staticmethod
    def from_settings(params: dict[Settings,Any]|None = None):
        if params is None:
            params = read_settings(*CAMERA_SETTINGS)
        interface = params[Settings.CAMERA_INTERFACE_MODULE]
        if interface in Capture.__INTERFACES.keys():
            capfun = Capture.__INTERFACES[interface]
        else:
            capfun = list(Capture.__INTERFACES.values())[0]
        cap = capfun(params[Settings.VIDEO_DEVICE],params[Settings.AUTO_EXPOSURE],params[Settings.EXPOSURE_TIME],params[Settings.CAMERA_BACKEND],params[Settings.IMAGE_RESCALE_FACTOR])
        return cap

    def __init__(self,device_id: int, 
                 auto_exposure: bool = DEFAULT_SETTINGS[Settings.AUTO_EXPOSURE], 
                 exposure_time: int = DEFAULT_SETTINGS[Settings.EXPOSURE_TIME],
                 backend: CaptureBackend = DEFAULT_SETTINGS[Settings.CAMERA_BACKEND],
                 scale_factor: int = DEFAULT_SETTINGS[Settings.IMAGE_RESCALE_FACTOR],
                 **kwargs) -> None:
        self._id = device_id
        self._auto_exposure = auto_exposure
        self._exposure_time = exposure_time
        if scale_factor>0:
            self._scale_factor = scale_factor
        else:
            self._scale_factor = DEFAULT_SETTINGS[Settings.IMAGE_RESCALE_FACTOR]

    @abstractmethod
    def get_image(self,rescale: bool = True) -> ndarray:
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

class FileCapture(Capture):
    def __init__(self, directory: Path, extension: str, auto_exposure: bool = DEFAULT_SETTINGS[Settings.AUTO_EXPOSURE], exposure_time: int = DEFAULT_SETTINGS[Settings.EXPOSURE_TIME], backend: CaptureBackend = DEFAULT_SETTINGS[Settings.CAMERA_BACKEND], scale_factor: int = DEFAULT_SETTINGS[Settings.IMAGE_RESCALE_FACTOR], **kwargs) -> None:
        super().__init__(0, auto_exposure, exposure_time, backend, scale_factor, **kwargs)
        self.directory = directory
        self.extension = extension
        self.image_names = []
        self._i = 0
    def open(self):
        self._i = 0
        if not os.path.isdir(self.directory):
            raise CaptureException("File capture directory does not exist")
        imnames = [self.directory/fname for fname in os.listdir(self.directory) if len(fname)>len(self.extension) and fname[-len(self.extension):]==self.extension]
        if len(imnames)<1:
            raise CaptureException(f"File capture directory does not contain any {self.extension} files")
        # Choose a random index in the list
        start_index = random.randint(0, len(imnames) - 1)
        # Generate the cyclic permutation
        self.image_names = imnames[start_index:] + imnames[:start_index]
    
    def get_image(self, rescale: bool = True) -> ndarray:
        img = np.array(Image.open(self.image_names[self._i]))
        if self._i+1>=len(self.image_names):
            self._i=0
        else:
            self._i += 1
        return img
    def close(self):
        pass
    def get_cameras(self):
        return None
    def get_backends(self):
        return []

SetupFunction = Callable[[int,bool,int,str],Capture]

class CV2Capture(Capture):
    def __init__(self, device_id, auto_exposure=DEFAULT_SETTINGS[Settings.AUTO_EXPOSURE], exposure_time=DEFAULT_SETTINGS[Settings.EXPOSURE_TIME], backend = DEFAULT_SETTINGS[Settings.CAMERA_BACKEND], scale_factor = 1, **kwargs) -> None:
        super().__init__(device_id, auto_exposure, exposure_time, scale_factor = scale_factor, **kwargs)
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

    def get_image(self,rescale=True) -> ndarray:
        is_capture = False
        if self.__instance:
            is_capture, img = self.__instance.read()
            if not is_capture:
                raise CaptureException("Image not retrieved from cv2.VideoCapture.read()")
            if rescale:
                imshape = img.shape
                img = cv2.resize(img,(int(imshape[1]*self._scale_factor),int(imshape[0]*self._scale_factor)))
            img = cv2.cvtColor(img,cv2.COLOR_BGR2RGB)
            return img
        raise CaptureException("Camera has not been opened")

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
            cv2.CAP_ANY

class PygameCapture(Capture):

    __recent_camera_list = []
    __recent_backend = None

    def __init__(self, device_id, auto_exposure=DEFAULT_SETTINGS[Settings.AUTO_EXPOSURE], exposure_time=DEFAULT_SETTINGS[Settings.EXPOSURE_TIME], backend = DEFAULT_SETTINGS[Settings.CAMERA_BACKEND], scale_factor = 1, **kwargs) -> None:
        super().__init__(device_id, auto_exposure, exposure_time, scale_factor=scale_factor, **kwargs)
        self.__backend = backend if backend in self.get_backends() else CaptureBackend.ANY
        self.__pygame_backend = _backend_to_pygame(backend)
        try:
            camera.quit()
            with suppress_stderr():
                camera.init(self.__pygame_backend)
            if self.__pygame_backend == "OpenCV":
                self.__instance = PygameCV2Camera(device=device_id,api_preference=_backend_to_cv2(self.__backend))
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
                cv2_backends.remove(CaptureBackend.ANY)
                return [CaptureBackend.ANY,CaptureBackend.PYGAME_WINDOWS_NATIVE,CaptureBackend.PYGAME_VIDEOCAPTURE,*cv2_backends]
            case "Linux":
                cv2_backends.remove(CaptureBackend.ANY)
                return [CaptureBackend.ANY,CaptureBackend.PYGAME_LINUX_NATIVE,*cv2_backends]
            case _: # mac, other
                return cv2_backends

    @classmethod
    def get_cameras(cls,force_newlist = False,backend: CaptureBackend|None=None) -> list[str]:
        new_backend = _backend_to_pygame(backend)
        old_backend = _backend_to_pygame(cls.__recent_backend)
        same_backend = (new_backend is not None and old_backend is not None and new_backend == old_backend) or (new_backend is None and old_backend is None)
        
        if not same_backend:
            camera.quit()
            with suppress_stderr():
                camera.init(backend=new_backend)
            recalculate = True
        elif force_newlist or cls.__recent_camera_list == []:
            recalculate = True
        else: 
            recalculate = False
        
        if recalculate:
            try:
                with suppress_stdout():
                    cls.__recent_camera_list =  list(map(str,camera.list_cameras()))
                cls.__recent_backend = backend
            except RuntimeError:
                camera.quit()
                with suppress_stderr():
                    camera.init(backend= new_backend)
                return cls.get_cameras(force_newlist=force_newlist)
        return cls.__recent_camera_list
    
    @classmethod
    def will_block(cls,backend: CaptureBackend) -> bool:
        # get whether a call to get_cameras will result in a lengthy, blocking call
        new_backend = _backend_to_pygame(backend)
        #TODO check the logic for this (at the very least the types are not matching)
        return not (new_backend and cls.__recent_backend and new_backend == cls.__recent_backend and new_backend != "OpenCV") or (new_backend is None and cls.__recent_backend is None and len(cls.__recent_camera_list)>0)

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
            while not self.__instance.query_image():
                time.sleep(0.5)
            time.sleep(0.5)
        except:
            raise CaptureException("Failed to start pygame camera")

    def close(self) -> None:
        self.__instance.stop()

    def get_image(self,rescale: bool = True) -> ndarray:
        try:
            surf = self.__instance.get_image()
            img = PygameCapture.pygame_to_cv2(surf)
            if rescale:
                imshape = img.shape
                img = cv2.resize(img,(int(imshape[1]*self._scale_factor),int(imshape[0]*self._scale_factor)))
            return img
        except (RuntimeError,pg.error):
            raise CaptureException("Failed to take image")
        except Exception as e:
            raise e
        

    @staticmethod
    def pygame_to_cv2(surf: Surface) -> ndarray:
        img = array3d(surf)
        img = img.transpose([1, 0, 2])
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
    elif be == CaptureBackend.ANY:
        # return camera.get_backends()[0]
        match platform.system():
            case "Windows":
                return "_camera (msmf)"
            case "Linux":
                return "_camera (v412)"
            case _:
                return camera.get_backends()[0]
    # base case
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
        try:
            cv2.destroyWindow(name)
        except:
            pass

def capture(arg0: Capture|str|Path,rescale = True) -> ndarray:
    if isinstance(arg0,str):
        arg0 = Path(arg0)
    
    if isinstance(arg0,Path):
        if not arg0.is_absolute():
            arg0 = arg0.absolute()
        arg0 = FileCapture(arg0,".png")

    if not isinstance(arg0,Capture):
        raise TypeError("capture argument must be of type Capture, Path, or str")

    with open_video_device(arg0) as vc:
        img = vc.get_image(rescale=rescale)
    return img
    

# solutions from Dave Smith's blog: suppresses the warnings from pygame and opencv
# https://thesmithfam.org/blog/2012/10/25/temporarily-suppress-console-output-in-python/
@contextmanager
def suppress_stdout():
    with open(os.devnull, "w") as devnull:
        old_stdout = sys.stdout
        sys.stdout = devnull
        try:  
            yield
        finally:
            sys.stdout = old_stdout
@contextmanager
def suppress_stderr():
    with open(os.devnull, "w") as devnull:
        old_stderr = sys.stderr
        sys.stderr = devnull
        try:  
            yield
        finally:
            sys.stderr = old_stderr


# Pygame has a bug where sys is not imported for whatever reason. This class will override the faulty constructor:
class PygameCV2Camera(_camera_opencv.Camera):

    def __init__(self, device=0, size=(640, 480), mode="RGB", api_preference=None):

        self._device_index = device
        self._size = size

        self.api_preference = api_preference

        if mode == "RGB":
            self._fmt = cv2.COLOR_BGR2RGB
        elif mode == "YUV":
            self._fmt = cv2.COLOR_BGR2YUV
        elif mode == "HSV":
            self._fmt = cv2.COLOR_BGR2HSV
        else:
            raise ValueError("Not a supported mode")

        self._open = False