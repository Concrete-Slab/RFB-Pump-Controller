from enum import Enum
from typing import Literal


class PSEvents(Enum):
    NEW_PORTS = Literal["new_ports"]
    """Signals that the controller has found new serial ports. Callbacks to take list of new ports and their descriptions as argument"""
    NEW_INTERFACES = Literal["new_interfaces"]
    """Signals that the controller has found new interfaces. Callbacks to take list of new interfaces as argument"""
    ERROR = Literal["error"]
    """Controller has encountered an error. Callbacks to take error as argument"""
    UPDATE_INTERFACES = Literal["update_interfaces"]
    """Signals that the UI has requested new interfaces"""
    UPDATE_PORTS = Literal["update_ports"]
    """Signals that the UI has requested new serial ports"""
    SERIAL_CONFIG = Literal["serial_config"]
    """Signals the choice of interface and port. Callbacks to take interface, port and any other *args and **kwargs as arguments"""
    
    REMOVE_ROOT_CALLBACKS = Literal["remove_root_callbacks"]
    """Signals to remove all event and state callbacks from the root polling loop"""


class CEvents(Enum):
    ERROR = Literal["error"]
    """Signals controller has encountered an error. Callbacks to take error as argument"""
    READY = Literal["ready"]
    """Signals pump is ready for user actions"""
    AUTO_DUTY_SET = Literal["auto_duty_set"]
    """Controller has set a pump duty. Callbacks to take the pump identifier and new duty as arguments"""
    AUTO_SPEED_SET = Literal["auto_speed_set"]
    """Controller has set a pump speed. Callbacks to take the pump identifier and the new speed as arguments"""
    MANUAL_DUTY_SET = Literal["manual_duty_set"]
    """User has set a pump duty. Callbacks to take the pump identifier and new duty as arguments"""
    PROCESS_STARTED = Literal["process_started"]
    """A specified process has finished initialising and has started. Callbacks to take ProcessName as an argument"""
    PROCESS_CLOSED = Literal["process_closed"]
    """A specified process has closed and cleaned up resources. Callbacks to take ProcessName as an argument"""
    START_PROCESS = Literal["start_process"]
    """Signals for a specified process to start. Callbacks to take ProcessName as an argument"""
    CLOSE_PROCESS = Literal["close_process"]
    """Signals for a specified process to close. Callbacks to take ProcessName as an argument"""
    LEVEL_DATA_ACQUIRED = Literal["level_data_acquired"]
    """Signals that the required parameters for the level sensor have been acquired. Callbacks to take device_number, r1, r2, h, ref_vol, and init_vol as arguments"""
    

class ProcessName(Enum):
    PID = Literal["pid"]
    """Process that runs the PID duty control feedback loop"""
    LEVEL = Literal["level"]
    """Process that reads the electrolyte reservoir levels"""
    DATA = Literal["data"]
    """Process that writes duties and levels to respective csv files during operation"""



