from abc import ABC, abstractmethod
from typing import Iterable
import numpy as np
import cv2
from support_classes import ImageFilterType
from cv2_gui.mouse_events import MouseInput, BoxDrawer, ROISelector, HeightSelector

def _notify_setup(func):

    def wrapper(self: LevelFilter,*args,**kwargs):
        if not hasattr(self,"setup"):
            self._setup_completed = False
        result = func(self,*args,**kwargs)
        if hasattr(self,"setup"):
            self._setup_completed = True
        return result
    return wrapper

def _maybe_call_filter(func):
    def wrapper(self: LevelFilter,*args,**kwargs):
        already_setup = getattr(self,"_setup_completed")
        if not already_setup and hasattr(self,"setup"):
            self.setup()
        return func(self,*args,**kwargs)
    return wrapper

class LevelFilter(ABC):

    filter_size: tuple[int,int]|None = None

    def __init__(self,ignore_level=False) -> None:
        super().__init__()
        self.ignore_level = ignore_level
        self._setup_completed = False

    def __init_subclass__(cls,**kwargs) -> None:
        super().__init_subclass__(**kwargs)
        # register setup call logging
        if "setup" in cls.__dict__:
            cls.setup = _notify_setup(cls.setup)
        # register callback to call setup before filtering if not done already
        if "filter" in cls.__dict__:
            cls.filter = _maybe_call_filter(cls.filter)
    
    def __call__(self,img: np.ndarray, scale: float) -> tuple[np.ndarray,float]:
        return self.filter(img,scale)

    @abstractmethod
    def setup(self) -> None:
        """
        Performs any long initialisation of the level filter that might be required before filtering can take place, such as importing large libraries or loading models
        """
        raise NotImplementedError("LevelFilter must implement setup()")
    @abstractmethod
    def filter(self,img: np.ndarray,scale:float) -> tuple[np.ndarray,float]:
        """
        ## Parameters:
        - img: ndarray - the image to be filtered
        - scale: float - scaling factor to convert from pixels to volume (mL of volume per height in pixels)
        ## Returns:
        A tuple of length 2, containing:
        1. ndarray of filtered image. This could be the image overlayed with a mask or bounding box for example
        1. float corresponding to the volume in mL of the fluid detected
        """
        raise NotImplementedError("LevelFilter must implement filter(np.ndarray)")
    @classmethod
    def selection_process(cls) -> Iterable[MouseInput]:
        if cls.filter_size is None:
            return LevelFilter._roi_selection_process()
        return LevelFilter._box_selection_process(*cls.filter_size)
    @staticmethod
    def _box_selection_process(box_width,box_height) -> Iterable[MouseInput]:
        roi1 = BoxDrawer(box_width,box_height,auto_progress=True,color=(0,0,255))
        roi1.text = "Select anolyte tank. Right-click to cancel"
        roi2 = BoxDrawer(box_width,box_height,auto_progress=True,color=(0,0,255))
        roi2.text = "Select catholyte tank. Right-click to cancel"
        height = HeightSelector(line_color=(0,255,0))
        height.text = "Select a height corresponding to a known volume"
        return [roi1,roi2,height]
    @staticmethod
    def _roi_selection_process() -> Iterable[MouseInput]:
        roi1 = ROISelector(auto_progress=True,color=(0,0,255))
        roi1.text = "Select anolyte tank. Right-click to cancel"
        roi2 = ROISelector(auto_progress=True,color=(0,0,255))
        roi2.text = "Select catholyte tank. Right-click to cancel"
        height = HeightSelector(line_color=(0,255,0))
        height.text = "Select a height corresponding to a known volume"
        return [roi1,roi2,height]

    def teardown(self):
        pass
    @staticmethod
    def from_filter_type(ftype: ImageFilterType,ignore_level=False) -> "LevelFilter":
        match ftype:
            case ImageFilterType.OTSU:
                from .filters.otsu_filter import OtsuFilter
                return OtsuFilter(ignore_level=ignore_level)
            case ImageFilterType.LINKNET:
                from .filters.torch_filters import LinkNetFilter
                return LinkNetFilter(ignore_level=ignore_level)
            case ImageFilterType.NONE:
                return NoFilter(ignore_level=ignore_level)
            case _:
                raise NotImplementedError("Unknown filter type: "+str(ftype))
    @classmethod    
    def _place_mask_on_image(cls,img: np.ndarray, mask: np.ndarray,color=(1,0,0), alpha = 0.25):
        assert len(img.shape) == 3 and img.shape[2] == 3
        if len(mask.shape) == 2:
            mask = mask[:,:,np.newaxis]
        if mask.shape[2] == 1:
            mask = np.repeat(mask,3,axis=2)
        assert len(mask.shape) == 3 and mask.shape == img.shape
        idx = mask>0
        blend = np.zeros_like(mask)
        blend[:] = np.array(color)
        mask[idx] = blend[idx]
        img[idx] = alpha*mask[idx] + (1-alpha)*img[idx]
        return img
    
    @classmethod
    def _place_bbox_on_image(cls,img: np.ndarray, bbox: tuple[int,int,int,int]):
        return cv2.rectangle(img,bbox,(0,1,0),thickness=1)


class NoFilter(LevelFilter):
    """
    Trivial level filter that does no filtering - always returns the same image and reads 0mL
    """
    def __init__(self, ignore_level=False) -> None:
        super().__init__(ignore_level)
    def setup(self):
        pass
    def filter(self,img: np.ndarray):
        return 0.0,img
    @classmethod
    def selection_process(cls) -> Iterable[MouseInput]:
        return []

        





