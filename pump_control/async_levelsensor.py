import math
from support_classes import Generator, SharedState, GeneratorException, Loggable, Settings, DEFAULT_SETTINGS, Capture, CaptureException
from .timeavg import TimeAvg
from typing import Any, Callable
import cv2
import datetime
import asyncio
import time
from math import isnan
from pathlib import Path
import numpy as np
import copy
import threading


#TODO change this to typing.Sequence[int] if error
Rect = tuple[int,int,int,int]

LevelReading = tuple[float,float,float,float,float]

class LevelSensor(Generator[tuple[LevelReading,np.ndarray|None]],Loggable):

    LOG_COLUMN_HEADERS = ["Timestamp","Elapsed Time","Anolyte Level Avg", "Catholyte Avg","Avg Difference","Total Change in Electrolyte Level"]

    def __init__(self, 
                 sensed_event = asyncio.Event(), 
                 logging_state: SharedState[bool] = SharedState(False), 
                 capture_device: Capture|None = None,
                 absolute_logging_path: Path = DEFAULT_SETTINGS[Settings.LEVEL_DIRECTORY],
                 sense_period: float = DEFAULT_SETTINGS[Settings.SENSING_PERIOD],
                 average_window_length: float = DEFAULT_SETTINGS[Settings.AVERAGE_WINDOW_WIDTH],
                 stabilisation_period: float = DEFAULT_SETTINGS[Settings.LEVEL_STABILISATION_PERIOD],
                 **kwargs) -> None:
        
        super().__init__(directory = absolute_logging_path,default_headers = LevelSensor.LOG_COLUMN_HEADERS)
        
        # shared states:
        # logging shared state: boolean that determines if data is saved
        self.__logging_state = logging_state
        # threading shared state: image that is updated with every new capture
        self.__display_state: SharedState[np.ndarray|None] = SharedState(initialValue=None)
        self.__display_flag = threading.Event()
        self.__display_thread = threading.Thread(target=_continuous_display,args=(self.__display_state,self.__display_flag))

        # video parameters to be set at a later time before generation
        self.__vc: Capture|None = capture_device

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

        # external buffer for averaging level readings
        # self.__buffer = LevelBuffer(buffer_size)
        # secretly set the buffer to the correct size without notifying of the change
        # self.state.value = (self.__buffer, None)

        # internal buffer for averaging level readings
        # self.__reading_an = TimeAvg(self.__average_window_length)
        # self.__reading_cath = TimeAvg(self.__average_window_length)

        self.__readings_buffer = TimeAvg(self.__average_window_length,data_size=4)

        # loop counter: used in calculation for offset period
        self.__i: int = 0

    def set_parameters(self,new_parameters: dict[Settings,Any],capture_device: Capture|None = None):
        if capture_device is not None:
            if self.__vc:
                self.__vc.close()
            self.__vc = capture_device
        if Settings.SENSING_PERIOD in new_parameters.keys():
            self.__sense_period = new_parameters[Settings.SENSING_PERIOD]
        if Settings.AVERAGE_WINDOW_WIDTH in new_parameters.keys():
            self.__average_window_length = new_parameters[Settings.AVERAGE_WINDOW_WIDTH]
            old_buffer = self.__readings_buffer
            self.__readings_buffer = TimeAvg.from_old(old_buffer,self.__average_window_length)
        if Settings.LEVEL_STABILISATION_PERIOD in new_parameters.keys():
            self.__stabilisation_period = new_parameters[Settings.LEVEL_STABILISATION_PERIOD]

    def set_vision_parameters(self, rect1: Rect, rect2: Rect, rect_ref: Rect, vol_ref: float):
        if any((rect1 is None, rect2 is None, rect_ref is None, vol_ref is None)):
            raise GeneratorException("Null values supplied to level sensor parameters")
        self.__indexAn = _get_indices(rect1)
        self.__indexCath = _get_indices(rect2)
        self.__scale = vol_ref/abs(rect_ref[3])
        self.__vc = Capture.from_settings()
        pass

    def is_ready(self) -> bool:
        return all((self.__indexAn is not None, self.__indexCath is not None, self.__scale is not None))

    async def _setup(self):
        if any((self.__vc is None, self.__indexAn is None, self.__indexCath is None, self.__scale is None)):
            raise GeneratorException("Null values supplied to level sensor parameters")
        self.new_file()
        self.__vc.open()
        self.__i = 0
        self.__initial_timestamp = time.time()
        self.__vol_init = None
        self.__readings_buffer = TimeAvg(self.__average_window_length,data_size=4)
        # set an initial sleep time. this is recalculated at each iteration of the loop
        self.__sleep_time = 0.5
        self.__display_thread = threading.Thread(target=_continuous_display,args=(self.__display_state,self.__display_flag))
        self.__display_thread.start()

    async def _loop(self) -> LevelReading|None:

        # wait until next reading is due
        await asyncio.sleep(self.__sleep_time)

        # begin performance benchmarking
        start_time = time.perf_counter()

        #-----------CAPTURE-------------
        # take the frame and record its time
        frame = self.__vc.get_image()
        t = time.time()

        #---------COMPUTER-VISION---------
        # perform CV
        frame_an = copy.copy(frame[self.__indexAn[0],self.__indexAn[1],:])
        frame_an, vol_an = _filter(frame_an,self.__scale)
        # _draw_level(frame_an,vol_an/self.__scale)

        frame_cath = copy.copy(frame[self.__indexCath[0],self.__indexCath[1],:])
        frame_cath, vol_cath = _filter(frame_cath,self.__scale)
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
        original_frame = copy.copy(frame)
        # draw the level lines on the original and filtered images
        if not isnan(avg_an) and not isnan(avg_cath):
            _draw_level(frame_an,vol_an/self.__scale)
            _draw_level(frame_cath,vol_cath/self.__scale)
            _draw_level(original_frame[self.__indexAn[0],self.__indexAn[1],:],avg_an/self.__scale)
            _draw_level(original_frame[self.__indexCath[0],self.__indexCath[1],:],avg_cath/self.__scale)
        # place the filtered images onto the original image
        frame[self.__indexAn[0],self.__indexAn[1],:] = frame_an
        frame[self.__indexCath[0],self.__indexCath[1],:] = frame_cath
        # write information text
        cv2.putText(frame, f'Electrolyte Loss: {0-avg_change} mL', (10,50), cv2.FONT_HERSHEY_SIMPLEX, 
                    0.75, (0, 0, 255), 2, cv2.LINE_AA)
        cv2.putText(frame, f'Anolyte: {avg_an} mL', (10,80), cv2.FONT_HERSHEY_SIMPLEX, 
                    0.75, (0, 0, 255), 2, cv2.LINE_AA)
        cv2.putText(frame, f'Catholyte: {avg_cath}cmL', (10,110), cv2.FONT_HERSHEY_SIMPLEX, 
                    0.75, (0, 0, 255), 2, cv2.LINE_AA)
        cv2.putText(frame, f'Diff: {avg_diff} mL', (10,140), cv2.FONT_HERSHEY_SIMPLEX, 
                    0.75, (0, 0, 255), 2, cv2.LINE_AA)

        # concatenate original and filtered images
        displayimg = np.concatenate((frame,original_frame),axis=1)
        # send to display thread
        self.__display_state.set_value(displayimg)

        #--------------UPDATE---------------
        # update the logging state
        elapsed_seconds = t - self.__initial_timestamp
        # reading is now finished, increment reading counter and record performance time
        end_time = time.perf_counter()
        perftime = (end_time-start_time)/1000 # time in seconds for computer vision
        self.__i += 1
        self.__sleep_time = max(self.__sense_period - perftime,0)

        # save reading
        # if (not isnan(reading_calculation_an)) and (not isnan(reading_calculation_cath)):
        data = [elapsed_seconds, avg_an, avg_cath, avg_diff,avg_change]

        # save the data to exposed state
        # self.__buffer.add(data)
        self.state.set_value((data,frame))
        # additional asyncio event set for pid await line
        self.sensed_event.set()

        #---------------SAVE---------------
        if self.__logging_state.force_value():
            timestamp = datetime.datetime.now().strftime("%m-%d-%Y %H-%M-%S")
            logging_data = [timestamp,*list(map(str,data))]
            self.log(logging_data)

    def teardown(self):
        self.__datafile = None
        if self.__vc is not None:
            self.__vc.close()
        self.__display_flag.clear()
        self.__display_thread.join()
        cv2.destroyAllWindows()

def _filter(frame: np.ndarray,scale: float) -> tuple[np.ndarray,float]:
    # frame: np.ndarray = cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
    # frm_height, frm_width = np.shape(frame)
    # # assert CV2_KERNEL_SIZE % 2 == 1
    # # kernel = np.ones((CV2_KERNEL_SIZE,CV2_KERNEL_SIZE))
    # # central_index = int((CV2_KERNEL_SIZE-1)/2)
    # # kernel[central_index,0:CV2_KERNEL_SIZE] = np.ones(CV2_KERNEL_SIZE)
    # # kernel[0:CV2_KERNEL_SIZE,central_index] = np.ones(CV2_KERNEL_SIZE)

    # thresh_window_size = max(np.floor(frm_height/3),frm_width)
    # # round to odd number
    # thresh_window_size += thresh_window_size % 2 -1


    # kernel = np.ones((3,int(3*frm_width/4)))
    # _, frame = cv2.threshold(frame,0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    # # frame = cv2.adaptiveThreshold(frame,255,cv2.ADAPTIVE_THRESH_MEAN_C,cv2.THRESH_BINARY,thresh_window_size,-10)
    # frame = cv2.morphologyEx(frame,cv2.MORPH_CLOSE,kernel,borderType=cv2.BORDER_REPLICATE)
    # frame = np.array(cv2.GaussianBlur(frame,(7,7),sigmaX=5,sigmaY=0.1))
    # num_nonzero = np.zeros(frm_width)
    # for i,pixel_column in enumerate(frame.T):
    #     num_nonzero[i] = np.size(pixel_column)-cv2.countNonZero(pixel_column)
    # median_height = float(np.median(num_nonzero))
    # frame = cv2.cvtColor(frame,cv2.COLOR_GRAY2BGR)

    frame: np.ndarray = cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
    frm_height, frm_width = np.shape(frame)

    # Generate list of average brithnesses of each row in image
    pow_fun = PowerFunction(1/3)
    avg_brightness = meanrows(frame,pow_fun.solve)
    
    
    kernel_size = int(math.floor(frm_height/4))
    kernel_size += kernel_size % 2 -1

    # Perform adaptive thresholding on average list using mean-C technique
    thresh_rows = adaptive_y_threshold(avg_brightness,window_size=kernel_size,C=-2)

    # Perform a morph close to remove erroneous regions:
    # First perform a morph erode
    thresh_rows = morph_erode_1d(thresh_rows,kernel_size)
    # Next a morph dilate
    thresh_rows = morph_dilate_1d(thresh_rows,kernel_size)

    # Select only the lowest region of dark in case more than 1 region remains
    thresh_rows = select_final(thresh_rows)

    # Convert the 1D list into the original frame shape again (extrapolate rows)
    for rownumber in range(0,frm_height):
        frame[rownumber,:] = thresh_rows[rownumber]
    # Convert back to RGB format
    frame = cv2.cvtColor(frame,cv2.COLOR_GRAY2BGR)

    # Get number of dark pixels to calculate height with
    npixels = 0
    for i in range(0,len(thresh_rows)):
        if thresh_rows[i] == 0: 
            npixels+=1

    return frame,scale*npixels

def adaptive_y_threshold(avg_list: list[int], window_size: int = 11, C: int = 0):
    if window_size % 2 == 0:
        raise ValueError("Even kernel size supplied to adaptive threshold")
    imid = math.floor(window_size/2)
    size_in = len(avg_list)
    thresh_out = [0]*size_in
    for i in range(0,size_in):
        vals_in_window = [0] * window_size
        minimum_index = i-imid
        maximum_index = i+imid


        minimum_window_index = 0
        if minimum_index < 0:
            minimum_window_index = -minimum_index
            vals_in_window[0:minimum_window_index] = [avg_list[0]]*minimum_window_index


        maximum_window_index = window_size -1
        if maximum_index > size_in -1:
            maximum_window_index = maximum_index - (size_in-1)
            vals_in_window[maximum_window_index:-1] = [avg_list[-1]]*(window_size-1-maximum_window_index)

        for jnormal in range (minimum_window_index,maximum_window_index):
            mainindex = i - imid + jnormal -1
            try:
                vals_in_window[jnormal] = avg_list[mainindex]
            except:
                print(mainindex)
                pass
        window_thresh = np.mean(vals_in_window) - C
        thresh_out[i] = 0 if avg_list[i] < window_thresh else 255
    return thresh_out

def select_final(thresh_in: list[int]):
    size_in = len(thresh_in)
    left = 0
    right = 0
    for i in range(0,size_in):
        if thresh_in[i] == 0:
            right = i
        else:
            left = i
    if right>left:
        left +=1
        thresh_in[0:left] = [255]*left
        thresh_in[left:right+1] = [0]*(right+1-left)
    return thresh_in

def morph_erode_1d(img: list[int], window_size: int = 11):
    if window_size % 2 == 0:
        raise ValueError("Even kernel size supplied to morph close")
    size_in = len(img)
    imid = math.floor(window_size/2)
    padded_data = [255]*imid + img + [0]*imid
    thresh_out = [0]*size_in

    for i in range(0,size_in):
        window = padded_data[i:i+window_size]
        set_to_full = False
        for j in range(0,window_size):
            if window[j] > 0:
                set_to_full = True
        thresh_out[i] = 255 if set_to_full else img[i]
    return thresh_out

def morph_dilate_1d(img: list[int], window_size: int = 11):
    if window_size % 2 == 0:
        raise ValueError("Even kernel size supplied to morph close")
    size_in = len(img)
    imid = math.floor(window_size/2)
    padded_data = [255]*imid + img + [0]*imid
    thresh_out = [0]*size_in
    for i in range(0,size_in):
        window = padded_data[i:i+window_size]
        set_to_zero = False
        for j in range(0,window_size):
            if window[j] == 0:
                set_to_zero = True
        thresh_out[i] = 0 if set_to_zero else img[i]
    return thresh_out

def meanrows(frame_in: np.ndarray,weightfun: Callable[[int],float]) -> list[int]:
    # Generate weights
    weights = np.zeros(frame_in.shape)
    for rownum in range(0,frame_in.shape[0]):
        for colnum in range(0,frame_in.shape[1]):
            weights[rownum,colnum] = weightfun(frame_in[rownum,colnum])
   
   # Apply weighted mean to each row
    frm_rows,frm_cols = frame_in.shape
    vals_out = [0]*frm_rows
    for rownum in range(0,frm_rows):
        
        numerator = np.sum(np.multiply(weights[rownum,:],frame_in[rownum,:]))
        denominator = np.sum(weights[rownum,:])
        vals_out[rownum] = numerator/denominator
    return vals_out


class Function:
    def __init__(self,*parameters,**optional_parameters):
        pass

    def solve(self,x: int) -> float:
        pass

class PowerFunction(Function):
    def __init__(self,power: float,*args,maxval: int = 255,**kwargs):
        super().__init__(*args,**kwargs)
        self.power = power
        self.maxval = maxval

    def solve(self,x: int) -> float:
        return (x/self.maxval)**self.power


def _draw_level(frame: np.array,height_from_base: float):
    sz = np.shape(frame)
    height_from_base = int(height_from_base)
    frm_height=sz[0]
    frm_width=sz[1]
    try:
        # frame might be color already
        frame = cv2.cvtColor(frame,cv2.COLOR_GRAY2BGR)
    except:
        pass
    cv2.line(frame,(0,frm_height-height_from_base),(frm_width-1,frm_height-height_from_base),(0,0,255),thickness=2)

def _get_indices(r: Rect):
    return  (slice(r[1],r[1]+r[3]), slice(r[0],r[0]+r[2]))

def _continuous_display(imgstate: SharedState[np.ndarray|None],run_event: threading.Event):
    run_event.set()
    try:
        while run_event.is_set():
            newimg = imgstate.get_value()
            if newimg is not None:
                cv2.imshow("Camera Feed",newimg)
                cv2.waitKey(1)
            time.sleep(0.1)
    finally:
        run_event.clear()
        cv2.destroyAllWindows()

class DummySensor(Generator[tuple[LevelReading,np.ndarray|None]],Loggable):

    def __init__(self,sensed_event = asyncio.Event(), logging_state: SharedState[bool] = SharedState(False), rel_level_directory="\\pumps\\levels",**kwargs) -> None:
        super().__init__()
        self.__FILENAME = "C:\\Users\\Thoma\\Documents\\Engineering\\Part C\\4YP\\controller\\pump_control\\dummy_level_data.csv"
        self.__logging_state = logging_state
        self.sensed_event = sensed_event
        self.f = None
        self.__vol_init: float|None = None
    
    def set_vision_parameters(self,*args):
        pass

    async def _setup(self):
        await asyncio.sleep(1)
        self.f = open(self.__FILENAME,mode="r",encoding="utf-8")
        self.f.readline()
        self.f.readline()
        first_data = self.f.readline().rstrip("\n".split(","))
        self.__vol_init = first_data[1] + first_data[2]
        self.__initial_timestamp = time.time()

    async def _loop(self):
        await asyncio.sleep(5)
        new_data = self.f.readline().rstrip("\n").split(",")[1:]
        

        timestamp = datetime.datetime.now().strftime("%m-%d-%Y %H-%M-%S")
        elapsed_time = time.time()-self.__initial_timestamp
        data_out = [elapsed_time,*new_data,float(new_data[1])+float(new_data[2])-self.__vol_init]
        self.state.set_value((data_out,None))
        self.sensed_event.set()
        if self.__logging_state.force_value():
            self.log([timestamp,*data_out])

    def teardown(self):
        self.f.close()
        return super().teardown()
