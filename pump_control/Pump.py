from typing import Coroutine, Iterable
from serial_interface import GenericInterface, InterfaceException
from support_classes import AsyncRunner, Teardown, SharedState, GeneratorException
import threading
import asyncio
from concurrent.futures import Future
from .async_levelsensor import LevelSensor, LevelBuffer, Rect, DummySensor
from .async_pidcontrol import PIDRunner, Duties
from .async_serialreader import SerialReader, SpeedReading
from .PUMP_CONSTS import PumpNames, PID_PUMPS
from abc import ABC


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
        # kwargs to include:
        #   LOGGING - True/False
        #   rel_duty_directory - relative directory for logging pump flowrates
        #   rel_level_directory - relative directory for logging reservoir levels
        #   queue_max_size - maximum size for the queue object containing serial buffer readings
        LOGGING = kwargs.pop("LOGGING",True)
        rel_duty_directory = kwargs.pop("rel_duty_directory","\\pumps\\flowrates")
        rel_level_directory = kwargs.pop("rel_level_directory","\\pumps\\levels")
        super().__init__()

        self.__serial_interface = serial_interface

        self.state: SharedState[PumpState] = SharedState[PumpState]()

        self.logging_state: SharedState[bool] = SharedState[bool](False)

        # create the PID and level sense objects. The PID object operates on the shared state and sensed_event from the level object
        # self.__level: LevelSensor = LevelSensor(logging_state=self.logging_state,rel_level_directory=rel_level_directory)
        self.__level: LevelSensor = LevelSensor(logging_state=self.logging_state,rel_level_directory=rel_level_directory)
        self.__pid: PIDRunner = PIDRunner(self.__level.state,self.__serial_interface,self.__level.sensed_event,logging_state=self.logging_state,rel_duty_directory=rel_duty_directory)
        self.__poller: SerialReader = SerialReader(self.__serial_interface)

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

    def start_levels(self, video_device: int, rect1: Rect, rect2: Rect, rect_ref: Rect, vol_ref: float, vol_init: float) -> tuple[SharedState[bool],SharedState[LevelBuffer]]:
        try:
            self.__level.set_vision_parameters(video_device, rect1, rect2, rect_ref, vol_ref, vol_init)
        except ValueError as e:
            print()
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
        # print("setting duty to "+str(new_duty))
        if is_duty(new_duty):
            if identifier == PID_PUMPS["anolyte"]:
                if self.__pid.is_running.value:
                    self.stop_pid()
                    stopb_str = GenericInterface.format_duty(PID_PUMPS["catholyte"].value,0)
                    self.run_async(self.__serial_interface.write(stopb_str))
                    self.state.set_value(ActiveState({PID_PUMPS["catholyte"]:0}))
            elif identifier == PID_PUMPS["catholyte"]:
                if self.__pid.is_running.value:
                    self.stop_pid()
                    stopcath_str = GenericInterface.format_duty(PID_PUMPS["anolyte"].value,0)
                    self.run_async(self.__serial_interface.write(stopcath_str))
                    self.state.set_value(ActiveState({PID_PUMPS["anolyte"]:0}))
            writestr = GenericInterface.format_duty(identifier.value,new_duty)
            self.run_async(self.__serial_interface.write(writestr))

    def teardown(self):
        # print("running teardown")
        self.stop_levels()
        self.stop_pid()
        self.stop_polling()
        #TODO check race condition
        self.stop_event_loop()

    def _async_teardowns(self) -> Iterable[Coroutine[None, None, None]]:
        setout: set[Coroutine[None,None,None]] = set()
        for pump in PumpNames:
            async def write_without_error(pmp: PumpNames):
                try:
                    await self.__serial_interface.write(f"<{pmp.value},0>")
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
        



