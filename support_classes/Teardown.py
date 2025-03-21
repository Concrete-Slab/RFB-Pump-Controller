from typing import Callable
from abc import ABC,abstractmethod

class Teardown(ABC):
    """Class that implements a teardown function to be run at program termination"""
    def __init__(self,*args,**kwargs) -> None:
        super().__init__()
        TDExecutor.register(self.teardown)
        pass


    @abstractmethod
    def teardown(self):
        """Sync function to be run either after main thread terminates or after all threads have terminated, depending on implementation"""
        pass


class TDExecutor:
    
    __teardowns = []

    def register(callback: Callable[[None],None]):
        TDExecutor.__teardowns.append(callback)

    def unregister(callback: Callable[[None],None]):
        TDExecutor.__teardowns.remove(callback)

    def execute():
        for cb in TDExecutor.__teardowns:
            try:
                cb()
            except:
                continue
    
def with_teardown(fun):
    def inner(*args,**kwargs):
        try:
            return fun(*args,**kwargs)
        finally:
            TDExecutor.execute()
    return inner