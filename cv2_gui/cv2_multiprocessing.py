from enum import Enum
from typing import Any
import multiprocessing as mp
from support_classes import SharedState, Capture, CaptureException, capture, ImageFilterType, Settings
from vision_model.level_filters import LevelFilter
from .mouse_events import EscException, MouseInput
import cv2
from contextlib import contextmanager
import numpy as np
import threading


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

def withwindow(fun,name="Window"):
    def inner(*args,**kwargs):
        with open_cv2_window(name):
            return fun(*args,**kwargs)
    return inner
        

class InputProcess(mp.Process):

    class ErrorCode(Enum):
        NONE = 0
        INCORRECT_SELECTION = 1
        CAPTURE_ERROR = 2
        OVER_EDGE_SELECTION = 3

    def __init__(self, filter_type: ImageFilterType, capture_params: dict[Settings,Any], window_name: str = "Window"):
        super().__init__()
        self.window = window_name
        self.output_data = mp.Array("i",[-1]*9,lock=True)
        self.error_data = mp.Value("i",0,lock=True)
        self.filter_type = filter_type
        self.capture_params = capture_params
        self.exit_flag = mp.Event()

    def get_error(self):
        with self.error_data.get_lock():
            return self.ErrorCode(self.error_data.value)
    def get_output(self):
        with self.output_data.get_lock():
            return self.output_data

    def run(self):
        self.exit_flag.clear()
        with open_cv2_window(self.window):
            capture_device = Capture.from_settings(params=self.capture_params)
            try:
                img = capture(capture_device)
            except CaptureException:
                self.exit_flag.set()
                with self.error_data.get_lock():
                    self.error_data.value = self.ErrorCode.CAPTURE_ERROR.value
            if self.exit_flag.is_set():
                return
            img = cv2.cvtColor(img,cv2.COLOR_RGB2BGR)
            input_list = LevelFilter.from_filter_type(self.filter_type).selection_process()
            # register the exit condition to the inputs
            for inp in input_list:
                inp.break_event = self.exit_flag
            try:
                outputs = MouseInput.chain_inputs(self.window,img,input_list,ignore_backwards=True)
                if outside_image(img,outputs[0]) or outside_image(img,outputs[1]):
                    self.error_data.value = self.ErrorCode.OVER_EDGE_SELECTION.value
                    self.exit_flag.set()
                    return
                outputs = [*outputs[0],*outputs[1],outputs[2]]
                outputs = list(map(int,outputs))
                with self.output_data.get_lock():
                    for i,val in enumerate(outputs):
                        self.output_data[i] = val
                if any([val<0 for val in outputs]):
                    with self.error_data.get_lock():
                        self.error_data.value = self.ErrorCode.INCORRECT_SELECTION.value
            except EscException:
                with self.error_data.get_lock():
                    self.error_data.value = self.ErrorCode.INCORRECT_SELECTION.value
            finally:
                self.exit_flag.set()
                return
        
class InputException(Exception):
    pass


def outside_image(img: np.ndarray, bbox: tuple[int,int,int,int]):
    shp = img.shape[:-1]
    if bbox[0]+bbox[2]>shp[1]:
        return True
    elif bbox[1]+bbox[3]>shp[0]:
        return True
    return False

            
class ViewerProcess(threading.Thread):
    WAITKEY_TIME = 50
    def __init__(self, window_name: str = "Window"):
        super().__init__()
        self.window = window_name
        self.exit_flag = threading.Event()
        self.input = SharedState[np.ndarray]()
        self.error = SharedState[BaseException]()
    def run(self):
        self.exit_flag.clear()
        with open_cv2_window(self.window):
            try:
                while not self.exit_flag.is_set():
                    next_img = self.input.get_value()
                    if next_img is not None:
                        next_img = cv2.cvtColor(next_img,cv2.COLOR_RGB2BGR)
                        cv2.imshow(self.window,next_img)
                    cv2.waitKey(self.WAITKEY_TIME)
            finally:
                self.exit_flag.set()
                return
