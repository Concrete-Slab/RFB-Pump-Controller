from support_classes import Generator, GeneratorException
from serial_interface import GenericInterface, InterfaceException
from .PUMP_CONSTS import PumpNames
import asyncio

SpeedReading = dict[PumpNames,float]
class SerialReader(Generator[SpeedReading|None]):

    def __init__(self,serial_interface: GenericInterface) -> None:
        super().__init__()
        self.__serial_interface = serial_interface

    async def _setup(self):
        pass

    async def _loop(self) -> SpeedReading:
        try:
            await asyncio.sleep(1)
            # allows a timeout on buffer reading to be set
            new_line = await asyncio.wait_for(self.__serial_interface.readbuffer(),4)
            new_speeds = list(map(float,new_line.split(",")))
            new_dict: SpeedReading = dict(zip(PumpNames,new_speeds))
            return new_dict
        except (TimeoutError,ValueError):
            return None
        except InterfaceException:
            raise

    def teardown(self):
        pass