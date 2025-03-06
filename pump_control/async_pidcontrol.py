from typing import Any, Iterable
from simple_pid import PID
from serial_interface.SerialInterface import SERIAL_WRITE_PAUSE
from .async_levelsensor import LevelReading, LevelOutput
from serial_interface import GenericInterface
import asyncio
from support_classes import Generator,SharedState, DEFAULT_SETTINGS, Settings, PumpNames, PumpConfig
import time

Duties = dict[PumpNames,int]

PID_PAUSE_MARGIN = 1.5
"""Factor of the SERIAL_WRITE_PAUSE that will be awaited to send new duties"""
PID_DATA_TIMEOUT = 1.0
""""Seconds that the PID controller will wait for new data before checking loop conditions. Essentially only determines how long it will take to kill the PID process once level process is killed"""

class PIDRunner(Generator[Duties]):


    def __init__(self, 
                 level_state: SharedState[LevelOutput], 
                 serial_interface: GenericInterface, level_event: asyncio.Event, 
                 base_duty: int = DEFAULT_SETTINGS[Settings.BASE_CONTROL_DUTY], 
                 refill_time: int = DEFAULT_SETTINGS[Settings.REFILL_TIME],
                 refill_duty: int = DEFAULT_SETTINGS[Settings.REFILL_DUTY],
                 refill_percentage: int = DEFAULT_SETTINGS[Settings.REFILL_PERCENTAGE_TRIGGER],
                 refill_cooldown_period: float = DEFAULT_SETTINGS[Settings.PID_REFILL_COOLDOWN],
                 refill_stop_on_full: bool = DEFAULT_SETTINGS[Settings.REFILL_STOP_ON_FULL],
                 anolyte_pump: PumpNames|None = DEFAULT_SETTINGS[Settings.ANOLYTE_PUMP],
                 proportional_gain: float = DEFAULT_SETTINGS[Settings.PROPORTIONAL_GAIN],
                 integral_gain: float = DEFAULT_SETTINGS[Settings.INTEGRAL_GAIN],
                 derivative_gain: float = DEFAULT_SETTINGS[Settings.DERIVATIVE_GAIN],
                 catholyte_pump: PumpNames|None = DEFAULT_SETTINGS[Settings.CATHOLYTE_PUMP], 
                 anolyte_refill_pump: PumpNames|None = DEFAULT_SETTINGS[Settings.ANOLYTE_REFILL_PUMP], 
                 catholyte_refill_pump: PumpNames|None = DEFAULT_SETTINGS[Settings.CATHOLYTE_REFILL_PUMP],
                 **kwargs) -> None:

        super().__init__()

        

        self.__pid_pumps = {
            Settings.ANOLYTE_PUMP: anolyte_pump,
            Settings.CATHOLYTE_PUMP: catholyte_pump,
            Settings.ANOLYTE_REFILL_PUMP: anolyte_refill_pump,
            Settings.CATHOLYTE_REFILL_PUMP: catholyte_refill_pump
        }

        # self.__prev_duties = {pmp:0 for pmp in PumpConfig().pumps}
        self.__prev_duties = {}
        self.__refill_time = refill_time
        self.__refill_duty = refill_duty
        self.__refill_percentage_trigger = refill_percentage
        self.__refill_cooldown_period = refill_cooldown_period
        self.__refill_stop_on_full = refill_stop_on_full
        self.__base_duty = base_duty
        self.__proportional_gain = proportional_gain
        self.__integral_gain = integral_gain
        self.__derivative_gain = derivative_gain

        self.__input_state = level_state
        self.__serial_interface = serial_interface
        self.__level_event = level_event
        self.__pid: PID | None = None
        self.__refill_start_time: float | None = None
        self.__refill_finish_time: float | None = None

    async def _setup(self):
        self.__prev_duties = {pmp:0 for pmp in PumpConfig().pumps}
        self.__pid = PID(Kp=-self.__proportional_gain, Ki=-self.__integral_gain, Kd=self.__derivative_gain, setpoint=0, sample_time=None, 
        output_limits=(-(255-self.__base_duty), 255-self.__base_duty), auto_mode=True, proportional_on_measurement=False, error_map=None)
        #TODO why on earth is this next bit necessary?
        self.__pid.set_auto_mode(False)
        await asyncio.sleep(3)
        self.__pid.set_auto_mode(True, last_output=-.28)

    async def _loop(self) -> Duties|None:

        # The outer while loop guards against reading levels faster than the mandatory serial write pause
        # This would cause the write queue to accumulate commands faster than it can execute
        # if the wait function returns false, then it has exited because the generator has been stopped
        # in such a case, the function returns early to speed up the teardown process

        initial_request_time = time.time()
        current_time = initial_request_time
        while current_time-initial_request_time < SERIAL_WRITE_PAUSE * PID_PAUSE_MARGIN:
            levels_available = await self.__wait_for_levels()
            if not levels_available:
                return
            current_time = time.time()

        level_state = self.__input_state.get_value()
        if level_state is not None and level_state.levels is not None:
            # There is new data! Read it from the level generator queue

            # level state is a dataclass; the "levels" item contains the LevelReading entry
            last_readings = level_state.levels

            # Assign new duties to refill pumps
            (flowrate_refill_anolyte,flowRate_refill_catholyte,refill_duties) = await self.__handle_refill(last_readings)
            # Assign new duties to electrolyte pumps
            (flowrate_anolyte,flowrate_catholyte,pid_duties) = await self.__handle_pid(last_readings)

            duties: Duties = {**pid_duties,**refill_duties}
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
        self.__refill_cooldown_period = float(new_parameters[Settings.PID_REFILL_COOLDOWN]) if Settings.PID_REFILL_COOLDOWN in new_parameters.keys() else self.__refill_cooldown_period
        
        self.__proportional_gain = float(new_parameters[Settings.PROPORTIONAL_GAIN]) if Settings.PROPORTIONAL_GAIN in new_parameters.keys() else self.__proportional_gain
        self.__integral_gain = float(new_parameters[Settings.INTEGRAL_GAIN]) if Settings.INTEGRAL_GAIN in new_parameters.keys() else self.__integral_gain
        self.__derivative_gain = float(new_parameters[Settings.DERIVATIVE_GAIN]) if Settings.DERIVATIVE_GAIN in new_parameters.keys() else self.__derivative_gain
        
        def _contains_any(lst1: Iterable, lst2: Iterable):
            for item in lst1:
                if item in lst2:
                    return True
            return False
        
        if _contains_any([Settings.BASE_CONTROL_DUTY,Settings.PROPORTIONAL_GAIN,Settings.INTEGRAL_GAIN,Settings.DERIVATIVE_GAIN],new_parameters.keys()):
            self.stop()
            self.__pid = PID(Kp=-self.__proportional_gain, Ki=-self.__integral_gain, Kd=self.__derivative_gain, setpoint=0, sample_time=None, 
                        output_limits=(-(255-self.__base_duty), 255-self.__base_duty), auto_mode=True, proportional_on_measurement=False, error_map=None)

        for pmpsetting in self.__pid_pumps.keys():
            if pmpsetting in new_parameters.keys():
                new_pump: PumpNames|None = new_parameters[pmpsetting]
                self.__pid_pumps[pmpsetting] = new_pump

    async def __handle_refill(self, new_levels: LevelReading|None) -> tuple[int,int,Duties]:

        # extract the volume change and initial volume from the new readings
        if new_levels:
            volume_change = new_levels[3]
            initial_volume = new_levels[0] + new_levels[1] - volume_change
        
            # calculate the percentage change in volume from initial volume
            percent_change = 0-volume_change/initial_volume * 100 if initial_volume != 0 else 0

            # determine if volume has been depleted enough to justify a refill
            insufficient_volume = (initial_volume>0) and (percent_change>self.__refill_percentage_trigger)

            # determine if a refill is ongoing, and if the reservoir is full again, and the setting to stop filling once full is active
            full_stop_refill = self.__refill_start_time is not None and volume_change >= 0 and self.__refill_stop_on_full

        else:
            # no new levels provided - we can neither start a refill nor end it with the "reservoir is refilled" cutoff logic. We may only determine if the time-based cutoff is reached.
            insufficient_volume = False
            full_stop_refill = False

        current_time = time.time()

        # determine if the refill cooldown is active
        cooldown_over = (self.__refill_finish_time is None) or (current_time - self.__refill_finish_time > self.__refill_cooldown_period)
        # determine if refilling is ongoing at the moment
        refill_not_yet_started = self.__refill_start_time is None
        # check conditions to stop refilling for the time-based cutoff
        time_stop_refill = self.__refill_start_time is not None and (current_time - self.__refill_start_time) > self.__refill_time and not self.__refill_stop_on_full

        if insufficient_volume and refill_not_yet_started and cooldown_over:
            # Start refilling if threshold is reached, the cooldown period is over, and we aren't already refilling 
            anolyte_write = await self.__write_nullsafe(self.__pid_pumps[Settings.ANOLYTE_REFILL_PUMP],self.__refill_duty)
            catholyte_write = await self.__write_nullsafe(self.__pid_pumps[Settings.CATHOLYTE_REFILL_PUMP],self.__refill_duty)
            self.__refill_finish_time = None
            self.__refill_start_time = current_time if (anolyte_write or catholyte_write) else None
        # elif self.__refill_start_time is not None and (current_time - self.__refill_start_time) > self.__refill_time and not self.__refill_stop_on_full:
        elif time_stop_refill or full_stop_refill:
            # stop the refill and reset variables
            anolyte_write = await self.__write_nullsafe(self.__pid_pumps[Settings.ANOLYTE_REFILL_PUMP],0)
            anolyte_write = await self.__write_nullsafe(self.__pid_pumps[Settings.CATHOLYTE_REFILL_PUMP],0)
            self.__refill_start_time = None
            self.__refill_finish_time = current_time
        duties: Duties = {}

        anolyte_refillrate = self.__prev_duties[self.__pid_pumps[Settings.ANOLYTE_REFILL_PUMP]] if self.__pid_pumps[Settings.ANOLYTE_REFILL_PUMP] is not None else 0
        catholyte_refillrate = self.__prev_duties[self.__pid_pumps[Settings.CATHOLYTE_REFILL_PUMP]] if self.__pid_pumps[Settings.CATHOLYTE_REFILL_PUMP] is not None else 0
        
        # anolyte_refillrate = self.__refill_duty if (self.__refill_start_time is not None and self.__pid_pumps[Settings.ANOLYTE_REFILL_PUMP] is not None) else 0
        if self.__pid_pumps[Settings.ANOLYTE_REFILL_PUMP] is not None:
            duties = {**duties,self.__pid_pumps[Settings.ANOLYTE_REFILL_PUMP]: anolyte_refillrate}

        # catholyte_refillrate = self.__refill_duty if (self.__refill_start_time is not None and self.__pid_pumps[Settings.CATHOLYTE_REFILL_PUMP] is not None) else 0
        if self.__pid_pumps[Settings.CATHOLYTE_REFILL_PUMP] is not None:
            duties = {**duties,self.__pid_pumps[Settings.CATHOLYTE_REFILL_PUMP]: catholyte_refillrate}

        return (anolyte_refillrate,catholyte_refillrate,duties)

    async def __handle_pid(self,new_levels: LevelReading) -> tuple[int,int,Duties]:

        # extract the difference in level from the level readings
        error = new_levels[2]

        control = round(self.__pid(error))

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
        if (pmp is not None) and (self.__prev_duties[pmp] != duty):
            pmpstr = pmp.value
            self.__serial_interface.write(GenericInterface.format_duty(pmpstr,duty))
            self.__prev_duties[pmp] = duty
            await asyncio.sleep(1.5)
        return (pmp is not None)
 
    async def __wait_for_levels(self) -> bool:
        # The following block continuously checks for either:
        # - The level event to be set, indicating that new level data is available
        #       The event is cleared after the block to allow the process to be repeated again
        #       In such a case the function return True
        # - The generator to be shut down.
        #       The generate() only checks the stop event after _loop returns.
        #       If the level sensor is shut down, this class has no way of knowing until _loop returns, so it will deadlock on the await line
        #       This block with an await timeout therefore allows the code to avoid this scenario and return early
        #       In such a case the function returns False
        while self.can_generate():
            try:
                await asyncio.wait_for(self.__level_event.wait(),timeout = PID_DATA_TIMEOUT)
                if self.__refill_start_time is not None:
                    # system is refilling, check to end refill in the case that new levels will take too long
                    # TODO Major error here????????????????
                    await self.__handle_refill(1,0)
                break
            except TimeoutError:
                pass
        if not self.can_generate():
            return False
        self.__level_event.clear()
        return True
