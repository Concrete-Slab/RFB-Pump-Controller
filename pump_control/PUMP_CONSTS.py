import numpy as np
from enum import Enum

SERIAL_READ_TIMEOUT = 1.0
"""Seconds until speed reading timeout is aborted and __poll_serial loop continues"""
PID_DATA_TIMEOUT = 1.0
""""Seconds that the PID controller will wait for new data before checking loop conditions. Essentially only determines how long it will take to kill the PID process once level process is killed"""
LEVEL_SENSE_PERIOD = 5.0
"""Seconds between level readings"""
BUFFER_WINDOW_LENGTH = 18*60
"""Seconds between the oldest and newest readings in the level readings buffer"""
LEVEL_AVERAGE_PERIOD = 60.0
"""Seconds over which consecutive readings are averaged"""
LEVEL_AVERAGE_PERIOD_SHORT = 30.0
"""Shorter period used for calibration"""
LEVEL_STABILISATION_PERIOD = 120.0
"""Period over which the initial volume calculation is stabilised"""
CV2_KERNEL = np.ones([27,27],np.uint8)
"""kernel size for image processing operators"""
CV2_KERNEL_SIZE = 31
REFILL_LOSS_TRIGGER = 0.1
"""Percent loss of solvent that will trigger the refill system"""
REFILL_DUTY = 50
"""Duty applied to the refill pump when PID controller detects low levels"""
REFILL_TIME = 30
"""Seconds for which the main reservoirs are topped up after a refill event is triggered"""

class PumpNames(Enum):
    A = "a"
    B = "b"
    C = "c"
    D = "d"
    E = "e"
    F = "f"

    @staticmethod
    def set_pid_pumps(new_dict):
        #TODO some sort of input validation
        __pid_pumps = new_dict

    @staticmethod
    def get_pid_pumps():
        return __pid_pumps

    def is_pid(self):
        return self in __pid_pumps.values()

__pid_pumps: dict[str,PumpNames|None] = {}
PID_PUMPS: dict[str,PumpNames|None] = {"anolyte": PumpNames.E,
                                       "catholyte": PumpNames.F,
                                       "refill anolyte": None,
                                       "refill catholyte": None}