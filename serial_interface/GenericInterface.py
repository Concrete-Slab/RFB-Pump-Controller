from abc import ABC, abstractmethod
import serial.tools.list_ports
import atexit

class GenericInterface(ABC):

    def __init__(self,port,**kwargs) -> None:
        # Constructors for all derived classes should have the same form
        # Any additional required parameters must be keyword arguments.
        # If a required parameter is None, then one can simply raise an InterfaceException
        #TODO maybe implement this functionality in this class so it is automatic on super() call?


        # Ensures that upon error, the exposed port(s) will close
        # This is important with serial ports, as only one program may use them at a time
        atexit.register(self.close)

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
    async def write(self,val: str):
        pass

    @staticmethod
    def get_serial_ports(debug: bool = False):
        COM_ports = serial.tools.list_ports.comports()
        COM_str = ['']*len(COM_ports)
        if debug:
            COM_str = COM_str + ["Dummy port"]
        for i in range(0,len(COM_ports)):
            COM_str[i] = COM_ports[i].device
        return COM_str


class InterfaceException(BaseException):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)