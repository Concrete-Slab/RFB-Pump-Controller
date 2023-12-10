from abc import ABC,abstractmethod
from .UIController import UIController
from pump_control import Pump, PumpNames
from enum import Enum
from .PAGE_EVENTS import CEvents
from .toplevel_boxes import LevelSelect,DataSettingsBox
from typing import Any


class BaseProcess(ABC):
    __instance = None

    def __init__(self,controller_context: UIController|None = None, pump_context: Pump|None = None):
        self._controller_context = controller_context
        self._pump_context = pump_context
        self._removal_callbacks = []

    def set_context(self,controller_context: UIController, pump_context: Pump):
        self._controller_context = controller_context
        self._pump_context = pump_context

    @classmethod
    def get_instance(cls):
        if cls.__instance is None:
            cls.__instance = cls()
        return cls.__instance

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

class PIDProcess(BaseProcess):
    @property
    def name(self):
        return "PID"
    
    def start(self):
        if self._controller_context and self._pump_context:
            (state_running,state_duties) = self._pump_context.start_pid()
            if len(self._removal_callbacks) == 0:
                self._removal_callbacks.append(self._controller_context._add_state(state_running,self.__handle_running))
                self._removal_callbacks.append(self._controller_context._add_state(state_duties,self.__handle_duties))
    
    def __handle_running(self,newstate: bool):
        if self._controller_context:
            if newstate:
                self._controller_context.notify_event(CEvents.PROCESS_STARTED,ProcessName.PID)
            else:
                self._controller_context.notify_event(CEvents.PROCESS_CLOSED,ProcessName.PID)

    def __handle_duties(self,newduties: dict[PumpNames,int]):
        if self._controller_context:
            for pmp in newduties.keys():
                self._controller_context.notify_event(CEvents.AUTO_DUTY_SET,pmp,newduties[pmp])
    
    def close(self):
        if self._pump_context:
            self._pump_context.stop_pid()
    
    @property
    def has_settings(self) -> bool:
        return True
    
    def open_settings(self):
        pass
        
class LevelProcess(BaseProcess):
    @property
    def name(self) -> str:
        return "Level Sensor"
    
    def start(self):
        if self._controller_context:
            on_failure = lambda: self._controller_context.notify_event(CEvents.PROCESS_CLOSED,ProcessName.LEVEL)
            on_success = self.__send_level_config
            box = self._controller_context._create_alert(LevelSelect,on_success=on_success,on_failure=on_failure)
    
    def __send_level_config(self,device_number: int, r1: tuple[int,int,int,int], r2: tuple[int,int,int,int], h: tuple[int,int,int,int], ref_vol: float):
        if self._pump_context and self._controller_context:

            (state_running,state_levels) = self._pump_context.start_levels(device_number,r1,r2,h,ref_vol)
            
            if len(self._removal_callbacks) == 0:
                self._removal_callbacks.append(self._controller_context._add_state(state_running,self.__handle_running))
    
    def __handle_running(self,isrunning: bool):
        if self._controller_context:
            if isrunning:
                self._controller_context.notify_event(CEvents.PROCESS_STARTED,ProcessName.LEVEL)
            else:
                self._controller_context.notify_event(CEvents.PROCESS_CLOSED,ProcessName.LEVEL)

    def close(self):
        if self._pump_context:
            self._pump_context.stop_levels()
    
    @property
    def has_settings(self) -> bool:
        return False
    
    def open_settings(self):
        pass

class DataProcess(BaseProcess):
    @property
    def name(self) -> str:
        return "Data Logging"
    def start(self):
        if self._pump_context and self._controller_context:
            self._pump_context.logging_state.set_value(True)
            self._controller_context.notify_event(CEvents.PROCESS_STARTED,ProcessName.DATA)
    
    def close(self):
        if self._pump_context and self._controller_context:
            self._pump_context.logging_state.set_value(False)
            self._controller_context.notify_event(CEvents.PROCESS_CLOSED,ProcessName.DATA)

    @property
    def has_settings(self) -> bool:
        return True
    
    def open_settings(self):
        if self._controller_context:
            on_success = self.__on_settings_modified
            on_failure = lambda: self._controller_context.notify_event(CEvents.CLOSE_SETTINGS,ProcessName.DATA)
            self._controller_context._create_alert(DataSettingsBox,on_success=on_success,on_failure=on_failure)

    def __on_settings_modified(self,modifications: dict[str,Any]):
        if self._controller_context:
            self._controller_context.notify_event(CEvents.SETTINGS_CONFIRMED,modifications)
            self._controller_context.notify_event(CEvents.CLOSE_SETTINGS,ProcessName.DATA)
        
class ProcessName(Enum):
    LEVEL = LevelProcess
    """Process that reads the electrolyte reservoir levels"""
    DATA = DataProcess
    """Process that writes duties and levels to respective csv files during operation"""
    PID = PIDProcess
    """Process that runs the PID duty control feedback loop"""

