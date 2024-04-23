from typing import Any, Iterable
from support_classes import SharedState, Settings, Generator, LOGGING_SETTINGS, DEFAULT_SETTINGS, PumpNames, GeneratorException
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


_HEADERS: dict[_DataType,list[str]] = {
        _DataType.LEVELS: ["Anolyte Level Avg", "Catholyte Avg","Avg Difference","Total Change in Electrolyte Level"],
        _DataType.SPEEDS: [f"Pump {str(pmp.value).upper()}" for pmp in PumpNames],
        _DataType.DUTIES:  ["Anolyte Pump Duty", "Catholyte Pump Duty", "Anolyte Refill Pump Duty","Catholyte Refill Pump Duty"]
    }

class DataLogger(Generator[None]):

    headers = {key: ["Elapsed Time",*_HEADERS[key]] for key in _HEADERS.keys()}

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
            _DataType.SPEEDS: log_imgs,
            _DataType.SPEEDS: log_spds,
            _DataType.DUTIES: log_dtys,
            _DataType.LEVELS: log_lvls
        }
        self.period = data_logging_period
        self.img_period = image_logging_period
        self.__base_filename: str = ""
        self.img_timer = 0.0

    def set_parameters(self,settings: dict[Settings,Any]):
        settings = {key:settings[key] for key in settings if key in LOGGING_SETTINGS}
        if len(settings)>0:
            self.stop()
        for key in settings.keys():
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

    async def _loop(self) -> None:
        perftimer = time.time()

        duties = self.duty_state.force_value()
        lvl_data = self.level_state.force_value()
        speeds = self.speed_state.force_value()
        t = time.time()-self.__initial_timestamp
        
        self._save_one(t,_DataType.DUTIES,duties)
        self._save_one(t,_DataType.SPEEDS,speeds)

        if lvl_data is not None:
            self._save_one(t,_DataType.LEVELS,lvl_data.levels)
            self._maybe_save_image(lvl_data.original_image)

        wait_time = time.time() - perftimer
        await asyncio.sleep(wait_time)
    
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
        if time_since_last_image>self.img_period and image is not None:
            Image.fromarray(image).save(self._get_path(_DataType.IMAGE))
            self.img_timer = t
