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

class ImageFilterType(Enum):
    OTSU = "otsu"
    LINKNET = "linknet"
    NONE = "none (no fluid detection)"

CV2_BACKENDS = set([CaptureBackend.CV2_MSMF,CaptureBackend.CV2_V4L2,CaptureBackend.CV2_VFW,CaptureBackend.CV2_WINRT,CaptureBackend.CV2_QT,CaptureBackend.CV2_DSHOW])

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
    PID_REFILL_COOLDOWN = "pid_refill_cooldown"
    """Time after each refill in which the PID controller will not perform any more refills"""
    IMAGE_RESCALE_FACTOR = "image_rescale_factor"
    """Factor by which images taken by a Capture will be scaled by (preserving aspect ratio)"""
    RECENT_SERIAL_PORT = "recent_serial_port"
    """Most recently used serial port"""
    RECENT_SERIAL_INTERFACE = "recent_serial_interface"
    """Most recently used serial interface"""
    PROPORTIONAL_GAIN = "proportional_gain"
    """PID controller proportional gain term"""
    INTEGRAL_GAIN = "integral_gain"
    """PID controller integral gain term"""
    DERIVATIVE_GAIN = "derivative_gain"
    """PID controller derivative gain"""
    IMAGE_SAVE_PERIOD = "image_save_period"
    """Period between saving images taken by level sensor"""
    IMAGE_DIRECTORY = "image_directory"
    """Full path to directory where images are saved"""
    LOG_IMAGES = "log_images"
    """True if images from level sensor are to be saved"""
    LOGGING_PERIOD = "logging_period"
    """Period between rows in logger csv"""
    IMAGE_FILTER = "image_filter"
    """The algorithm used to filter the level from fluid images"""

__thispath = Path().absolute().parent
DEFAULT_SETTINGS: dict[Settings, Any] = {
    Settings.LOG_LEVELS: True,
    Settings.LOG_PID: True,
    Settings.LOG_SPEEDS: False,
    Settings.LEVEL_DIRECTORY: (__thispath / "pumps/experiment_0/levels").as_posix(),
    Settings.PID_DIRECTORY: (__thispath / "pumps/experiment_0/duties").as_posix(),
    Settings.SPEED_DIRECTORY: (__thispath / "pumps/experiment_0/speeds").as_posix(),
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
    Settings.CAMERA_BACKEND: CaptureBackend.ANY,
    Settings.PID_REFILL_COOLDOWN: 18*60.0,
    Settings.IMAGE_RESCALE_FACTOR: 1.0,
    Settings.RECENT_SERIAL_PORT: None,
    Settings.RECENT_SERIAL_INTERFACE: None,
    Settings.PROPORTIONAL_GAIN: 100,
    Settings.INTEGRAL_GAIN: 0.005,
    Settings.DERIVATIVE_GAIN: 0,
    Settings.IMAGE_SAVE_PERIOD: 60,
    Settings.IMAGE_DIRECTORY: (__thispath/"pumps/experiment_0/images").as_posix(),
    Settings.LOG_IMAGES: False,
    Settings.LOGGING_PERIOD: 5.0,
    Settings.IMAGE_FILTER: ImageFilterType.LINKNET,
}

_LOG_DIRECTORIES = set([Settings.LEVEL_DIRECTORY,Settings.PID_DIRECTORY,Settings.SPEED_DIRECTORY,Settings.IMAGE_DIRECTORY])
_LOG_STATES = set([Settings.LOG_LEVELS,Settings.LOG_PID,Settings.LOG_SPEEDS,Settings.LOG_IMAGES])
LOGGING_SETTINGS = set([Settings.LOGGING_PERIOD,Settings.IMAGE_SAVE_PERIOD,*_LOG_DIRECTORIES,*_LOG_STATES])
PID_PUMPS = set([Settings.ANOLYTE_PUMP,Settings.CATHOLYTE_PUMP,Settings.ANOLYTE_REFILL_PUMP,Settings.CATHOLYTE_REFILL_PUMP])
PID_SETTINGS = set([*PID_PUMPS,Settings.BASE_CONTROL_DUTY,Settings.REFILL_TIME,Settings.REFILL_DUTY,Settings.REFILL_PERCENTAGE_TRIGGER,Settings.PID_REFILL_COOLDOWN,Settings.PROPORTIONAL_GAIN,Settings.INTEGRAL_GAIN,Settings.DERIVATIVE_GAIN])
CAMERA_SETTINGS = set([Settings.IMAGE_SAVE_PERIOD,Settings.IMAGE_RESCALE_FACTOR,Settings.CAMERA_BACKEND,Settings.CAMERA_INTERFACE_MODULE,Settings.VIDEO_DEVICE,Settings.AUTO_EXPOSURE,Settings.EXPOSURE_TIME])
CV_SETTINGS = set([Settings.LEVEL_STABILISATION_PERIOD,Settings.SENSING_PERIOD,Settings.AVERAGE_WINDOW_WIDTH])
LEVEL_SETTINGS = set([*CAMERA_SETTINGS,*CV_SETTINGS,Settings.LOG_IMAGES,Settings.IMAGE_DIRECTORY,Settings.IMAGE_SAVE_PERIOD])

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
    for pathsetting in _LOG_DIRECTORIES:
        path = final_settings[pathsetting.value]
        if isinstance(path,Path):
            final_settings[pathsetting.value] = path.as_posix()
    # convert from CaptureBackend to str
    be = final_settings[Settings.CAMERA_BACKEND.value]
    if isinstance(be,CaptureBackend):
        final_settings[Settings.CAMERA_BACKEND.value] = be.value
    # convert from ImageFilterType to str
    ift = final_settings[Settings.IMAGE_FILTER.value]
    if isinstance(ift,ImageFilterType):
        final_settings[Settings.IMAGE_FILTER.value] = ift.value
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
    elif key in _LOG_DIRECTORIES:
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
    elif key == Settings.IMAGE_FILTER:
        if value is not None:
            value = ImageFilterType(value)
        else:
            value = DEFAULT_SETTINGS[key]
    return value
