from .GenericInterface import InterfaceException, GenericInterface
from .SerialInterface import SerialInterface
from support_classes import PumpConfig
import random
import time
from serial import Serial

# Mocking classes that simulate behaviour of a serial port.

class DummyInterface(SerialInterface):
    def __init__(self, num_pumps: int, port: str, baudrate: int = 9600, **kwargs) -> None:
        self.__num_pumps = num_pumps
        try:
            super().__init__(port, baudrate, **kwargs)
        except InterfaceException:
            pass

    # simply redefining the serial initialiser allows us to insert the mocking "DummySerial" class into the existing serial loop
    def _serial_initialiser(self):
        return DummySerial(self.__num_pumps, self.port, baudrate=9600)



class DummySerial(Serial):
    def __init__(self, num_pumps: int, port: str | None = None, baudrate: int = 9600, bytesize: int = 8, parity: str = "N", stopbits: float = 1, timeout: float | None = None, xonxoff: bool = False, rtscts: bool = False, write_timeout: float | None = None, dsrdtr: bool = False, inter_byte_timeout: float | None = None, exclusive: float | None = None) -> None:
        names = PumpConfig.allowable_values[:num_pumps]
        self.applied_duties = {name:"0" for name in names}
        self.output_pointer = 0
        self.output = "0,"*(num_pumps-1)+"0\n"
        self._generate_output()
        self.time_of_last_input = time.time()

    @property
    def in_waiting(self) -> bool:
        if time.time()-self.time_of_last_input>=1:
            return True
        else:
            return False

    def write(self,b: bytes):
        s = b.decode()
        pmpname, duty = GenericInterface.unformat_duty(s)
        speed = str(int(int(duty)/255 * 12300))
        self.applied_duties[pmpname] = speed

    def reset_output_buffer(self) -> None:
        pass

    def reset_input_buffer(self) -> None:
        pass

    def read(self,size: int = 1) -> bytes:
        out = self.output[self.output_pointer]
        if out == "\n":
            self._generate_output()
        else:
            self.output_pointer += 1
        return out.encode()

    def _generate_output(self):
        def random_value(str_in: str):
            num_in = int(str_in)
            if num_in < 500:
                num_out = int(num_in - num_in/10 + num_in/5 * random.random())
            else:
                num_out = int(num_in - 50 + 100 * random.random())
            return str(num_out)
        outlst = [random_value(val) for val in self.applied_duties.values()]
        csv = ",".join(outlst)
        self.output = f"{csv}\n"
        self.output_pointer = 0
        self.time_of_last_input = time.time()

    def close(self):
        pass
