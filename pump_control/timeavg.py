from collections import deque
import numpy as np
    
class TimeAvg:

    def __init__(self,delta_t: float,data_size: int = 0):
        self.dt = delta_t
        self.stream = deque[_DataPoint]()
        self.__data_size = data_size

    @property
    def furthest_time(self) -> float|None:
        if len(self.stream)<1:
            return None
        return self.stream[-1].time
    @property
    def latest_time(self) -> float|None:
        if len(self.stream)<1:
            return None
        return self.stream[0].time
    
    def append(self,data: list[float], timestamp: float):
        if not isinstance(data,list):
            data = list(data)
        if self.__data_size == 0:
            self.__data_size = len(data)
        elif len(data) != self.__data_size or len(data)<1:
            raise ValueError("Time data size does not match that already in memory")
        datap = _DataPoint(list(map(float,data)),timestamp)

        self.stream.append(datap)
        if self.furthest_time is not None and self.latest_time is not None:
            while self.latest_time-self.furthest_time>self.dt:
                self.stream.popleft()

    def calculate(self) -> list[float]:
        twod_list = [datapoint.data for datapoint in self.stream]
        out= list(np.mean(np.array(twod_list),axis=0))
        return out
    
    @staticmethod
    def from_old(old_timeavg: "TimeAvg",delta_t) -> "TimeAvg":
        new_timeavg = TimeAvg(delta_t,data_size = old_timeavg.__data_size)
        new_timeavg.stream = old_timeavg.stream
        if len(old_timeavg.stream)<1:
            return new_timeavg
        if new_timeavg.furthest_time is not None and new_timeavg.latest_time is not None:
            while new_timeavg.latest_time - new_timeavg.furthest_time > delta_t:
                new_timeavg.stream.popleft()
        return new_timeavg

        

class _DataPoint:

    def __init__(self,data: list[float], time: float) -> None:
        self.data = data
        self.time = time
