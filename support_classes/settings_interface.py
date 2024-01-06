from enum import Enum
import json
from typing import Any
from pathlib import Path

class PumpNames(Enum):
    A = "a"
    B = "b"
    C = "c"
    D = "d"
    E = "e"
    F = "f"

class CaptureBackend(Enum):
    ANY = "Default"
    PYGAME_WINDOWS_NATIVE = "Microsoft Media Foundation (pygame)"
    PYGAME_LINUX_NATIVE = "Video for Linux (pygame)"
    PYGAME_VIDEOCAPTURE = "VideoCapture (pygame)"
    CV2_MSMF = "Microsoft Media Foundation (OpenCV)"
    CV2_V4L2 = "Video for Linux (OpenCV)"
    CV2_VFW = "Video for Windows (OpenCV)"
    CV2_WINRT = "Windows Runtime (MSMF via OpenCV)"
    CV2_DSHOW = "DirectShow (OpenCV)"
    CV2_QT = "QuickTime (OpenCV)"

CV2_BACKENDS = set([CaptureBackend.CV2_MSMF,CaptureBackend.CV2_V4L2,CaptureBackend.CV2_VFW,CaptureBackend.CV2_WINRT,CaptureBackend.CV2_QT])

SETTINGS_FILENAME = "settings.json"

class Settings(Enum):
    LOG_LEVELS = "log_levels"
    LOG_PID = "log_pid"
    LOG_SPEEDS = "log_speeds"
    LEVEL_DIRECTORY = "level_directory"
    PID_DIRECTORY = "pid_directory"
    SPEED_DIRECTORY = "speed_directory"
    ANOLYTE_PUMP = "anolyte_pump"
    CATHOLYTE_PUMP = "catholyte_pump"
    ANOLYTE_REFILL_PUMP = "anolyte_refill_pump"
    CATHOLYTE_REFILL_PUMP = "catholyte_refill_pump"
    REFILL_TIME = "refill_time"
    """Seconds for which the main reservoirs are topped up after a refill event is triggered"""
    REFILL_DUTY = "refill_duty"
    """Duty applied to the refill pump when PID controller detects low levels"""
    REFILL_PERCENTAGE_TRIGGER = "refill_percentage_trigger"
    """Percent loss of solvent that will trigger the refill system"""
    BASE_CONTROL_DUTY = "base_control_duty"
    """Duty applied to pumps when controller input is zero"""
    VIDEO_DEVICE = "video_device"
    """Integer that selects the video device to be used with cv2"""
    AUTO_EXPOSURE = "auto_exposure"
    """Sets automatic camera exposure on or off"""
    EXPOSURE_TIME = "exposure_time"
    """Sets the exposure time for the camera if auto exposure is off"""
    SENSING_PERIOD = "sensing_period"
    """Sets the time in seconds between images of the reservoirs"""
    AVERAGE_WINDOW_WIDTH = "average_window_width"
    """Sets the number of seconds over which level readings are averaged"""
    LEVEL_STABILISATION_PERIOD = "level_stabilisation_period"
    """Sets the time before which the initial volume of the tanks is recorded"""
    CAMERA_INTERFACE_MODULE = "camera_interface_module"
    """Python module to be used for the camera interface"""
    CAMERA_BACKEND = "camera_backend"

__thispath = Path().absolute().parent
DEFAULT_SETTINGS: dict[Settings, Any] = {
    Settings.LOG_LEVELS: True,
    Settings.LOG_PID: True,
    Settings.LOG_SPEEDS: False,
    Settings.LEVEL_DIRECTORY: (__thispath / "pumps/levels").as_posix(),
    Settings.PID_DIRECTORY: (__thispath / "pumps/duties").as_posix(),
    Settings.SPEED_DIRECTORY: (__thispath / "pumps/speeds").as_posix(),
    Settings.VIDEO_DEVICE: 0,
    Settings.ANOLYTE_PUMP: None,
    Settings.CATHOLYTE_PUMP: None,
    Settings.ANOLYTE_REFILL_PUMP: None,
    Settings.CATHOLYTE_REFILL_PUMP: None,
    Settings.REFILL_TIME: 10,
    Settings.REFILL_DUTY: 10,
    Settings.REFILL_PERCENTAGE_TRIGGER: 20,
    Settings.BASE_CONTROL_DUTY: 92,
    Settings.AUTO_EXPOSURE: True,
    Settings.EXPOSURE_TIME: 1000,
    Settings.SENSING_PERIOD: 5.0,
    Settings.AVERAGE_WINDOW_WIDTH: 18*60.0,
    Settings.LEVEL_STABILISATION_PERIOD: 120.0,
    Settings.CAMERA_INTERFACE_MODULE: "OpenCV",
    Settings.CAMERA_BACKEND: CaptureBackend.ANY
}

PID_SETTINGS = set([Settings.ANOLYTE_PUMP,Settings.CATHOLYTE_PUMP,Settings.ANOLYTE_REFILL_PUMP,Settings.CATHOLYTE_REFILL_PUMP,Settings.BASE_CONTROL_DUTY,Settings.REFILL_TIME,Settings.REFILL_DUTY,Settings.REFILL_PERCENTAGE_TRIGGER])
LOGGING_SETTINGS = set([Settings.LOG_LEVELS,Settings.LOG_PID,Settings.LOG_SPEEDS,Settings.LEVEL_DIRECTORY,Settings.PID_DIRECTORY,Settings.SPEED_DIRECTORY])
PID_PUMPS = set([Settings.ANOLYTE_PUMP,Settings.CATHOLYTE_PUMP,Settings.ANOLYTE_REFILL_PUMP,Settings.CATHOLYTE_REFILL_PUMP])
LOG_DIRECTORIES = set([Settings.LEVEL_DIRECTORY,Settings.PID_DIRECTORY,Settings.SPEED_DIRECTORY])
CAMERA_SETTINGS = set([Settings.CAMERA_BACKEND,Settings.CAMERA_INTERFACE_MODULE,Settings.VIDEO_DEVICE,Settings.AUTO_EXPOSURE,Settings.EXPOSURE_TIME])
CV_SETTINGS = set([Settings.LEVEL_STABILISATION_PERIOD,Settings.SENSING_PERIOD,Settings.AVERAGE_WINDOW_WIDTH])
LEVEL_SETTINGS = set([*CAMERA_SETTINGS,*CV_SETTINGS])

def read_settings(*keys: Settings) -> dict[Settings,Any]:
    all_settings = __open_settings_filesafe()
    # use dictionary comprehension to return relevent subset of settings
    if len(keys) == 0:
        keys = DEFAULT_SETTINGS.keys()
    out: dict[Settings,Any] = {}
    for key in keys:
        # TODO fix possible key error in logic
        if key in all_settings.keys():
            out = {**out,key:all_settings[key]}
        elif key in DEFAULT_SETTINGS.keys():
            out = {**out,key:DEFAULT_SETTINGS[key]}
        # convert from str to pumpnames if setting involves a pump (and is not None)
        curr_value = out[key]
        out[key] = __cast_to_correct_type(key,curr_value)
    return out

def read_setting(setting: Settings):
    key_val = read_settings(setting)
    return key_val[setting]

def modify_settings(new_changes: dict[Settings,Any]) -> dict[Settings,Any]:
    # read all settings
    all_settings = read_settings()
    # make sure the input dictionary has correct types
    for nkey in new_changes.keys():
        new_changes[nkey] = __cast_to_correct_type(nkey,new_changes[nkey])

    modifications: dict[Settings,Any] = {}

    new_keys = set(new_changes.keys())
    common_keys = set([key for key in new_keys if key in all_settings.keys()])

    for key in common_keys:
        # find values that are modified from all_settings
        new_value = new_changes[key]
        
        if new_value!=all_settings[key]:
            modifications = {**modifications, key: __cast_to_correct_type(key,new_value)}
            # save the modified value to all_settings
            all_settings[key] = new_value

    final_settings = {str(key.value):all_settings[key] for key in all_settings.keys()}
    # convert from pumpnames to str
    for pmpsetting in PID_PUMPS:
        pmp = final_settings[pmpsetting.value]
        if isinstance(pmp,PumpNames):
            final_settings[pmpsetting.value] = pmp.value
    # convert from Path to str
    for pathsetting in LOG_DIRECTORIES:
        path = final_settings[pathsetting.value]
        if isinstance(path,Path):
            final_settings[pathsetting.value] = path.as_posix()
    # convert from CaptureBackend to str
    be = final_settings[Settings.CAMERA_BACKEND.value]
    if isinstance(be,CaptureBackend):
        final_settings[Settings.CAMERA_BACKEND.value] = be.value
    

    # write to file
    with open(SETTINGS_FILENAME,"w") as f:
        json.dump(final_settings,f)
    # return the modifications to settings
    return modifications

def __open_settings_filesafe() -> dict[Settings,Any]:
    try:
        with open(SETTINGS_FILENAME,"r") as f:
            settings_in = dict(json.load(f))
        #TODO change to just modifying indices instead of appending
        settings_out = {}
        for key in DEFAULT_SETTINGS.keys():
            if key.value in settings_in:
                settings_out = {**settings_out,key:settings_in[key.value]}
            else:
                settings_out = {**settings_out,key:DEFAULT_SETTINGS[key]}
    except:
        settings_out = DEFAULT_SETTINGS
    return settings_out

def __cast_to_correct_type(key,value):
    if key in PID_PUMPS:
        if value is not None:
            value = PumpNames(value)
    elif key in LOG_DIRECTORIES:
        if value is not None:
            value = Path(value)
        else:
            # if path is None (e.g. blank settings.json), then use the default path provided
            value = DEFAULT_SETTINGS[key]
    elif key == Settings.CAMERA_BACKEND:
        if value is not None:
            value = CaptureBackend(value)
        else:
            value = DEFAULT_SETTINGS[key]
    return value
