from enum import Enum
from support_classes import PumpNames, Settings
from dataclasses import dataclass
from typing import Any
from ui_root import event_group

class ProcessName(Enum):
    PID = "pid"
    """Process that runs the PID duty control feedback loop"""
    DATA = "data"
    """Process that writes duties and levels to respective csv files during operation"""
    LEVEL = "level"
    """Process that reads the electrolyte reservoir levels"""

@event_group
class CEvents:
    @dataclass
    class Error:
        """Signals controller has encountered an error. Callbacks to take error as argument"""
        err: BaseException
    class Ready:
        """Signals pump is ready for user actions"""
    @dataclass
    class AutoDutySet:
        """Controller has set a pump duty. Callbacks to take the pump identifier and new duty as arguments"""
        pump_id: PumpNames
        new_duty: int
    @dataclass
    class AutoSpeedSet:
        """Controller has set a pump speed. Callbacks to take the pump identifier and new speed as arguments"""
        pump_id: PumpNames
        new_speed: int
    @dataclass
    class ManualDutySet:
        """User has set a pump duty. Callbacks to take the pump identifier and new duty as arguments"""
        pump_id: PumpNames
        new_duty: int
    @dataclass
    class ProcessStarted:
        """A specified process has finished initialising and has started. Callbacks to take ProcessName as an argument"""
        process_name: ProcessName
    @dataclass
    class ProcessClosed:
        """A specified process has closed and cleaned up resources. Callbacks to take ProcessName as an argument"""
        process_name: ProcessName
    @dataclass
    class StartProcess:
        """Signals for a specified process to start. Callbacks to take ProcessName as an argument"""
        process_name: ProcessName
    @dataclass
    class CloseProcess:
        """Signals for a specified process to close. Callbacks to take ProcessName as an argument"""
        process_name: ProcessName
    class OpenROISelection:
        """Signals that the user wishes to open the ROI selection screen"""
    class CloseROISelection:
        """Signals that the required parameters for the level sensor have been acquired. Callbacks to take device_number, r1, r2, h, ref_vol, and init_vol as arguments"""
    @dataclass
    class OpenSettings:
        """User wishes to open the settings for a process. Callbacks to take ProcessName as argument"""
        process_name: ProcessName
    @dataclass
    class CloseSettings:
        """User wishes to close the settings window for a process. Callbacks to take ProcessName as argument"""
        process_name: ProcessName
    @dataclass
    class SettingsModified:
        """User has confirmed settings. Callbacks to take a dictionary containing the modified settings"""
        modifications: dict[Settings,Any]
    class StopAll:
        """Stop all pumps"""