from typing import TypeVar, Generic
from threading import Event

T = TypeVar("T")
class SharedState(Generic[T]):

    def __init__(self,initialValue: T=None) -> None:
        self.value: T | None = initialValue
        self.__event = Event()

    def set_value(self,value: T):
        self.value = value
        self.__event.set()

    def get_value(self) -> T | None:
        if self.__event.is_set():
            self.__event.clear()
            return self.value
        else:
            return None

