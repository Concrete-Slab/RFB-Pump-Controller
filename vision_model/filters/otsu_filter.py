from vision_model.level_filters import LevelFilter
import numpy as np
import copy
import cv2

class OtsuFilter(LevelFilter):
    def __init__(self, ignore_level=False) -> None:
        super().__init__(ignore_level)
    def setup(self):
        pass
    def filter(self, img: np.ndarray, scale: float) -> tuple[np.ndarray, float]:
        imgout = copy.copy(img)
        mask: np.ndarray = cv2.cvtColor(copy.copy(img),cv2.COLOR_BGR2GRAY)
        frm_height, frm_width = np.shape(mask)
        kernel = np.ones((31,int(3*frm_width/4)))
        _, mask = cv2.threshold(mask,0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        # frame = cv2.adaptiveThreshold(frame,255,cv2.ADAPTIVE_THRESH_MEAN_C,cv2.THRESH_BINARY,thresh_window_size,-10)
        mask = cv2.morphologyEx(mask,cv2.MORPH_CLOSE,kernel,borderType=cv2.BORDER_REPLICATE)
        mask = np.array(cv2.GaussianBlur(mask,(15,15),sigmaX=5,sigmaY=0.1))
        num_zero = np.zeros(frm_width)
        for i,pixel_column in enumerate(mask.T):
            num_zero[i] = np.size(pixel_column)-cv2.countNonZero(pixel_column)
        npixels = float(np.median(num_zero))
        mask = cv2.cvtColor(mask,cv2.COLOR_GRAY2BGR)
        bbox = (0,frm_height-npixels,frm_width,npixels)

        imgout = self._place_mask_on_image(imgout,mask)
        imgout = self._place_bbox_on_image(imgout,bbox)
        return imgout,scale*npixels