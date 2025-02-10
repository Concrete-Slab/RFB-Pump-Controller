from enum import Enum
from typing import Literal

class MEvents(Enum):
    UPDATE_MICROCONTROLLERS = "update_microcontrollers"
    """Signals that the UI has requested a new microcontroller list"""
    NEW_MICROCONTROLLERS = "new_microcontrollers"
    """Signals that the controller has found new microcontrollers. Callbacks to take list of device names (str) as argument"""
    SEND_PREMADE = "send_premade"
    """Signals that the user wishes to upload premade code to the microcontroller. Callbacks to take code filepath (Path) and number of pumps (int) as arguments"""
    BAD_DEVICE = "bad_device"
    """Signals that upload to device has failed. Callbacks to take error message (str) as argument"""
    BAD_FILE = "bad_file"
    """Signals that the microcontroller code does not exist or is in the wrong format. Arguments to take error message (str) as argument"""

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
    OPEN_ROI_SELECTION = Literal["open_roi_selection"]
    """Signals that the user wishes to open the ROI selection screen"""
    CLOSE_ROI_SELECTION = Literal["level_data_acquired"]
    """Signals that the required parameters for the level sensor have been acquired. Callbacks to take device_number, r1, r2, h, ref_vol, and init_vol as arguments"""
    OPEN_SETTINGS = Literal["open_settings"]
    """User wishes to open the settings for a process. Callbacks to take ProcessName as argument"""
    CLOSE_SETTINGS = Literal["close_settings"]
    """User wishes to close the settings window for a process. Callbacks to take ProcessName as argument"""
    SETTINGS_MODIFIED = Literal["settings_confirmed"]
    """User has confirmed settings. Callbacks to take a dictionary containing the modified settings"""
    STOP_ALL = Literal["stop_all"]
    """Stop all pumps"""
    
    

class ProcessName(Enum):
    LEVEL = "Level"
    """Process that reads the electrolyte reservoir levels"""
    DATA = "Data Logging"
    """Process that writes duties and levels to respective csv files during operation"""
    PID = "PID"
    """Process that runs the PID duty control feedback loop"""
