from typing import TypeVar, Generic
from threading import Event, Lock

T = TypeVar("T")
class SharedState(Generic[T]):

    def __init__(self,initialValue: T=None) -> None:
        self.value: T | None = initialValue
        self.__event = Event()
        self.__lock = Lock()

    def set_value(self,value: T):
        with self.__lock:
            self.value = value
            self.__event.set()

    def get_value(self) -> T | None:
        with self.__lock:
            if self.__event.is_set():
                self.__event.clear()
                val = self.value
                return val
            else:
                return None
