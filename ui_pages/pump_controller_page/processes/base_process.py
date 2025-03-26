from abc import ABC, abstractmethod
from ui_root import UIController, AlertBox
from pump_control import Pump
from ui_pages.pump_controller_page.CONTROLLER_EVENTS import ProcessName, CEvents
from typing import Any, Protocol, Callable, TypeVar, runtime_checkable
from support_classes import Settings, SharedState

A = TypeVar("A")

@runtime_checkable
class AlertBoxConstructor(Protocol):
    def __call__(self, on_success:Callable[[A],None]|None = None, on_failure: Callable[[None],None]|None = None) -> AlertBox[A]: ...

class BaseProcess(ABC):

    def __init__(self,controller_context: UIController, pump_context: Pump):
        assert (isinstance(self.settings_constructor,AlertBoxConstructor) or self.settings_constructor is None)
        self._controller_context = controller_context
        self._pump_context = pump_context
        self._removal_callbacks = []

    @classmethod
    @abstractmethod
    def process_name(cls) -> ProcessName:
        """returns the *ProcessName* member associated with this process controller"""
        pass
    @property
    @abstractmethod
    def name(self) -> str:
        """returns the intended display name of the process"""
        pass
    @property
    @abstractmethod
    def settings_constructor(self) -> AlertBoxConstructor|None:
        """returns a function that follows the *AlertBoxConstructor* protocol. The function returned should take *on_success* and *on_failure* as optional parameters, and return an *AlertBox*"""
        pass
    @abstractmethod
    def start(self) -> None:
        """Start the process"""
        pass
    @abstractmethod
    def close(self) -> None:
        """Close the process"""
        pass

    def _monitor_running(self, running_state: SharedState[bool]):
        if len(self._removal_callbacks) == 0:
            self._removal_callbacks.append(self._controller_context._add_state(running_state,self._handle_running))

    def _handle_running(self,newstate: bool):
        if newstate:
            self._controller_context.notify_event(CEvents.ProcessStarted(self.process_name()))
        else:
            self._controller_context.notify_event(CEvents.ProcessClosed(self.process_name()))
    
    @property
    def has_settings(self) -> bool:
        return not self.settings_constructor is None
    
    def open_settings(self):
        if not self.settings_constructor:
            raise RuntimeError(f"Class {self.__class__.__name__} does not have an associated settings alert box")
        on_successful = self._on_settings_modified
        on_failure = lambda: self._controller_context.notify_event(CEvents.CloseSettings(self.process_name()))
        settings_box = self.settings_constructor(on_failure=on_failure,on_success=on_successful)
        self._controller_context._create_alert(settings_box)

    def _on_settings_modified(self, modifications: dict[Settings,Any]):
        self._controller_context.notify_event(CEvents.SettingsModified(modifications))
        self._controller_context.notify_event(CEvents.CloseSettings(self.process_name()))