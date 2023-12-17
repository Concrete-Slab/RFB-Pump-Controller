from support_classes import Generator, SharedState, GeneratorException, Loggable
from .PUMP_CONSTS import LEVEL_SENSE_PERIOD, BUFFER_WINDOW_LENGTH, LEVEL_AVERAGE_PERIOD, CV2_KERNEL_SIZE, LEVEL_STABILISATION_PERIOD
from .Buffer import Buffer
from .timeavg import TimeAvg
import cv2
import datetime
import asyncio
import time
from math import isnan
from pathlib import Path
from .datalogger import log_data
import numpy as np
import copy
import threading



#TODO change this to typing.Sequence[int] if error
Rect = tuple[int,int,int,int]

LevelBuffer = Buffer[list[float]]

class LevelSensor(Generator[tuple[LevelBuffer,np.ndarray|None]],Loggable):

    LOG_COLUMN_HEADERS = ["Timestamp","Elapsed Time","Anolyte Level Avg", "Catholyte Avg","Avg Difference","Total Change in Electrolyte Level"]
    DEFAULT_DIRECTORY = "pumps/levels"

    def __init__(self, sensed_event = asyncio.Event(), logging_state: SharedState[bool] = SharedState(False), absolute_logging_path: Path|None=None,**kwargs) -> None:
        

        if absolute_logging_path is None:
            absolute_logging_path = Path(__file__).absolute().parent / LevelSensor.DEFAULT_DIRECTORY
        super().__init__(directory = absolute_logging_path,default_headers = LevelSensor.LOG_COLUMN_HEADERS)
        
        # shared states:
        # logging shared state: boolean that determines if data is saved
        self.__logging_state = logging_state
        # threading shared state: image that is updated with every new capture
        self.__display_state: SharedState[np.ndarray|None] = SharedState(initialValue=None)
        self.__display_flag = threading.Event()
        self.__display_thread = threading.Thread(target=_continuous_display,args=(self.__display_state,self.__display_flag))

        # video parameters to be set at a later time before generation
        self.__vc: cv2.VideoCapture|None = None
        self.__video_device: int|None = None   
        self.__vol_init: float|None = None

        # public exposed property: signals that a level reading has been made
        # when set, it indicates that a reading has been made that has not been 
        self.sensed_event = sensed_event

        # external buffer for averaging level readings
        buffer_size = int(BUFFER_WINDOW_LENGTH/LEVEL_SENSE_PERIOD)
        self.__buffer = LevelBuffer(buffer_size)
        # secretly set the buffer to the correct size without notifying of the change
        self.state.value = (self.__buffer, None)

        # internal buffer for averaging level readings
        self.__reading_an = TimeAvg(LEVEL_AVERAGE_PERIOD)
        self.__reading_cath = TimeAvg(LEVEL_AVERAGE_PERIOD)

        # loop counter: used in calculation for offset period
        self.__i: int = 0

    def set_vision_parameters(self, video_device: int, rect1: Rect, rect2: Rect, rect_ref: Rect, vol_ref: float):
        
        if any((video_device is None, rect1 is None, rect2 is None, rect_ref is None, vol_ref is None)):
            raise GeneratorException("Null values supplied to level sensor parameters")
        self.__video_device = video_device
        self.__indexAn = _get_indices(rect1)
        self.__indexCath = _get_indices(rect2)
        self.__scale = vol_ref/rect_ref[3]
        pass

    async def _setup(self):
        if any((self.__video_device is None, self.__indexAn is None, self.__indexCath is None, self.__scale is None)):
            raise GeneratorException("Null values supplied to level sensor parameters")
        self.new_file()
        self.__vc = cv2.VideoCapture(self.__video_device)
        self.__i = 0
        self.__initial_timestamp = time.time()
        self.__sleep_time = 0.5
        self.__display_thread = threading.Thread(target=_continuous_display,args=(self.__display_state,self.__display_flag))
        self.__display_thread.start()

    async def _loop(self) -> LevelBuffer|None:

        # wait until next reading is due
        await asyncio.sleep(self.__sleep_time)

        # begin performance benchmarking
        start_time = time.perf_counter()

        #-----------CAPTURE-------------
        # take the frame and record its time
        rval, frame = self.__vc.read()
        t = time.time()

        #---------COMPUTER-VISION---------
        # perform CV
        frame_an = copy.copy(frame[self.__indexAn[0],self.__indexAn[1],:])
        frame_an, vol_an = _filter(frame_an,self.__scale)
        # _draw_level(frame_an,vol_an/self.__scale)

        frame_cath = copy.copy(frame[self.__indexCath[0],self.__indexCath[1],:])
        frame_cath, vol_cath = _filter(frame_cath,self.__scale)
        # _draw_level(frame_cath,vol_cath/self.__scale)

        # store CV results in internal buffer and calculate new average readings
        self.__reading_an.append([vol_an,t])
        self.__reading_cath.append([vol_cath,t])
        reading_calculation_an = self.__reading_an.calculate()
        reading_calculation_cath = self.__reading_cath.calculate()

        # set the initial volume to the current volume while still in stabilisation period
        if self.__i*LEVEL_SENSE_PERIOD<LEVEL_STABILISATION_PERIOD:
            self.__vol_init = reading_calculation_an + reading_calculation_cath

        net_vol_change = reading_calculation_an + reading_calculation_cath - self.__vol_init
        vol_diff = reading_calculation_an - reading_calculation_cath

        #---------------DISPLAY-------------------
        original_frame = copy.copy(frame)
        # draw the level lines on the original and filtered images
        if not isnan(reading_calculation_an) and not isnan(reading_calculation_cath):
            _draw_level(frame_an,reading_calculation_an/self.__scale)
            _draw_level(frame_cath,reading_calculation_cath/self.__scale)
            _draw_level(original_frame[self.__indexAn[0],self.__indexAn[1],:],reading_calculation_an/self.__scale)
            _draw_level(original_frame[self.__indexCath[0],self.__indexCath[1],:],reading_calculation_cath/self.__scale)
        # place the filtered images onto the original image
        frame[self.__indexAn[0],self.__indexAn[1],:] = frame_an
        frame[self.__indexCath[0],self.__indexCath[1],:] = frame_cath
        # write information text
        cv2.putText(frame, f'Electrolyte Loss:{0-net_vol_change}mL', (10,50), cv2.FONT_HERSHEY_SIMPLEX, 
                    0.5, (0, 0, 255), 2, cv2.LINE_AA)
        cv2.putText(frame, f'Anolyte: {reading_calculation_an}mL', (10,70), cv2.FONT_HERSHEY_SIMPLEX, 
                    0.5, (0, 0, 255), 2, cv2.LINE_AA)
        cv2.putText(frame, f'Catholyte: {reading_calculation_cath}mL', (10,90), cv2.FONT_HERSHEY_SIMPLEX, 
                    0.5, (0, 0, 255), 2, cv2.LINE_AA)
        cv2.putText(frame, f'Diff: {vol_diff}mL', (10,110), cv2.FONT_HERSHEY_SIMPLEX, 
                    0.5, (0, 0, 255), 2, cv2.LINE_AA)
        cv2.putText(frame, f'Anolyte: {reading_calculation_an}mL', (20,50), cv2.FONT_HERSHEY_SIMPLEX, 
                    0.5, (0, 0, 255), 2, cv2.LINE_AA)
        cv2.putText(frame, f'Catholyte: {reading_calculation_cath}mL', (30,50), cv2.FONT_HERSHEY_SIMPLEX, 
                    0.5, (0, 0, 255), 2, cv2.LINE_AA)
        cv2.putText(frame, f'Diff: {vol_diff}m', (40,50), cv2.FONT_HERSHEY_SIMPLEX, 
                    0.5, (0, 0, 255), 2, cv2.LINE_AA)

        # concatenate original and filtered images
        displayimg = np.concatenate((frame,original_frame),axis=1)
        # send to display thread
        self.__display_state.set_value(displayimg)


        #--------------SAVE---------------
        # update the logging state
        elapsed_seconds = t - self.__initial_timestamp
        # reading is now finished, increment reading counter and record performance time
        end_time = time.perf_counter()
        perftime = (end_time-start_time)/1000 # time in seconds for computer vision
        self.__i += 1
        self.__sleep_time = max(LEVEL_SENSE_PERIOD - perftime,0)

        # save reading
        if (not isnan(reading_calculation_an)) and (not isnan(reading_calculation_cath)):
            data = [elapsed_seconds, reading_calculation_an, reading_calculation_cath, vol_diff,net_vol_change]

            # save the data to the internal buffer and the exposed state
            self.__buffer.add(data)
            self.state.set_value((self.__buffer,frame))
            # additional asyncio event set for pid await line
            self.sensed_event.set()

            if self.__logging_state.force_value():
                timestamp = datetime.datetime.now().strftime("%m-%d-%Y %H-%M-%S")
                logging_data = [timestamp,*list(map(str,data))]
                self.log(logging_data)
                # timestamp = datetime.datetime.now().strftime("%m-%d-%Y %H-%M-%S")
                # data_str = [timestamp] + list(map(str,data))
                # if self.__datafile is None:
                #     self.__datafile = timestamp
                # log_data(self.__LOG_PATH,self.__datafile,data_str,column_headers=self.LOG_COLUMN_HEADERS)

    def teardown(self):
        self.__datafile = None
        if self.__vc is not None:
            self.__vc.release()
        self.__display_flag.clear()
        self.__display_thread.join()
        cv2.destroyAllWindows()

def _filter(frame: np.ndarray,scale: float) -> tuple[np.ndarray,float]:
    frame: np.ndarray = cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
    frm_width = np.shape(frame)[1]
    # assert CV2_KERNEL_SIZE % 2 == 1
    # kernel = np.ones((CV2_KERNEL_SIZE,CV2_KERNEL_SIZE))
    # central_index = int((CV2_KERNEL_SIZE-1)/2)
    # kernel[central_index,0:CV2_KERNEL_SIZE] = np.ones(CV2_KERNEL_SIZE)
    # kernel[0:CV2_KERNEL_SIZE,central_index] = np.ones(CV2_KERNEL_SIZE)

    kernel = np.ones((3,int(frm_width/2)))
    _, frame = cv2.threshold(frame,0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    frame = cv2.morphologyEx(frame,cv2.MORPH_CLOSE,kernel,borderType=cv2.BORDER_REPLICATE)
    frame = np.array(cv2.GaussianBlur(frame,(7,7),sigmaX=5,sigmaY=0.1))
    num_nonzero = np.zeros(frm_width)
    for i,pixel_column in enumerate(frame.T):
        num_nonzero[i] = np.size(pixel_column)-cv2.countNonZero(pixel_column)
    median_height = float(np.median(num_nonzero))
    frame = cv2.cvtColor(frame,cv2.COLOR_GRAY2BGR)
    return frame,scale*median_height

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
        cv2.destroyWindow("Camera Feed")

class DummySensor(Generator[tuple[LevelBuffer,np.ndarray|None]],Loggable):

    def __init__(self,sensed_event = asyncio.Event(), logging_state: SharedState[bool] = SharedState(False), rel_level_directory="\\pumps\\levels",**kwargs) -> None:
        super().__init__()
        self.__FILENAME = "C:\\Users\\Thoma\\Documents\\Engineering\\Part C\\4YP\\controller\\pump_control\\dummy_level_data.csv"
        buffer_size = int(BUFFER_WINDOW_LENGTH/LEVEL_SENSE_PERIOD)
        self.__buffer = LevelBuffer(buffer_size)
        # secretly set the buffer to the correct size
        self.state.value = (self.__buffer,None)
        self.__logging_state = logging_state
        self.sensed_event = sensed_event
        self.f = None
    
    def set_vision_parameters(self,*args):
        pass

    async def _setup(self):
        await asyncio.sleep(1)
        self.f = open(self.__FILENAME,mode="r",encoding="utf-8")
        self.f.readline()
        self.f.readline()

    async def _loop(self):
        await asyncio.sleep(5)
        nextdiff = float(self.f.readline().rstrip("\n").split(",")[3])
        self.__buffer.add(nextdiff)
        self.state.set_value((self.__buffer,None))
        self.sensed_event.set()
        if self.__logging_state.force_value():
            self.log(nextdiff)

    def teardown(self):
        self.f.close()
        return super().teardown()
