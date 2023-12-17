import numpy as np
from simple_pid import PID
import datetime
from .async_levelsensor import LevelBuffer
from serial_interface import GenericInterface
import asyncio
from support_classes import Generator,SharedState
from .PUMP_CONSTS import PID_DATA_TIMEOUT, PID_PUMPS, REFILL_LOSS_TRIGGER, REFILL_DUTY, REFILL_TIME, PumpNames
from pathlib import Path
from .datalogger import log_data
import time

Duties = dict[PumpNames,int]

class PIDRunner(Generator[Duties]):

    LOG_COLUMN_HEADERS = ["Timestamp", "Elapsed Seconds", "Anolyte Pump Duty", "Catholyte Pump Duty", "Refill Pump Duty"]
    
    def __init__(self, level_state: SharedState[tuple[LevelBuffer,np.ndarray|None]], serial_interface: GenericInterface, level_event: asyncio.Event, logging_state: SharedState[bool]=SharedState(False), rel_duty_directory="\\pumps\\flowrates", base_duty=92, **kwargs) -> None:
        super().__init__()
        self.__rel_duty_directory = rel_duty_directory.strip("\\").strip("/").replace("\\","/")
        self.__LOG_PATH = Path(__file__).absolute().parent / self.__rel_duty_directory
        print(self.__LOG_PATH)
        print(str(Path(__file__).absolute().parent))
        self.__input_state = level_state
        self.__serial_interface = serial_interface
        self.__logging = logging_state.value
        self.__logging_state = logging_state
        self.__datafile: str|None = None
        self.__base_duty = base_duty
        self.__level_event = level_event
        self.__pid: PID|None = None
        self.__is_refilling: bool = False
        self.__refill_start_time: float | None = None

    async def _setup(self):

        #TODO verify that changing the min output to 0 will not change bevaviour
        self.__pid = PID(Kp=-100, Ki=-0.005, Kd=0.0, setpoint=0, sample_time=None, 
        output_limits=(-(255-self.__base_duty), 255-self.__base_duty), auto_mode=True, proportional_on_measurement=False, error_map=None)
        #TODO why on earth is this next bit necessary?
        self.__pid.set_auto_mode(False)
        await asyncio.sleep(3)
        self.__pid.set_auto_mode(True, last_output=-.28)

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

        self.__logging = self.__logging_state.value
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
            if self.__logging:
                timestamp = datetime.datetime.now().strftime("%m-%d-%Y %H-%M-%S")
                data = [timestamp, flowRateAn, flowRateCath,flowRateRefillAnolyte,flowRateRefillCatholyte]
                if self.__datafile is None:
                    self.__datafile = timestamp
                log_data(self.__LOG_PATH.as_posix(),self.__datafile,data,column_headers=self.LOG_COLUMN_HEADERS)
            
            return duties
        return None

    def teardown(self):
        self.__datafile = None

    async def __handle_refill(self,initial_volume,volume_change) -> tuple[int,int,Duties]:
        percent_change = 0-volume_change/initial_volume
        if initial_volume>0 and percent_change>REFILL_LOSS_TRIGGER and self.__refill_start_time is None:
            anolyte_write = await self.__write_nullsafe(PID_PUMPS["refill anolyte"],REFILL_DUTY)
            catholyte_write = await self.__write_nullsafe(PID_PUMPS["refill catholyte"],REFILL_DUTY)
            self.__refill_start_time = time.time() if (anolyte_write or catholyte_write) else None
        elif self.__refill_start_time is not None and (time.time() - self.__refill_start_time) > REFILL_TIME:
            await self.__write_nullsafe(PID_PUMPS["refill anolyte"],REFILL_DUTY)
            await self.__write_nullsafe(PID_PUMPS["refill catholyte"],REFILL_DUTY)
            self.__refill_start_time = None
        duties: Duties = {}
        
        anolyte_refillrate = REFILL_DUTY if (self.__refill_start_time is not None and PID_PUMPS["refill anolyte"] is not None) else 0
        if PID_PUMPS["refill anolyte"] is not None:
            duties = {**duties,PID_PUMPS["refill anolyte"]: anolyte_refillrate}
        
        catholyte_refillrate = REFILL_DUTY if (self.__refill_start_time is not None and PID_PUMPS["refill catholyte"] is not None) else 0
        if PID_PUMPS["refill catholyte"] is not None:
            duties = {**duties,PID_PUMPS["refill catholyte"]: catholyte_refillrate}
        
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

        anolyte_write = await self.__write_nullsafe(PID_PUMPS["anolyte"],flowRateAn)
        if anolyte_write:
            anolyte_flowrate = flowRateAn
            duties = {**duties,PID_PUMPS["anolyte"]: anolyte_flowrate}

        catholyte_write = await self.__write_nullsafe(PID_PUMPS["catholyte"],flowRateCath)
        if anolyte_write:
            catholyte_flowrate = flowRateCath
            duties = {**duties,PID_PUMPS["catholyte"]: catholyte_flowrate}

        return (anolyte_flowrate,catholyte_flowrate,duties)
    
    async def __write_nullsafe(self,pmp: PumpNames,duty: int) -> bool:
        if pmp is not None:
            await self.__serial_interface.write(GenericInterface.format_duty(pmp.value,duty))
            await asyncio.sleep(1.5)
            return True
        return False
