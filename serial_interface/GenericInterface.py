from abc import ABC, abstractmethod
import queue
import serial.tools.list_ports
from dataclasses import dataclass

DUMMY_PORT = "Dummy Port"
DUMMY_DESCRIPTION = "Debug Only"

@dataclass
class WriteCommand:
    pump: str
    duty: int
    def to_str(self) -> str:
        return GenericInterface.format_duty(self.pump,self.duty)
    @staticmethod
    def from_str(str_in: str) -> "WriteCommand":
        return WriteCommand(*GenericInterface.unformat_duty(str_in))

@dataclass
class SpeedReading:
    pump: str
    speed: float

    @staticmethod
    def from_str(str_in: str) -> list["SpeedReading"]:
        return [SpeedReading(*res) for res in GenericInterface.unformat_speeds(str_in)]


class GenericInterface(ABC):

    def __init__(self,port,**kwargs) -> None:
        pass

    @property
    @abstractmethod
    def written_duties(self) -> queue.Queue[WriteCommand]:
        """This is a queue that stores all write commands that have been successfully performed"""
        pass
    
    @abstractmethod
    async def establish(self):
        pass

    @abstractmethod
    def close(self):
        pass

    @abstractmethod
    async def readbuffer(self) -> str:
        pass

    @abstractmethod
    def write(self,command: WriteCommand):
        pass

    @staticmethod
    def get_serial_ports(debug: bool = False):
        COM_ports = serial.tools.list_ports.comports()
        COM_str = ['']*len(COM_ports)
        
        description = ['']*len(COM_str)
        for i in range(0,len(COM_ports)):
            COM_str[i] = COM_ports[i].device
            description[i] = COM_ports[i].description
        if debug:
            COM_str = COM_str + [DUMMY_PORT]
            description = description + [DUMMY_DESCRIPTION]

        return COM_str,description
    
    @staticmethod
    def format_duty(ident: str, duty: int) -> str:
        return f"<{ident},{duty}>"
    @staticmethod
    def unformat_duty(str_in: str) -> tuple[str,int]:
        items = str_in.removeprefix("<").removesuffix(">").split(",")
        return (items[0],int(items[1]))
    @staticmethod
    def unformat_speeds(str_in: str) -> list[tuple[str,float]]:
        # TODO: The logic for interpreting the serial speed readings is in async_serialreader, but it likely should be handled by the serial interface
        # In this way, the formatting protocols for writing and reading from the microcontroller are solely handled by GenericInterface
        raise NotImplementedError("Speed decoding has not been implemented in GenericInterface yet")


class InterfaceException(BaseException):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)