from abc import ABC, abstractmethod
import asyncio
from .shared_state import SharedState
from typing import TypeVar, Generic
import time

T = TypeVar("T")

class GeneratorException(BaseException):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)

class Generator(Generic[T],ABC):

    def __init__(self,*args,**kwargs) -> None:
        super().__init__(*args,**kwargs)
        self.state = SharedState[T]()
        self.__flag = asyncio.Event()
        self.is_running = SharedState[bool](False)
    
    @abstractmethod
    async def _setup(self) -> None:
        pass

    @abstractmethod
    async def _loop(self) -> T|None:
        pass

    async def generate(self):
        self.__flag.clear()
        try:
            await self._setup()
            self.is_running.set_value(True)
            while not self.__flag.is_set():
                new_state = await self._loop()
                if new_state is not None:
                    self.state.set_value(new_state)
        finally:
            self.__flag.set()
            self.is_running.set_value(False)
            self.teardown()

    async def _wait_while_checking(self,wait_duration: float, check_interval = 0.1):
        t_start = time.time()
        t = t_start
        while t-t_start<wait_duration and not self.__flag.is_set():
            await asyncio.sleep(check_interval)
            t = time.time()


    @abstractmethod
    def teardown(self):
        pass

    def can_generate(self):
        return not self.__flag.is_set()
    
    def stop(self):
        self.__flag.set()
