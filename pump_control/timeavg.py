from collections import deque
import numpy as np

# class TimeAvg():
#     def __init__(self, delta_t):
#         self.delta_t = delta_t
#         self.stream = deque()

#     def append(self, datapoint):
#         stream = self.stream
#         stream.append(datapoint)    # appends on the right
#         length = len(stream)
#         if length < 1:
#             return -1
#         real_delta_t = stream[length - 1][1] - stream[0][1]
#         while real_delta_t > self.delta_t:
#             stream.popleft()
#             length -= 1
#             real_delta_t = stream[length - 1][1] - stream[0][1]

#     def calculate(self):
#         stream = self.stream
#         length = len(stream)
#         if length < 1:
#             return -1
#         real_delta_t = stream[length - 1][1] - stream[0][1]
#         while real_delta_t > self.delta_t:
#             stream.popleft()
#             length -= 1
#             real_delta_t = stream[length - 1][1] - stream[0][1]
#         y = np.array(stream)[:, 0]
#         t = np.array(stream)[:, 1]
#         return np.trapz(y, x=t) / (real_delta_t)

class TimeAvg:

    def __init__(self,delta_t,data_size: int = 0) -> None:
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
        print(f"data is {data}")
        new_point = _DataPoint(data,timestamp)
        self.__latest_time = timestamp
        if self.__furthest_time is None:
            self.__furthest_time = timestamp
        while self.__latest_time - self.__furthest_time > self.__delta_t:
            self.stream.popleft()
            self.__furthest_time = self.stream[0].time
        self.stream.append(new_point)
    
    def calculate(self):
        if len(self.stream)<1:
            return 0
        averages = [0]*self.__data_size
        for i in range(0,self.__data_size):
            total = 0
            for j in range(0,len(self.stream)):
                total = total + self.stream[j].data[i]
            averages[i] = total/(j+1)
        return averages

class _DataPoint:

    def __init__(self,data: list[float], time: float) -> None:
        self.data = data
        self.time = time
