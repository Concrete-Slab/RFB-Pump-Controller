from typing import TypeVar, Generic
from threading import Event, Lock
import multiprocessing as mp

T = TypeVar("T")
class SharedState(Generic[T]):

    def __init__(self,initialValue: T=None) -> None:
        self.value: T | None = initialValue
        self._event = Event()
        self._lock = Lock()

    def set_value(self,value: T):
        with self._lock:
            self.value = value
            self._event.set()

    def get_value(self) -> T | None:
        with self._lock:
            if self._event.is_set():
                self._event.clear()
                val = self.value
                return val
            else:
                return None
            
    def force_value(self):
        with self._lock:
            return self.value
        
T = TypeVar("T")
class MPSharedState(Generic[T]):
    def __init__(self, initialValue: T = None) -> None:
        manager = mp.Manager()
        self.value = manager.list([initialValue])
        self._event = mp.Event()

    def set_value(self, value: T):
        with self.value as v:
            v[0] = value
            self._event.set()
            print("setting value", value)

    def get_value(self) -> T | None:
        with self.value as v:
            if self._event.is_set():
                self._event.clear()
                return v[0]  # Access the actual value
            else:
                return None

    def force_value(self):
        with self.value as v:
            return v[0]


