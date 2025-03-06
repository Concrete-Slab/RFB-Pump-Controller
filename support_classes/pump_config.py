from enum import StrEnum
from typing import Type, cast
    
class PumpNames(StrEnum):
    pass

class PumpConfig:
    allowable_values = list("abcdefghijklmnopqrstuvwxyz")
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(PumpConfig, cls).__new__(cls)
            cls._instance._pumps = None
            cls._instance._frozen = False
        return cls._instance
    
    max_pumps = len(allowable_values)
    
    def generate_pumps(self, n: int):
        if self._frozen:
            raise RuntimeError("Singleton is immutable - pump assignments cannot be changed")
        allowable_values = list("abcdefghijklmnopqrstuvwxyz")
        if n<1 or n>len(allowable_values):
            raise ValueError("There must be between 1 and 26 pumps")
        # Dynamic Enum creation, with type cast for pylance inference
        pump_enum = PumpNames("PumpNames",{item.upper():item for item in allowable_values[:n]},module=__name__)
        self._pumps = cast(Type[PumpNames],pump_enum)
        self._frozen = True

    @property
    def pumps(self):
        if self._pumps is None:
            raise RuntimeError("Pumps have not been generated yet")
        return self._pumps
