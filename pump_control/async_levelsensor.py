import os
from vision_model.level_filters import LevelFilter
from support_classes import Generator, GeneratorException, Settings, DEFAULT_SETTINGS, Capture, FileCapture, ImageFilterType
from support_classes.camera_interface import FileCapture
import cv2_gui.cv2_multiprocessing as cvmp
from .timeavg import TimeAvg
from typing import Any
import cv2
import asyncio
import time
from pathlib import Path
import numpy as np
import copy
from dataclasses import dataclass

#TODO change this to typing.Sequence[int] if error
Rect = tuple[int,int,int,int]

LevelReading = tuple[float,float,float,float]

@dataclass
class LevelOutput:
    levels: LevelReading|None
    original_image: np.ndarray
    filtered_image: np.ndarray

class LevelSensor(Generator[LevelOutput]):


    def __init__(self, 
                 sensed_event = asyncio.Event(), 
                 capture_device: Capture|None = None,
                 sense_period: float = DEFAULT_SETTINGS[Settings.SENSING_PERIOD],
                 average_window_length: float = DEFAULT_SETTINGS[Settings.AVERAGE_WINDOW_WIDTH],
                 stabilisation_period: float = DEFAULT_SETTINGS[Settings.LEVEL_STABILISATION_PERIOD],
                 image_filter_type: ImageFilterType = DEFAULT_SETTINGS[Settings.IMAGE_FILTER],
                 **kwargs) -> None:
        
        super().__init__()
        
        # shared states:
        # threading shared state: image that is updated with every new capture
        # self.__display_state: SharedState[np.ndarray|None] = SharedState(initialValue=None)
        # self.__display_flag = mp.Event()
        # self.__display_thread = mp.Process(target=_continuous_display,args=(self.__display_state,self.__display_flag))

        self.__cv2_process = cvmp.ViewerProcess(window_name="Level Visualisation")

        # video parameters to be set at a later time before generation
        self._vc: Capture|None = capture_device


        # computer vision parameters
        self.__stabilisation_period = stabilisation_period
        self.__average_window_length = average_window_length
        self.__sense_period = sense_period

        self.__indexAn: tuple[slice|slice]|None = None
        self.__indexCath: tuple[slice|slice]|None = None
        self.__scale: float|None = None

        # initial volume is calculated after a certain number of iterations
        self.__vol_init: float|None = None

        # public exposed property: signals that a level reading has been made
        # when set, it indicates that a reading has been made that has not been 
        self.sensed_event = sensed_event

        self.__readings_buffer = TimeAvg(self.__average_window_length,data_size=4)
        self._filter = LevelFilter.from_filter_type(image_filter_type)

        # loop counter: used in calculation for offset period
        self.__i: int = 0

    def set_parameters(self,new_parameters: dict[Settings,Any],capture_device: Capture|None = None):
        if capture_device is not None:
            self.stop()
            self._vc = capture_device
        if Settings.SENSING_PERIOD in new_parameters.keys():
            self.__sense_period = new_parameters[Settings.SENSING_PERIOD]
        if Settings.AVERAGE_WINDOW_WIDTH in new_parameters.keys():
            self.__average_window_length = new_parameters[Settings.AVERAGE_WINDOW_WIDTH]
            old_buffer = self.__readings_buffer
            self.__readings_buffer = TimeAvg.from_old(old_buffer,self.__average_window_length)
        if Settings.LEVEL_STABILISATION_PERIOD in new_parameters.keys():
            self.__stabilisation_period = new_parameters[Settings.LEVEL_STABILISATION_PERIOD]
        if Settings.IMAGE_FILTER in new_parameters.keys():
            self._filter = LevelFilter.from_filter_type(new_parameters[Settings.IMAGE_FILTER])

    def set_vision_parameters(self, rect1: Rect, rect2: Rect, height_ref: Rect, vol_ref: float):
        if any((rect1 is None, rect2 is None, height_ref is None, vol_ref is None)):
            raise GeneratorException("Null values supplied to level sensor parameters")
        self.__indexAn = _get_indices(rect1)
        self.__indexCath = _get_indices(rect2)
        self.__scale = vol_ref/abs(height_ref)
        self._vc = Capture.from_settings()

    def is_ready(self) -> bool:
        return all((self.__indexAn is not None, self.__indexCath is not None, self.__scale is not None))

    async def _setup(self):
        if any((self._vc is None, self.__indexAn is None, self.__indexCath is None, self.__scale is None)):
            raise GeneratorException("Null values supplied to level sensor parameters")

        self._vc.open()
        self.__i = 0
        self.__vol_init = None
        self.__readings_buffer = TimeAvg(self.__average_window_length,data_size=4)
        self._filter.setup()
        # set an initial sleep time. this is recalculated at each iteration of the loop
        self.__sleep_time = 0.5
        # self.__cv2_process.start()

    async def _loop(self) -> tuple[LevelReading|None,np.ndarray]|None:

        # wait until next reading is due
        await asyncio.sleep(self.__sleep_time)

        # begin performance benchmarking
        start_time = time.perf_counter()

        #-----------CAPTURE-------------
        # take the frame and record its time
        frame = self._vc.get_image()
        t = time.time()

        #---------COMPUTER-VISION---------
        # perform CV
        frame_an = copy.copy(frame[self.__indexAn[0],self.__indexAn[1],:])
        frame_an, vol_an = self._filter.filter(frame_an,self.__scale)
        # _draw_level(frame_an,vol_an/self.__scale)

        frame_cath = copy.copy(frame[self.__indexCath[0],self.__indexCath[1],:])
        frame_cath, vol_cath = self._filter.filter(frame_cath,self.__scale)
        # _draw_level(frame_cath,vol_cath/self.__scale)

        if self.__i*self.__sense_period < self.__stabilisation_period or self.__vol_init is None:
            net_vol_change = 0
        else:
            net_vol_change = vol_an + vol_cath - self.__vol_init
        vol_diff = vol_an - vol_cath

        raw_data = [vol_an,vol_cath,vol_diff,net_vol_change]
        self.__readings_buffer.append(raw_data,t)
        averaged_data = self.__readings_buffer.calculate()

        avg_an = averaged_data[0]
        avg_cath = averaged_data[1]
        avg_diff = averaged_data[2]
        avg_change = averaged_data[3]

        # set the initial volume to the current volume while still in stabilisation period
        if self.__i*self.__sense_period < self.__stabilisation_period:
            self.__vol_init = avg_an + avg_cath

        #---------------DISPLAY-------------------
        unaltered_frame = copy.copy(frame)

        # place the filtered images onto the original image
        frame[self.__indexAn[0],self.__indexAn[1],:] = frame_an
        frame[self.__indexCath[0],self.__indexCath[1],:] = frame_cath

        # send to display thread
        # self.__cv2_process.input.set_value(frame)

        #--------------UPDATE---------------
        # update the logging state
        # reading is now finished, increment reading counter and record performance time
        end_time = time.perf_counter()
        perftime = (end_time-start_time)/1000 # time in seconds for computer vision
        self.__i += 1
        self.__sleep_time = max(self.__sense_period - perftime,0)

        # save reading
        # if (not isnan(reading_calculation_an)) and (not isnan(reading_calculation_cath)):
        data = [avg_an, avg_cath, avg_diff,avg_change]

        # save the data to exposed state
        new_state = LevelOutput(data,unaltered_frame,frame)
        self.state.set_value(new_state)
        # additional asyncio event set for pid await line
        self.sensed_event.set()
        return None

    def teardown(self):
        if self._vc is not None:
            self._vc.close()
        # self.__cv2_process.exit_flag.set()
        # self.__cv2_process.join()
        cv2.destroyAllWindows()

def _get_indices(r: Rect):
    return  (slice(r[1],r[1]+r[3]), slice(r[0],r[0]+r[2]))

class DummySensor(LevelSensor):

    def __init__(self, imgpath: Path|str, sensed_event=asyncio.Event(), capture_device: Capture | None = None, sense_period: float = DEFAULT_SETTINGS[Settings.SENSING_PERIOD], average_window_length: float = DEFAULT_SETTINGS[Settings.AVERAGE_WINDOW_WIDTH], stabilisation_period: float = DEFAULT_SETTINGS[Settings.LEVEL_STABILISATION_PERIOD], image_filter_type: ImageFilterType = DEFAULT_SETTINGS[Settings.IMAGE_FILTER], ignore_level = True, **kwargs) -> None:
        super().__init__(sensed_event, capture_device, sense_period, average_window_length, stabilisation_period, image_filter_type, **kwargs)
        if isinstance(imgpath,str):
            imgpath = Path(imgpath)
        if not imgpath.is_absolute():
            imgpath = imgpath.absolute()
        self.img_names = [imgpath/fname for fname in os.listdir(imgpath)]
        self.ignore_level = ignore_level
        self._vc = FileCapture((Path(__file__)/"Images").absolute(),".png")
        self._filter

    def set_parameters(self, new_parameters: dict[Settings, Any], capture_device: Capture | None = None):
        capture_device = self._vc
        super().set_parameters(new_parameters, capture_device)
        self._filter.ignore_level = self.ignore_level
