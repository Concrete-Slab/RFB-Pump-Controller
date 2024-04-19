from abc import ABC,abstractmethod
from .UIController import UIController
from pump_control import Pump
from support_classes import PumpNames, Settings
from enum import Enum
from .PAGE_EVENTS import CEvents
from .toplevel_boxes import LevelSelect,DataSettingsBox,PIDSettingsBox,LevelSettingsBox
from typing import Any, Callable


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
    
    def remove_context(self):
        self._controller_context = None
        self._pump_context = None

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
        if self._controller_context:
            on_failure = lambda: self._controller_context.notify_event(CEvents.CLOSE_SETTINGS,ProcessName.PID)
            on_success = self.__on_settings_modified
            self._controller_context._create_alert(PIDSettingsBox,on_success=on_success,on_failure=on_failure)
    
    def __on_settings_modified(self,modifications: dict[Settings,Any]):
        if self._controller_context:
            self._controller_context.notify_event(CEvents.SETTINGS_MODIFIED,modifications)
            self._controller_context.notify_event(CEvents.CLOSE_SETTINGS,ProcessName.PID)
    
class LevelProcess(BaseProcess):

    def __init__(self, controller_context: UIController | None = None, pump_context: Pump | None = None):
        super().__init__(controller_context, pump_context)
        self.level_data: _LevelData|None = None

    @property
    def name(self) -> str:
        return "Level Sensor"
    
    def start(self):
        if self._controller_context:
            # on_failure = lambda: self._controller_context.notify_event(CEvents.PROCESS_CLOSED,ProcessName.LEVEL)
            # on_success = self.__send_level_config
            # box = self._controller_context._create_alert(LevelSelect,on_success=on_success,on_failure=on_failure)
            if self.level_data is None:
                self.request_ROIs(after_success=self.__send_level_config,after_failure= lambda: self._controller_context.notify_event(CEvents.PROCESS_CLOSED,ProcessName.LEVEL))
            else:
                self.__send_level_config()

    def request_ROIs(self,after_success: Callable[[None],None]|None = None,after_failure: Callable[[None],None] = None):
        if self._controller_context:
            def on_failure():
                self._controller_context.notify_event(CEvents.CLOSE_ROI_SELECTION)
                if after_failure:
                    after_failure()
            def on_success(r1: Rect, r2: Rect, h: Rect, ref_vol: float):
                self.level_data = _LevelData(r1,r2,h,ref_vol)
                self._controller_context.notify_event(CEvents.CLOSE_ROI_SELECTION)
                if after_success:
                    after_success()
            box = self._controller_context._create_alert(LevelSelect,on_success=on_success,on_failure=on_failure)

    def __send_level_config(self):
        if self._pump_context and self._controller_context and self.level_data:

            (state_running,state_levels) = self._pump_context.start_levels(*self.level_data.as_tuple())
            
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
        return True
    
    def open_settings(self):
        if self._controller_context:
            on_success = self.__on_settings_modified
            on_failure = lambda: self._controller_context.notify_event(CEvents.CLOSE_SETTINGS,ProcessName.LEVEL)
            box = self._controller_context._create_alert(LevelSettingsBox,on_failure=on_failure,on_success=on_success)

    def __on_settings_modified(self, modifications: dict[Settings,Any]):
        if self._controller_context:
            self._controller_context.notify_event(CEvents.SETTINGS_MODIFIED,modifications)
            self._controller_context.notify_event(CEvents.CLOSE_SETTINGS,ProcessName.LEVEL)

Rect = tuple[int,int,int,int]
class _LevelData:
    def __init__(self,r1: Rect, r2: Rect, h: Rect, ref_vol: float):
        self.r1 = r1
        self.r2 = r2
        self.h = h
        self.ref_vol = ref_vol
    def as_tuple(self) -> tuple[Rect,Rect,Rect,float]:
        return (self.r1,self.r2,self.h,self.ref_vol)

class DataProcess(BaseProcess):
    @property
    def name(self) -> str:
        return "Data Logging"
    def start(self):
        if self._pump_context and self._controller_context:
            state_running = self._pump_context.start_logging()
            if len(self._removal_callbacks) == 0:
                self._removal_callbacks.append(self._controller_context._add_state(state_running,self.__handle_running))
    
    def close(self):
        if self._pump_context and self._controller_context:
            self._pump_context.stop_logging()

    def __handle_running(self,newstate: bool):
        if self._controller_context:
            if newstate:
                self._controller_context.notify_event(CEvents.PROCESS_STARTED,ProcessName.DATA)
            else:
                self._controller_context.notify_event(CEvents.PROCESS_CLOSED,ProcessName.DATA)
        

    @property
    def has_settings(self) -> bool:
        return True
    
    def open_settings(self):
        if self._controller_context:
            on_success = self.__on_settings_modified
            on_failure = lambda: self._controller_context.notify_event(CEvents.CLOSE_SETTINGS,ProcessName.DATA)
            self._controller_context._create_alert(DataSettingsBox,on_success=on_success,on_failure=on_failure)

    def __on_settings_modified(self,modifications: dict[Settings,Any]):
        if self._controller_context:
            self._controller_context.notify_event(CEvents.SETTINGS_MODIFIED,modifications)
            self._controller_context.notify_event(CEvents.CLOSE_SETTINGS,ProcessName.DATA)
        
class ProcessName(Enum):
    PID = PIDProcess.get_instance()
    """Process that runs the PID duty control feedback loop"""
    DATA = DataProcess.get_instance()
    """Process that writes duties and levels to respective csv files during operation"""
    LEVEL = LevelProcess.get_instance()
    """Process that reads the electrolyte reservoir levels"""

