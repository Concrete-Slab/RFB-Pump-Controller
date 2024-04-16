from abc import ABC, abstractmethod
from typing import Iterable
import numpy as np
import cv2
from support_classes import ImageFilterType, Teardown
from cv2_gui.mouse_events import MouseInput, BoxDrawer, ROISelector, HeightSelector

class LevelFilter(Teardown,ABC):

    filter_size: tuple[int,int]|None = None

    def __init__(self,ignore_level=False) -> None:
        super().__init__()
        self.ignore_level = ignore_level
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
    
    # https://stackoverflow.com/questions/63923800/drawing-bounding-rectangles-around-multiple-objects-in-binary-image-in-python
    @classmethod
    def _reduce_mask(cls,mask: np.ndarray, kernel_size=(10,10)):
        # morph close to remove smaller blobs more efficiently
        kernel = np.ones(kernel_size)
        thresh = cv2.morphologyEx(mask,cv2.MORPH_CLOSE,kernel)
        
        contours = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours = contours[0] if len(contours) == 2 else contours[1]
        rects = [(0,0,0,0)]*len(contours)
        areas = [0.0]*len(contours)
        for i,cntr in enumerate(contours):
            rect = cv2.boundingRect(cntr)
            rect_area = rect[2]*rect[3]
            rects[i] = rect
            areas[i] = rect_area
        
        mask_out = np.zeros_like(thresh)
        if len(areas)<1:
            return mask_out
        index = areas.index(max(areas))
        bbox = rects[index]
        row_slice = slice(bbox[1],bbox[1]+bbox[3])
        col_slice = slice(bbox[0],bbox[0]+bbox[2])
        mask_out[row_slice,col_slice] = thresh[row_slice,col_slice]
        return mask_out


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

        





