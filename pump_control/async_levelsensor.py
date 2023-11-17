from support_classes import Generator, SharedState, GeneratorException
from .PUMP_CONSTS import LEVEL_SENSE_PERIOD, BUFFER_WINDOW_LENGTH, LEVEL_AVERAGE_PERIOD, LEVEL_AVERAGE_PERIOD_SHORT, CV2_KERNEL
from .Buffer import Buffer
from .timeavg import TimeAvg
import cv2
import datetime
import asyncio
import csv
import time
from math import isnan
from pathlib import Path
from .datalogger import log_data

#TODO change this to typing.Sequence[int] if error
Rect = tuple[int,int,int,int]

LevelBuffer = Buffer[list[float]]

class LevelSensor(Generator[LevelBuffer]):

    LOG_COLUMN_HEADERS = ["Timestamp","Level 1 Avg", "Level 2 Avg","Avg Difference"]

    def __init__(self, sensed_event = asyncio.Event(), logging_state: SharedState[bool] = SharedState(False), rel_level_directory="\\pumps\\levels",**kwargs) -> None:
        super().__init__()

        self.__rel_level_directory = rel_level_directory.strip("\\").strip("/").replace("\\","/")
        self.__LOG_PATH = Path(__file__).absolute().parent / self.__rel_level_directory
        
        self.__delta_t = LEVEL_AVERAGE_PERIOD
        self.__delta_t_short = LEVEL_AVERAGE_PERIOD_SHORT
        self.__logging_state = logging_state
        self.__logging = self.__logging_state.value

        # video parameters to be set at a later time before generation
        self.__vc: cv2.VideoCapture|None = None
        self.__video_device: int|None = None   
        self.__rect1: Rect|None = None
        self.__rect2: Rect|None = None
        self.__rect_ref: Rect|None = None
        self.__vol_ref: float|None = None
        self.__vol_init: float|None = None

        # logging filename to be set when the first data is to be logged
        self.__datafile: str|None = None

        # public exposed property: signals that a level reading has been made
        # when set, it indicates that a reading has been made that has not been 
        self.sensed_event = sensed_event

        buffer_size = int(BUFFER_WINDOW_LENGTH/LEVEL_SENSE_PERIOD)
        self.__buffer = LevelBuffer(buffer_size)
        # secretly set the buffer to the correct size
        self.state.value = self.__buffer

        self.__kernel = CV2_KERNEL

        
        self.__reading1 = TimeAvg(self.__delta_t)
        self.__reading2 = TimeAvg(self.__delta_t)
        self.__reading1_short = TimeAvg(self.__delta_t_short)
        self.__reading2_short = TimeAvg(self.__delta_t_short)
        self.__i: int = 0

        # used for performance learning: make sure state is sent roughly every 5 seconds
        # TODO maybe improve this algorithm from just simple mean
        self.__avg_perftime = 0.0

    def set_vision_parameters(self, video_device: int, rect1: Rect, rect2: Rect, rect_ref: Rect, vol_ref: float, vol_init: float):
        
        if any((video_device is None, rect1 is None, rect2 is None, rect_ref is None, vol_ref is None, vol_init is None)):
            raise GeneratorException("Null values supplied to level sensor parameters")
        self.__video_device = video_device
        self.__rect1 = rect1
        self.__rect2 = rect2
        self.__rect_ref = rect_ref
        self.__vol_ref = vol_ref
        self.__vol_init = vol_init

    async def _setup(self):
        print("levelsensor reached beginning of setup")
        if any((self.__video_device is None, self.__rect1 is None, self.__rect2 is None, self.__rect_ref is None, self.__vol_ref is None, self.__vol_init is None)):
            raise GeneratorException("Null values supplied to level sensor parameters")

        self.__height_max = max(self.__rect1[1],self.__rect2[1])
        self.__height_min = min(self.__rect1[3],self.__rect2[3])

        self.__rect1 = (int(self.__rect1[0]), int(self.__height_max), int(self.__rect1[2]), int(self.__height_min))
        self.__rect2 = (int(self.__rect2[0]), int(self.__height_max), int(self.__rect2[2]), int(self.__height_min))
        self.__r1_area = self.__rect1[2] * self.__rect1[3]
        self.__r2_area = self.__rect2[2] * self.__rect2[3]


        self.__vc = cv2.VideoCapture(self.__video_device)
        self.__i: int = 0
        self.__initial_timestamp = time.time()
        self.__logging = self.__logging_state.value
        print("levelsensor reached end of setup")

    async def _loop(self) -> LevelBuffer|None:

        # begin performance benchmarking
        start_time = time.perf_counter()

        # take the frame and record its time
        rval, frame = self.__vc.read()
        t = time.time()

        # perform image processing operations
        frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        imCrop1 = frame[self.__height_max:int(self.__height_max +
                                            self.__height_min),
                        int(self.__rect1[0]):int(self.__rect1[0] + self.__rect1[2])]
        imCrop1 = cv2.cvtColor(imCrop1, cv2.COLOR_RGB2GRAY)
        otsu1, thr1 = cv2.threshold(
            imCrop1, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        thr1 = cv2.morphologyEx(
            thr1, cv2.MORPH_CLOSE, self.__kernel)
        thr1 = cv2.GaussianBlur(thr1, (5, 5), 0)
        imCrop2 = frame[self.__height_max:int(self.__height_max +
                                            self.__height_min),
                        int(self.__rect2[0]):int(self.__rect2[0] + self.__rect2[2])]
        imCrop2 = cv2.cvtColor(imCrop2, cv2.COLOR_RGB2GRAY)
        otsu2, thr2 = cv2.threshold(
            imCrop2, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        #ret, thr2 = cv2.threshold(
        #    imCrop2, otsu1, 255, cv2.THRESH_BINARY)
        thr2 = cv2.morphologyEx(
            thr2, cv2.MORPH_CLOSE, self.__kernel)
        thr2 = cv2.GaussianBlur(thr2, (5, 5), 0)
        
        scale = self.__vol_ref/self.__rect_ref[3]
        calc1 = scale*(self.__r1_area - cv2.countNonZero(thr1)) * 1.0 / self.__rect1[2]
        calc2 = scale*(self.__r2_area - cv2.countNonZero(thr2)) * 1.0 / self.__rect2[2]

        # # there is some dead volume, both reservoir readings should initially add to initial combined volume
        # # init_vol = calc1 + 2*offset1 + calc2
        # if(self.__i==300): # offsets are determined after some iterations to allow readings to stabilize from noise
            
        #     # This code is rather cumbersome!!
        #     reading1_short = TimeAvg(self.__delta_t_short)
        #     reading2_short = TimeAvg(self.__delta_t_short)
        #     offset = (self.__vol_init - reading1_short.calculate()-reading2_short.calculate())/2
        #     self.__reading1 = TimeAvg(self.__delta_t)
        #     self.__reading2 = TimeAvg(self.__delta_t)
        #     print('Offset completed')
        # if(self.__i>=300):
        #     calc1+=offset
        #     calc2+=offset

        self.__reading1.append([calc1, t])
        self.__reading2.append([calc2, t])
        # thr1 = cv2.cvtColor(thr1, cv2.COLOR_GRAY2RGB)
        # thr1[np.where((thr1 == [0,0,0]).all(axis = 2))] = [0,33,166]
        # thr2 = cv2.cvtColor(thr2, cv2.COLOR_GRAY2RGB)
        # thr2[np.where((thr2 == [0,0,0]).all(axis = 2))] = [0,33,166]

        # frame[self.__height_max:int(self.__height_max + self.__height_min),
        #     int(self.__rect1[0]):int(self.__rect1[0] + self.__rect1[2])] = thr1

        # frame[self.__height_max:int(self.__height_max + self.__height_min),
        #     int(self.__rect2[0]):int(self.__rect2[0] + self.__rect2[2])] = thr2
        # frame = frame





        # update the logging state
        self.__logging = self.__logging_state.value



        

        # save the data to the internal buffer and the exposed state
        elapsed_seconds = t - self.__initial_timestamp
        reading_calculation_1 = self.__reading1.calculate()
        reading_calculation_2 = self.__reading2.calculate()
        if (not isnan(reading_calculation_1)) and (not isnan(reading_calculation_2)):
            data = [elapsed_seconds, reading_calculation_1, reading_calculation_2, reading_calculation_1-reading_calculation_2]

            self.__buffer.add(data)
            self.state.set_value(self.__buffer)
            # additional asyncio event set for pid await line
            self.sensed_event.set()

            if self.__logging:
                timestamp = datetime.datetime.now().strftime("%m-%d-%Y %H-%M-%S")
                data_str = [timestamp] + list(map(str,data))
                if self.__datafile is None:
                    self.__datafile = timestamp
                log_data(self.__LOG_PATH,self.__datafile,data_str,column_headers=self.LOG_COLUMN_HEADERS)
                # if self.__datafile is None:

                    
                #     # create file and write the first line of data
                #     timestamp = datetime.datetime.now().strftime("%m-%d-%Y %H-%M-%S")
                #     proposal_directory = self.__SCRIPT_LOCATION / self.__rel_level_directory
                #     if not os.path.isdir(proposal_directory.as_posix()):
                #         os.makedirs(proposal_directory.as_posix())
                #     filepath = proposal_directory / f"/{timestamp}.csv"
                #     filepath = Path(__file__).absolute().parent / f"{self.__rel_level_directory}/{timestamp}.csv"
                #     self.__datafile = filepath.as_posix()
                #     with open(self.__datafile, "a+", newline='') as f:
                #         writer = csv.writer(f, delimiter=",")
                #         writer.writerow(['Time (seconds elapsed)', 'Left (mL)', 'Right (mL)'])
                #         writer.writerow(data)
                # else:
                #     # write the new data onto the existing file
                #     with open(self.__datafile, "a", newline='') as f:
                #         writer = csv.writer(f, delimiter=",")
                #         writer.writerow(data)
        

        
        # reading is now finished, increment reading counter and record performance time
        end_time = time.perf_counter()
        perftime = (end_time-start_time)/1000 # time in seconds for computer vision
        self.__i += 1

        # save data roughly every 5 seconds
        # avgperf = self.__update_perftime(perftime)
        sleep_time = max(LEVEL_SENSE_PERIOD - perftime,0)
        await asyncio.sleep(sleep_time)


    def __update_perftime(self,newperftime) -> float:
        newavg = (self.__avg_perftime*self.__i + newperftime) / (self.__i+1)
        self.__avg_perftime = newavg
        return newavg

    def teardown(self):
        self.__datafile = None
        if self.__vc is not None:
            self.__vc.release()
        cv2.destroyAllWindows()

    

class DummySensor(Generator[LevelBuffer]):

    def __init__(self,sensed_event = asyncio.Event(), logging_state: SharedState[bool] = SharedState(False), rel_level_directory="\\pumps\\levels",**kwargs) -> None:
        super().__init__()
        self.__FILENAME = "C:\\Users\\Thoma\\Documents\\Engineering\\Part C\\4YP\\controller\\pump_control\\dummy_level_data.csv"
        buffer_size = int(BUFFER_WINDOW_LENGTH/LEVEL_SENSE_PERIOD)
        self.__buffer = LevelBuffer(buffer_size)
        # secretly set the buffer to the correct size
        self.state.value = self.__buffer
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
        self.state.set_value(self.__buffer)
        self.sensed_event.set()

    def teardown(self):
        self.f.close()
        return super().teardown()





