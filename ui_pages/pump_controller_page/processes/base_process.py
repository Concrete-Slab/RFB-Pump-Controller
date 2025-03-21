from abc import ABC, abstractmethod
from ui_root import UIController
from pump_control import Pump

class BaseProcess(ABC):

    def __init__(self,controller_context: UIController, pump_context: Pump):
        self._controller_context = controller_context
        self._pump_context = pump_context
        self._removal_callbacks = []

    @property
    @abstractmethod
    def name(self) -> str:
        pass
    @abstractmethod
    def start(self) -> None:
        pass
    @abstractmethod
    def close(self) -> None:
        pass
    @property
    @abstractmethod
    def has_settings(self) -> bool:
        pass
    @abstractmethod
    def open_settings(self) -> None:
        pass