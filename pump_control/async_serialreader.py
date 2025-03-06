from support_classes import Generator, PumpNames, PumpConfig, Timer
from serial_interface import GenericInterface, InterfaceException
import asyncio

MINIMUM_POLL_TIME = 1.0
MAXIMUM_POLL_TIME = 4.0

SpeedReading = dict[PumpNames,float]
class SerialReader(Generator[SpeedReading|None]):

    def __init__(self,serial_interface: GenericInterface) -> None:
        super().__init__()
        self.__serial_interface = serial_interface
        self.__timer = Timer(MINIMUM_POLL_TIME)

    async def _setup(self):
        pass

    async def _loop(self) -> SpeedReading:
        try:
            if self.__timer.check():
                new_line = await asyncio.wait_for(self.__serial_interface.readbuffer(),MAXIMUM_POLL_TIME)
            # ensures a minium time between polls to guard against microcontrollers that spam readings over the serial port
            while self.can_generate() and not self.__timer.check():
                # conversely, one can also put a timeout on buffer reading to be set, guarding against slow/no readings
                new_line = await asyncio.wait_for(self.__serial_interface.readbuffer(),MAXIMUM_POLL_TIME)
            self.__timer.reset()
            new_speeds = list(map(float,new_line.split(",")))
            if len(new_speeds)<len(PumpConfig().pumps):
                additional_speeds = [0.0]*(len(PumpConfig().pumps)-len(new_speeds))
                new_speeds = [*new_speeds,*additional_speeds]
            new_dict: SpeedReading = dict(zip(PumpConfig().pumps,new_speeds))
            return new_dict
        except (TimeoutError,ValueError):
            return None
        except InterfaceException:
            raise

    def teardown(self):
        pass