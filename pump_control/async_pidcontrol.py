from typing import Any
import numpy as np
from simple_pid import PID
import datetime
from .async_levelsensor import LevelBuffer
from serial_interface import GenericInterface
import asyncio
from support_classes import Generator,SharedState,Loggable, DEFAULT_SETTINGS, Settings, PumpNames
from .PUMP_CONSTS import PID_DATA_TIMEOUT
from pathlib import Path
import time

Duties = dict[PumpNames,int]

class PIDRunner(Generator[Duties],Loggable):

    LOG_COLUMN_HEADERS = ["Timestamp", "Elapsed Seconds", "Anolyte Pump Duty", "Catholyte Pump Duty", "Anolyte Refill Pump Duty","Catholyte Refill Pump Duty"]

    def __init__(self, 
                 level_state: SharedState[tuple[LevelBuffer,np.ndarray|None]], 
                 serial_interface: GenericInterface, level_event: asyncio.Event, 
                 logging_state: SharedState[bool]=SharedState(False), 
                 absolute_logging_directory: Path = DEFAULT_SETTINGS[Settings.PID_DIRECTORY], 
                 base_duty: int = DEFAULT_SETTINGS[Settings.BASE_CONTROL_DUTY], 
                 refill_time: int = DEFAULT_SETTINGS[Settings.REFILL_TIME],
                 refill_duty: int = DEFAULT_SETTINGS[Settings.REFILL_DUTY],
                 refill_percentage: int = DEFAULT_SETTINGS[Settings.REFILL_PERCENTAGE_TRIGGER],
                 anolyte_pump: PumpNames|None = DEFAULT_SETTINGS[Settings.ANOLYTE_PUMP], 
                 catholyte_pump: PumpNames|None = DEFAULT_SETTINGS[Settings.CATHOLYTE_PUMP], 
                 anolyte_refill_pump: PumpNames|None = DEFAULT_SETTINGS[Settings.ANOLYTE_REFILL_PUMP], 
                 catholyte_refill_pump: PumpNames|None = DEFAULT_SETTINGS[Settings.CATHOLYTE_REFILL_PUMP], 
                 **kwargs) -> None:

        super().__init__(directory = absolute_logging_directory, default_headers = PIDRunner.LOG_COLUMN_HEADERS)

        

        self.__pid_pumps = {
            Settings.ANOLYTE_PUMP: anolyte_pump,
            Settings.CATHOLYTE_PUMP: catholyte_pump,
            Settings.ANOLYTE_REFILL_PUMP: anolyte_refill_pump,
            Settings.CATHOLYTE_REFILL_PUMP: catholyte_refill_pump
        }

        self.__prev_duties = {pmp:0 for pmp in PumpNames}

        self.__refill_time = refill_time
        self.__refill_duty = refill_duty
        self.__refill_percentage_trigger = refill_percentage
        self.__base_duty = base_duty

        self.__input_state = level_state
        self.__serial_interface = serial_interface
        self.__logging_state = logging_state
        self.__level_event = level_event
        self.__pid: PID|None = None
        self.__refill_start_time: float | None = None

    async def _setup(self):

        #TODO verify that changing the min output to 0 will not change bevaviour
        self.__pid = PID(Kp=-100, Ki=-0.005, Kd=0.0, setpoint=0, sample_time=None, 
        output_limits=(-(255-self.__base_duty), 255-self.__base_duty), auto_mode=True, proportional_on_measurement=False, error_map=None)
        #TODO why on earth is this next bit necessary?
        self.__pid.set_auto_mode(False)
        await asyncio.sleep(3)
        self.__pid.set_auto_mode(True, last_output=-.28)
        self.new_file()

    async def _loop(self) -> Duties|None:
        # The following block continuously checks for either:
        # - The level event to be set, indicating that new level data is available
        #       The event is cleared after the block to allow the process to be repeated again
        # - The generator to be shut down.
        #       The generate() only checks the stop event after _loop returns.
        #       If the level sensor is shut down, this class has no way of knowing until _loop returns, so it will deadlock on the await line
        #       This block with an await timeout therefore allows the code to avoid this scenario and return early
        while self.can_generate():
            try:
                await asyncio.wait_for(self.__level_event.wait(),timeout = PID_DATA_TIMEOUT)
                break
            except TimeoutError:
                pass
        if not self.can_generate():
            return
        self.__level_event.clear()

        # update the state of the datalogger

        level_state = self.__input_state.get_value()
        if level_state is not None:
            # There is new data! Read it from the level generator queue

            last_readings = np.array(level_state[0].read())

            # Calculate the average of the buffer readings
            # positive if anolyte volume greater than catholyte volume
            error = np.mean(last_readings[:,3])

            volume_change = np.mean(last_readings[:,4])
            init_volume = np.mean(last_readings[:,1]) + np.mean(last_readings[:,2]) - volume_change
            
            # Perform the PID control (rounded as duty is an integer)
            control = round(self.__pid(error))

            # Assign new duties
            (flowRateRefillAnolyte,flowRateRefillCatholyte,refill_duties) = await self.__handle_refill(init_volume,volume_change)
            (flowRateAn,flowRateCath,pid_duties) = await self.__handle_pid(control)

            duties: Duties = {**pid_duties,**refill_duties}

            # Optionally, save the new duties in the data file as a new line
            if self.__logging_state.force_value():
                timestamp = datetime.datetime.now().strftime("%m-%d-%Y %H-%M-%S")
                data = [timestamp, flowRateAn, flowRateCath,flowRateRefillAnolyte,flowRateRefillCatholyte]
                # if self.__datafile is None:
                #     self.__datafile = timestamp
                # log_data(self.__LOG_PATH.as_posix(),self.__datafile,data,column_headers=self.LOG_COLUMN_HEADERS)
                self.log(data)
            return duties
        return None

    def teardown(self):
        pass

    def get_pumps(self) -> dict[Settings,PumpNames|None]:
        return self.__pid_pumps

    def set_parameters(self,new_parameters: dict[Settings,Any]):
        self.__base_duty = int(new_parameters[Settings.BASE_CONTROL_DUTY]) if Settings.BASE_CONTROL_DUTY in new_parameters.keys() else self.__base_duty
        self.__refill_time = int(new_parameters[Settings.REFILL_TIME]) if Settings.REFILL_TIME in new_parameters.keys() else self.__refill_time
        self.__refill_duty = int(new_parameters[Settings.REFILL_DUTY]) if Settings.REFILL_DUTY in new_parameters.keys() else self.__refill_duty
        self.__refill_percentage_trigger = int(new_parameters[Settings.REFILL_PERCENTAGE_TRIGGER]) if Settings.REFILL_PERCENTAGE_TRIGGER in new_parameters.keys() else self.__refill_percentage_trigger
        
        for pmpsetting in self.__pid_pumps.keys():
            if pmpsetting in new_parameters.keys():
                new_pump: PumpNames|None = new_parameters[pmpsetting]
                self.__pid_pumps[pmpsetting] = new_pump

    async def __handle_refill(self,initial_volume,volume_change) -> tuple[int,int,Duties]:
        percent_change = 0-volume_change/initial_volume * 100
        if initial_volume>0 and percent_change>self.__refill_percentage_trigger and self.__refill_start_time is None:
            anolyte_write = await self.__write_nullsafe(self.__pid_pumps[Settings.ANOLYTE_REFILL_PUMP],self.__refill_duty)
            catholyte_write = await self.__write_nullsafe(self.__pid_pumps[Settings.CATHOLYTE_REFILL_PUMP],self.__refill_duty)
            self.__refill_start_time = time.time() if (anolyte_write or catholyte_write) else None
        elif self.__refill_start_time is not None and (time.time() - self.__refill_start_time) > self.__refill_duty:
            await self.__write_nullsafe(self.__pid_pumps[Settings.ANOLYTE_REFILL_PUMP],self.__refill_duty)
            await self.__write_nullsafe(self.__pid_pumps[Settings.CATHOLYTE_REFILL_PUMP],self.__refill_duty)
            self.__refill_start_time = None
        duties: Duties = {}
        
        anolyte_refillrate = self.__refill_duty if (self.__refill_start_time is not None and self.__pid_pumps[Settings.ANOLYTE_REFILL_PUMP] is not None) else 0
        if self.__pid_pumps[Settings.ANOLYTE_REFILL_PUMP] is not None:
            duties = {**duties,self.__pid_pumps[Settings.ANOLYTE_REFILL_PUMP]: anolyte_refillrate}
        
        catholyte_refillrate = self.__refill_duty if (self.__refill_start_time is not None and self.__pid_pumps[Settings.CATHOLYTE_REFILL_PUMP] is not None) else 0
        if self.__pid_pumps[Settings.CATHOLYTE_REFILL_PUMP] is not None:
            duties = {**duties,self.__pid_pumps[Settings.CATHOLYTE_REFILL_PUMP]: catholyte_refillrate}
        
        return (anolyte_refillrate,catholyte_refillrate,duties)
    
    async def __handle_pid(self,control: int) -> tuple[int,int,Duties]:
        if (control > 0):
            flowRateAn = self.__base_duty + control
            flowRateCath = self.__base_duty
        else:
            flowRateAn = self.__base_duty
            flowRateCath = self.__base_duty - control

        duties: Duties = {}
        anolyte_flowrate = 0
        catholyte_flowrate = 0

        anolyte_write = await self.__write_nullsafe(self.__pid_pumps[Settings.ANOLYTE_PUMP],flowRateAn)
        if anolyte_write:
            anolyte_flowrate = flowRateAn
            duties = {**duties,self.__pid_pumps[Settings.ANOLYTE_PUMP]: anolyte_flowrate}

        catholyte_write = await self.__write_nullsafe(self.__pid_pumps[Settings.CATHOLYTE_PUMP],flowRateCath)
        if catholyte_write:
            catholyte_flowrate = flowRateCath
            duties = {**duties,self.__pid_pumps[Settings.CATHOLYTE_PUMP]: catholyte_flowrate}

        return (anolyte_flowrate,catholyte_flowrate,duties)
    
    async def __write_nullsafe(self,pmp: PumpNames,duty: int) -> bool:
        if self.__prev_duties[pmp] != duty:
            pmpstr = pmp.value
            await self.__serial_interface.write(GenericInterface.format_duty(pmpstr,duty))
            self.__prev_duties[pmp] = duty
            await asyncio.sleep(1.5)
        return (pmp is not None)
