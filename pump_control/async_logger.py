from typing import Any, Iterable
from support_classes import SharedState, Settings, Generator, LOGGING_SETTINGS, DEFAULT_SETTINGS, PumpNames, PumpConfig, GeneratorException, PID_PUMPS
from .async_levelsensor import LevelOutput
from .async_pidcontrol import Duties
from .async_serialreader import SpeedReading
import numpy as np
from pathlib import Path
import os
import time
from datetime import datetime
from PIL import Image
import csv
import asyncio
from enum import Enum

_LOG_DIRECTORIES = set([Settings.LEVEL_DIRECTORY,Settings.PID_DIRECTORY,Settings.SPEED_DIRECTORY,Settings.IMAGE_DIRECTORY])
_LOG_STATES = set([Settings.LOG_LEVELS,Settings.LOG_PID,Settings.LOG_SPEEDS,Settings.LOG_IMAGES])
_DEFAULT_PUMP_MAP = {setting : DEFAULT_SETTINGS[setting] for setting in PID_PUMPS}
_DUTY_HEADER_MAP = {Settings.ANOLYTE_PUMP: "Anolyte Pump Duty",
                    Settings.CATHOLYTE_PUMP: "Catholyte Pump Duty",
                    Settings.ANOLYTE_REFILL_PUMP: "Anolyte Refill Pump Duty",
                    Settings.CATHOLYTE_REFILL_PUMP: "Catholyte Refill Pump Duty",
                    }

class _DataType(Enum):
    IMAGE = "image"
    DUTIES = "duties"
    SPEEDS = "speeds"
    LEVELS = "levels"
    @classmethod
    def from_setting(cls,setting:Settings) ->"_DataType":
        if setting in (Settings.LOG_IMAGES,Settings.IMAGE_DIRECTORY):
            return _DataType.IMAGE
        elif setting in (Settings.LOG_LEVELS,Settings.LEVEL_DIRECTORY):
            return _DataType.LEVELS
        elif setting in (Settings.LOG_PID,Settings.PID_DIRECTORY):
            return _DataType.DUTIES
        elif setting in (Settings.LOG_SPEEDS,Settings.SPEED_DIRECTORY):
            return _DataType.SPEEDS
        else:
            raise NotImplementedError("Unknown Setting: "+setting.value)




class DataLogger(Generator[None]):

    def __init__(
            self, 
            speed_state: SharedState[SpeedReading],
            duty_state: SharedState[Duties],
            level_state: SharedState[LevelOutput],
            img_dir: Path = DEFAULT_SETTINGS[Settings.IMAGE_DIRECTORY],
            spd_dir: Path = DEFAULT_SETTINGS[Settings.SPEED_DIRECTORY],
            dty_dir: Path = DEFAULT_SETTINGS[Settings.PID_DIRECTORY],
            lvl_dir: Path = DEFAULT_SETTINGS[Settings.LEVEL_DIRECTORY],
            log_imgs: bool = DEFAULT_SETTINGS[Settings.LOG_IMAGES],
            log_spds: bool = DEFAULT_SETTINGS[Settings.LOG_SPEEDS],
            log_dtys: bool = DEFAULT_SETTINGS[Settings.LOG_PID],
            log_lvls: bool = DEFAULT_SETTINGS[Settings.LOG_LEVELS],
            pump_map: dict[Settings,PumpNames|None] = _DEFAULT_PUMP_MAP,
            data_logging_period: float = DEFAULT_SETTINGS[Settings.LOGGING_PERIOD],
            image_logging_period: float = DEFAULT_SETTINGS[Settings.IMAGE_SAVE_PERIOD]
        ) -> None:
        super().__init__()
        self.speed_state = speed_state
        self.duty_state = duty_state
        self.level_state = level_state
        self.dirs: dict[_DataType,Path] = {
            _DataType.IMAGE: img_dir,
            _DataType.SPEEDS: spd_dir,
            _DataType.DUTIES: dty_dir,
            _DataType.LEVELS: lvl_dir
        }
        self.logged: dict[_DataType,bool] = {
            _DataType.IMAGE: log_imgs,
            _DataType.SPEEDS: log_spds,
            _DataType.DUTIES: log_dtys,
            _DataType.LEVELS: log_lvls
        }
        self.period = data_logging_period
        self.img_period = image_logging_period
        self.__base_filename: str = ""
        self.img_timer = 0.0
        self.headers = {}
        self.pump_map = pump_map

    def set_parameters(self,settings: dict[Settings,Any]):
        logging_settings = {key:settings[key] for key in settings if key in LOGGING_SETTINGS}
        if len(logging_settings)>0:
            self.stop()
        for key in logging_settings.keys():
            try:
                dt_key = _DataType.from_setting(key)
                if key in _LOG_STATES:
                    self.logged[dt_key] = settings[key]
                elif key in _LOG_DIRECTORIES:
                    self.dirs[dt_key] = settings[key]
            except NotImplementedError:
                if key == Settings.LOGGING_PERIOD:
                    self.period = settings[key]
                elif key == Settings.IMAGE_SAVE_PERIOD:
                    self.img_period = settings[key]
        pump_settings = {key:settings[key] for key in settings if key in _DUTY_HEADER_MAP.keys()}
        for key in pump_settings.keys():
            self.pump_map[key] = pump_settings[key]

    def teardown(self):
        pass

    def _get_path(self,dtype:_DataType) -> Path:
        if self.__base_filename is None:
            return None
        directory = self.dirs[dtype]
        filename = ""
        match dtype:
            case _DataType.DUTIES:
                filename = "duties_"+self.__base_filename
            case _DataType.SPEEDS:
                filename = "speeds_"+self.__base_filename
            case _DataType.LEVELS:
                filename = "levels_"+self.__base_filename
            case _DataType.IMAGE:
                filename = "img_"+str(time.time())+".png"
            case _:
                raise GeneratorException("Unknown datatype key: "+str(dtype))
        return directory / filename
    
    async def _setup(self):
        self.__base_filename = str(datetime.now().strftime("%Y-%m-%d %H-%M-%S"))+".csv"
        
        _HEADERS: dict[_DataType,list[str]] = {
            _DataType.LEVELS: ["Anolyte Level Avg (mL)", "Catholyte Avg (mL)","Avg Difference (mL)","Total Change in Electrolyte Level (mL)"],
            _DataType.SPEEDS: [f"Pump {str(pmp.value).upper()} (RPM)" for pmp in PumpConfig().pumps],
            _DataType.DUTIES:  [_DUTY_HEADER_MAP[key] for key in self.pump_map if self.pump_map[key] is not None] # these are the headers for the duty logs. We only need the ones that the PID process will be using (therefore a non-None pump in self.pump_map)
        }

        self.headers = {key: ["Elapsed Time (s)",*_HEADERS[key]] for key in _HEADERS.keys()}

        self.img_timer = time.time()

        # make directories if they do not exist
        for dtype,dirpath in self.dirs.items():
            if not os.path.isdir(dirpath) and self.logged[dtype]:
                os.makedirs(dirpath)

        for dtype in [key for key in self.headers.keys() if self.logged[key]]:
            with open(self._get_path(dtype),"w",newline="") as f:
                writer = csv.writer(f)
                writer.writerow(self.headers[dtype])

        self.__initial_timestamp = time.time()
        await asyncio.sleep(0.1)

    def _get_role_from_pmp(self,pmp: PumpNames|None):
        if pmp is None:
            raise GeneratorException("Nonetype pump has been assigned a duty - cannot save duties")
        valid_keys = [key for key in self.pump_map.keys() if self.pump_map[key] == pmp]
        if len(valid_keys)!=1:
            raise GeneratorException(f"Pump {pmp.value} has {len(valid_keys)} PID roles when it should only have 1 - cannot save duties")
        return valid_keys[0]

    async def _loop(self) -> None:
        perftimer = time.time()

        duties = self.duty_state.force_value()
        ordered_duties_list = None
        if duties is not None:
            ordered_duties_list = [0]*len(duties)
            # go through each pump in the new duties:
            for pmp in duties.keys():
                # find the role of the pump in the PID scheme
                pmp_role = self._get_role_from_pmp(pmp)
                # find the header title for that setting
                header = _DUTY_HEADER_MAP[pmp_role]
                # find the column number of that heading (-1 to remove elapsed time)
                column = self.headers[_DataType.DUTIES].index(header)-1
                # put the duty in that column
                ordered_duties_list[column] = duties[pmp]
            # valid_duties = list(duties.values())
            # zero_padding = [0]*max(len(self.headers[_DataType.DUTIES])-1-len(valid_duties), 0)
            # duties = [*valid_duties,*zero_padding]
        lvl_data = self.level_state.force_value()
        speeds = self.speed_state.force_value()
        if speeds is not None:
            speeds = [spd for spd in speeds.values()]
        t = time.time()-self.__initial_timestamp
        
        self._save_one(t,_DataType.DUTIES,ordered_duties_list)
        self._save_one(t,_DataType.SPEEDS,speeds)

        if lvl_data is not None:
            self._save_one(t,_DataType.LEVELS,lvl_data.levels)
            self._maybe_save_image(lvl_data.original_image)

        log_time = time.time() - perftimer
        wait_time = self.period-log_time
        # await asyncio.sleep(wait_time)
        await self._wait_while_checking(wait_time,check_interval=0.5)
    
    def _save_one(self,elapsed_seconds: float, dtype: _DataType ,data:Iterable[Any]|None):
        if data is None:
            return
        if self.logged[dtype]:
            str_data = [str(elapsed_seconds),*list(map(str,data))]
            try:
                with open(self._get_path(dtype),"a+",newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(str_data)
            except (PermissionError,FileNotFoundError,IOError) as e:
                raise GeneratorException(str(e))

    def _maybe_save_image(self,image: np.ndarray|None):
        t = time.time()
        time_since_last_image = t - self.img_timer
        if self.logged[_DataType.IMAGE] and time_since_last_image>self.img_period and image is not None:
            Image.fromarray(image).save(self._get_path(_DataType.IMAGE))
            self.img_timer = t
