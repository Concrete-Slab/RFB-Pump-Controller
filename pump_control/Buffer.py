from typing import Generic, TypeVar
import numpy as np

T = TypeVar('T')

class Buffer(Generic[T]):
    def __init__(self,initial_buffer_size) -> None:
        super().__init__()
        self._N = initial_buffer_size
        self.__n = 0
        self.__buffer: list[T] = []
    
    def add(self,val:T):
        if self.__n < self._N:
            self.__buffer.append(val)
            self.__n += 1
        else:
            self.__buffer.pop(0)
            self.__buffer.append(val)

    def set_N(self,newN):
        if newN >= self._N:
            self._N = newN
        elif newN > 0:
            startIndex = self.__n-newN
            if startIndex > 0:
                self.__buffer = self.__buffer[startIndex:]
                self.__n = newN
            else:
                self.__buffer = []
                self.__n = 0
    
    def get_N(self):
        return self._N
            

    def read(self):
        return self.__buffer
