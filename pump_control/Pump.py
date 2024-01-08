from typing import Any, Coroutine, Iterable
from serial_interface import GenericInterface, InterfaceException
from support_classes import AsyncRunner, Teardown, SharedState, GeneratorException, Settings, read_settings, PID_SETTINGS, PumpNames, CAMERA_SETTINGS, LEVEL_SETTINGS
from concurrent.futures import Future

from support_classes.camera_interface import Capture
from support_classes.settings_interface import read_setting
from .async_levelsensor import LevelSensor, LevelReading, Rect
from .async_pidcontrol import PIDRunner, Duties
from .async_serialreader import SerialReader, SpeedReading
import numpy as np
from abc import ABC
import copy

class PumpState(ABC):
    pass

class ReadyState(PumpState):
    def __init__(self) -> None:
        pass

class ActiveState(PumpState):
    def __init__(self,new_duties: dict[PumpNames, int]):
        self.auto_duties = new_duties

class ErrorState(PumpState):
    def __init__(self,error: BaseException) -> None:
        self.error = error

class ReadException(BaseException):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)

class PIDException(BaseException):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)

class LevelException(BaseException):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)

class Pump(AsyncRunner,Teardown):

    def __init__(self, serial_interface: GenericInterface, **kwargs) -> None:
        super().__init__()

        self.__serial_interface = serial_interface

        self.state: SharedState[PumpState] = SharedState[PumpState]()

        settings = read_settings()

        

        self.__log_levels: bool = settings[Settings.LOG_LEVELS]
        self.__log_pid: bool = settings[Settings.LOG_PID]
        self.__log_speeds: bool = settings[Settings.LOG_SPEEDS]

        anolyte_pump: PumpNames|None = settings[Settings.ANOLYTE_PUMP]
        catholyte_pump: PumpNames|None = settings[Settings.CATHOLYTE_PUMP]
        anolyte_refill_pump: PumpNames|None = settings[Settings.ANOLYTE_REFILL_PUMP]
        catholyte_refill_pump: PumpNames|None = settings[Settings.CATHOLYTE_REFILL_PUMP]
    
        self.logging_state: SharedState[bool] = SharedState[bool](False)

        self.__level_logging_state: SharedState[bool] = SharedState[bool](False)
        self.__pid_logging_state: SharedState[bool] = SharedState[bool](False)
        self.__polling_logging_state: SharedState[bool] = SharedState[bool](False)
        # create the PID and level sense objects. The PID object operates on the shared state and sensed_event from the level object
        # self.__level: LevelSensor = LevelSensor(logging_state=self.logging_state,rel_level_directory=rel_level_directory)
        # self.__level: LevelSensor = LevelSensor(logging_state=self.__level_logging_state,
        #                                         absolute_logging_path=settings[Settings.LEVEL_DIRECTORY],
        #                                         capture_device=Capture.from_settings(),
        #                                         sense_period=settings[Settings.SENSING_PERIOD],
        #                                         stabilisation_period=settings[Settings.LEVEL_STABILISATION_PERIOD],
        #                                         average_window_length=settings[Settings.AVERAGE_WINDOW_WIDTH])
        # self.__pid: PIDRunner = PIDRunner(self.__level.state,
        #                                   self.__serial_interface,
        #                                   self.__level.sensed_event,
        #                                   logging_state=self.__pid_logging_state,
        #                                   absolute_logging_directory=settings[Settings.PID_DIRECTORY],
        #                                   base_duty=settings[Settings.BASE_CONTROL_DUTY],
        #                                   refill_time = settings[Settings.REFILL_TIME],
        #                                   refill_duty = settings[Settings.REFILL_DUTY],
        #                                   refill_percentage= settings[Settings.REFILL_PERCENTAGE_TRIGGER],
        #                                   anolyte_pump = anolyte_pump,
        #                                   catholyte_pump=catholyte_pump,
        #                                   anolyte_refill_pump=anolyte_refill_pump,
        #                                   catholyte_refill_pump=catholyte_refill_pump
        #                                   )
        # self.__poller: SerialReader = SerialReader(self.__serial_interface,logging_directory=settings[Settings.SPEED_DIRECTORY],logging_state=self.__polling_logging_state)
        self.__level: LevelSensor = LevelSensor(logging_state=self.__level_logging_state)
        self.__pid: PIDRunner = PIDRunner(self.__level.state,
                                          self.__serial_interface,
                                          self.__level.sensed_event,
                                          logging_state=self.__pid_logging_state,
                                          )
        self.__poller: SerialReader = SerialReader(self.__serial_interface,
                                                   logging_state=self.__polling_logging_state)
        self.change_settings(settings)


    def initialise(self):
        def on_established(future: Future[None]):
            try:
                future.result()
                # Future does not have an error: assign ready state to queue
                self.state.set_value(ReadyState())
            except InterfaceException as e:
                # Future completed with error: Assign error state to queue and close loop
                self.state.set_value(ErrorState(e))
                self.stop_event_loop()
            except:
                self.state.set_value(ErrorState(BaseException("Unknown Error")))
                self.stop_event_loop()
        
        self.run_async(self.__serial_interface.establish(), callback = on_established)

    def start_polling(self) -> tuple[SharedState[bool],SharedState[SpeedReading]]:
        self.run_async(self.__poller.generate(), callback = self.__polling_check_error)
        return (self.__poller.is_running,self.__poller.state)

    def __polling_check_error(self,future: Future):
        try:
            future.result()
        except (InterfaceException) as ie:
            print("Pump detected an interface exception!")
            self.state.set_value(ErrorState(ie))
            self.teardown()
        except GeneratorException as ge:
            self.state.set_value(ReadException(str(ge)))
        finally:
            self.stop_pid()

    def stop_polling(self):
        self.__poller.stop()
        
    def start_pid(self) -> tuple[SharedState[bool],SharedState[Duties]]:
        self.run_async(self.__pid.generate(), callback = self.__pid_check_error)
        return (self.__pid.is_running, self.__pid.state)
    
    def __pid_check_error(self,future:Future):
        try:
            future.result()
        except (InterfaceException) as ie:
            self.state.set_value(ErrorState(ie))
            self.teardown()
        except GeneratorException as ge:
            self.state.set_value(PIDException(str(ge)))
        finally:
            self.stop_pid()

    def stop_pid(self):
        self.__pid.stop()

    def levels_ready(self):
        return self.__level.is_ready()

    def start_levels(self, rect1: Rect, rect2: Rect, rect_ref: Rect, vol_ref: float) -> tuple[SharedState[bool],SharedState[tuple[LevelReading,np.ndarray|None]]]:
        try:
            self.__level.set_vision_parameters(rect1, rect2, rect_ref, vol_ref)
        except ValueError as e:
            print(e)
            self.state.set_value(ErrorState(LevelException(str(e))))
        self.run_async(self.__level.generate(), callback = self.__levels_check_error)
        return (self.__level.is_running,self.__level.state)

    def __levels_check_error(self,future: Future):
        try:
            future.result()
        except InterfaceException as ie:
            self.state.set_value(ErrorState(ie))
            self.teardown()
        except GeneratorException as ge:
            self.state.set_value(ErrorState(LevelException(str(ge))))
        finally:
            self.stop_levels()

    def stop_levels(self):
        self.__level.stop()

    def manual_set_duty(self,identifier: PumpNames, new_duty: int):
        if is_duty(new_duty):
            pid_pumps = [pmp for pmp in self.__pid.get_pumps().values() if pmp is not None]
            if identifier in pid_pumps and self.__pid.is_running.value:
                self.stop_pid()
                state_dict: dict[PumpNames,int] = {}
                for pidpmp in pid_pumps:
                    if pidpmp is not None and pidpmp != identifier:
                        self.run_async(self.__serial_interface.write(GenericInterface.format_duty(pidpmp.value,0)))
                        state_dict = {**state_dict, pidpmp: 0}
                self.state.set_value(ActiveState(state_dict))
            writestr = GenericInterface.format_duty(identifier.value,new_duty)
            self.run_async(self.__serial_interface.write(writestr))

    def change_settings(self,modifications: dict[Settings,Any]):
        def _contains_any(lst1: Iterable, lst2: Iterable):
            for item in lst1:
                if item in lst2:
                    return True
            return False
        modified_keys = set(modifications.keys())

        #----------------- PID settings --------------------
        if _contains_any(modified_keys,[Settings.ANOLYTE_PUMP,Settings.CATHOLYTE_PUMP,Settings.ANOLYTE_REFILL_PUMP,Settings.CATHOLYTE_REFILL_PUMP,Settings.BASE_CONTROL_DUTY]):
            self.stop_pid()
        if _contains_any(modified_keys,[Settings.AVERAGE_WINDOW_WIDTH,Settings.PID_REFILL_COOLDOWN]):
            cd_possibilities = read_settings(Settings.PID_REFILL_COOLDOWN,Settings.AVERAGE_WINDOW_WIDTH)
            window: float = cd_possibilities[Settings.AVERAGE_WINDOW_WIDTH]
            pid_cd: float = cd_possibilities[Settings.PID_REFILL_COOLDOWN]
            modifications[Settings.PID_REFILL_COOLDOWN] = max(pid_cd,window)

        # PID is running in a separate thread, so it needs to be queued in the threaded event loop
        pid_mods = {key:modifications[key] for key in modified_keys if key in PID_SETTINGS}
        self.run_sync(self.__pid.set_parameters,args = (pid_mods,))

        #----------------- Level settings ------------------
        new_capture: Capture|None = None
        if _contains_any(modified_keys,CAMERA_SETTINGS):
            self.stop_levels()
            new_capture = Capture.from_settings()
        elif Settings.AVERAGE_WINDOW_WIDTH in modified_keys:
            self.stop_levels()

        # Levels are running in a separate thread, so modifying needs to be queued on the event loop
        level_mods = {key:modifications[key] for key in modified_keys if key in LEVEL_SETTINGS}
        level_args = (level_mods,new_capture) if new_capture else (level_mods,)
        self.run_sync(self.__level.set_parameters,args = level_args)

        #----------------- Data settings --------------------
        if Settings.LEVEL_DIRECTORY in modified_keys:
            self.__level.set_dir(modifications[Settings.LEVEL_DIRECTORY])
        if Settings.PID_DIRECTORY in modified_keys:
            self.__pid.set_dir(modifications[Settings.PID_DIRECTORY])
        if Settings.SPEED_DIRECTORY in modified_keys:
            self.__poller.set_dir(modifications[Settings.SPEED_DIRECTORY])
        
        if Settings.LOG_LEVELS in modified_keys:
            self.__log_levels = modifications[Settings.LOG_LEVELS]
            self.__level_logging_state.set_value(self.__log_levels and self.logging_state.force_value())
        if Settings.LOG_PID in modified_keys:
            self.__log_pid = modifications[Settings.LOG_PID]
            self.__pid_logging_state.set_value(self.__log_pid and self.logging_state.force_value())
        if Settings.LOG_SPEEDS in modified_keys:
            self.__log_speeds = modifications[Settings.LOG_SPEEDS]
            self.__polling_logging_state.set_value(self.__log_speeds and self.logging_state.force_value())

    def set_logging(self,new_state: bool):
        self.__level_logging_state.set_value(self.__log_levels and new_state)
        self.__pid_logging_state.set_value(self.__log_pid and new_state)
        self.__polling_logging_state.set_value(self.__log_speeds and new_state)
        self.logging_state.set_value(new_state)

    def teardown(self):
        # print("running teardown")
        self.stop_levels()
        self.stop_pid()
        self.stop_polling()
        #TODO check race condition
        self.stop_event_loop()

    async def emergency_stop(self):
        """Stop all pumps. Since there is a mandatory delay between writes to the serial port, it is important to stop the pumps in the optimal order to minimise damage to the flow system. Pumps with high speeds are prioritised first. Within the high speed pumps, any pumps responsible for refilling the electrolyte reservoirs are handled first, followed by any electrolyte pumps. The low speed pumps are then handled in the same hierarchy"""
        LOW_PRIORITY_SPEED = 900
        # find the pumps that are low priority
        current_duties = self.__poller.state.force_value()
        if current_duties is not None:
            low_priority = []
            high_priority = []
            for pmp in current_duties.keys():
                if current_duties[pmp] < LOW_PRIORITY_SPEED:
                    low_priority.append(pmp)
                else:
                    high_priority.append(pmp)
        else:
            low_priority = [pmp.value for pmp in PumpNames]
            high_priority = []
        
        # now stop these pumps with order determined by pid system importance
        await self.__stop_with_hierarchy(high_priority)
        await self.__stop_with_hierarchy(low_priority)

    async def __stop_with_hierarchy(self,pumps: list[PumpNames]):
        HIERARCHY = [Settings.ANOLYTE_REFILL_PUMP,Settings.CATHOLYTE_REFILL_PUMP,Settings.ANOLYTE_PUMP,Settings.CATHOLYTE_PUMP]
        important_pumps = self.__pid.get_pumps()
        high_priority: list[PumpNames] = []
        low_priority = copy.copy(pumps)
        for pump_role in HIERARCHY:
            current_pump = important_pumps[pump_role]
            if current_pump in pumps:
                high_priority.append(current_pump)
                low_priority.remove(current_pump)
        
        # first loop through the high priority pumps (in their order of hierarchy):
        for hpp in high_priority:
            await self.__serial_interface.write(GenericInterface.format_duty(hpp.value,0))
        
        # then do the low(er) priority pumps in any order
        for lpp in low_priority:
            await self.__serial_interface.write(GenericInterface.format_duty(lpp.value,0))

    def _async_teardowns(self) -> Iterable[Coroutine[None, None, None]]:
        setout: set[Coroutine[None,None,None]] = set()
        for pump in PumpNames:
            async def write_without_error(pmp: PumpNames):
                try:
                    await self.__serial_interface.write(GenericInterface.format_duty(pmp.value,0))
                except InterfaceException:
                    pass
            setout.add(write_without_error(pump))
        return setout
    
    def _sync_teardown(self) -> None:
        self.__serial_interface.close()
#TODO write code to start the PID and Level sensors

def is_duty(duty: int):
    if duty >= 0 and duty <= 255:
        return True
    return False
