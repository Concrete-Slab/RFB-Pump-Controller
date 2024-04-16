from collections import deque

class TimeAvg:

    def __init__(self,delta_t: int,data_size: int = 0) -> None:
        self.__delta_t = delta_t
        self.stream: deque[_DataPoint] = deque()
        self.__latest_time: float|None = None
        self.__furthest_time: float|None = None
        self.__data_size = data_size

    def append(self, data: list[float], timestamp):
        if not isinstance(data,list):
            data = [data]
        if self.__data_size == 0:
            self.__data_size = len(data)
        elif len(data) != self.__data_size:
            raise ValueError("Time data size does not match that already in memory")
        new_point = _DataPoint(data,timestamp)
        self.__latest_time = timestamp
        if self.__furthest_time is None:
            self.__furthest_time = timestamp
        while self.__latest_time - self.__furthest_time > self.__delta_t:
            self.stream.popleft()
            self.__furthest_time = self.stream[0].time
        self.stream.append(new_point)
    
    def calculate(self):
        averages = [0.0]*self.__data_size
        if len(self.stream)<1:
            return averages
        for i in range(0,self.__data_size):
            total = 0
            for j in range(0,len(self.stream)):
                total = total + self.stream[j].data[i]
            averages[i] = total/(j+1)
        return averages
    
    @staticmethod
    def from_old(old_timeavg: "TimeAvg",delta_t) -> "TimeAvg":
        new_timeavg = TimeAvg(delta_t,data_size = old_timeavg.__data_size)
        new_timeavg.stream = old_timeavg.stream
        if len(old_timeavg.stream)<1:
            return new_timeavg
        while new_timeavg.stream[-1].time - new_timeavg.stream[0].time > delta_t:
            new_timeavg.stream.popleft()
        return new_timeavg

class _DataPoint:

    def __init__(self,data: list[float], time: float) -> None:
        self.data = data
        self.time = time
