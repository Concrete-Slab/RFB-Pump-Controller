import numpy as np
from simple_pid import PID
import datetime
from .async_levelsensor import LevelBuffer
from serial_interface import GenericInterface
import asyncio
from support_classes import Generator,SharedState
from .PUMP_CONSTS import PID_DATA_TIMEOUT, PumpNames, PID_PUMPS
from pathlib import Path
from .datalogger import log_data

Duties = tuple[int,int]

class PIDRunner(Generator[Duties]):

    LOG_COLUMN_HEADERS = ["Timestamp", "Anolyte Pump Duty", "Catholyte Pump Duty"]
    
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
        try:
            level_buffer, frame = self.__input_state.get_value()
            if level_buffer is not None:
                # There is new data! Read it from the level generator queue
 
                last_readings = np.array(level_buffer.read())

                # Calculate the average of the buffer readings
                # negative if reading 1 greater than reading 2
                error = 0 - np.mean(last_readings[:,3])
                
                # Perform the PID control (rounded as duty is an integer)
                control = round(self.__pid(error))

                # Assign new duties
                if (control > 0):
                    flowRateAn = self.__base_duty + control
                    flowRateCath = self.__base_duty
                    
                else:
                    flowRateAn = self.__base_duty
                    flowRateCath = self.__base_duty - control

                # Write the new flow rates to the serial device
                await self.__serial_interface.write(GenericInterface.format_duty(PID_PUMPS["anolyte"].value,flowRateAn))
                await self.__serial_interface.write(GenericInterface.format_duty(PID_PUMPS["catholyte"].value,flowRateCath))

                # Optionally, save the new duties in the data file as a new line
                if self.__logging:
                    # print(flowRateA, flowRateB)
                    timestamp = datetime.datetime.now().strftime("%m-%d-%Y %H-%M-%S")
                    data = [timestamp, flowRateAn, flowRateCath]
                    if self.__datafile is None:
                        self.__datafile = timestamp
                    log_data(self.__LOG_PATH.as_posix(),self.__datafile,data,column_headers=self.LOG_COLUMN_HEADERS)
                
                return (flowRateAn,flowRateCath)
        except IOError as e:
            print("Error saving flowrates to file")
            print(e)
        return None

    def teardown(self):
        self.__datafile = None