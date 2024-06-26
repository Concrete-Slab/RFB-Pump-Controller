from .GenericInterface import InterfaceException
from .SerialInterface import write_loop,read_loop,SerialInterface
from support_classes import PumpNames, SharedState
import random
import threading
import queue
import time
from serial import Serial

# Mocking classes that simulate behaviour of a serial port.

class DummyInterface(SerialInterface):
    def __init__(self, port: str, baudrate: int = 9600, **kwargs) -> None:
        try:
            super().__init__(port, baudrate, **kwargs)
        except InterfaceException:
            pass
        self._SerialInterface__thread = threading.Thread(target = dummy_serial_loop, args = (self.port,self._SerialInterface__read_queue,self._SerialInterface__write_queue,self._SerialInterface__thread_alive,self._SerialInterface__thread_error))


def dummy_serial_loop(port, read_queue: queue.Queue[str], write_queue: queue.Queue[str], alive_event: threading.Event, error_state: SharedState[BaseException|None]):
    serial_inst = None
    try:
        serial_inst = DummySerial(port,timeout=0,baudrate=9600)
        alive_event.set()
        while alive_event.is_set():
            ## WRITE TO PORT FROM QUEUE
            write_loop(serial_inst,write_queue)
            ## READ FROM PORT TO QUEUE
            read_loop(serial_inst,read_queue)
            time.sleep(0.1)
    except BaseException as e:
        error_state.set_value(e)
    finally:
        alive_event.clear()
        if serial_inst is not None:
            serial_inst.close()


class DummySerial(Serial):
    def __init__(self, port: str | None = None, baudrate: int = 9600, bytesize: int = 8, parity: str = "N", stopbits: float = 1, timeout: float | None = None, xonxoff: bool = False, rtscts: bool = False, write_timeout: float | None = None, dsrdtr: bool = False, inter_byte_timeout: float | None = None, exclusive: float | None = None) -> None:
        self.applied_duties = {pmp.value:str(0) for pmp in PumpNames}
        self.output_pointer = 0
        self.output = "0,0,0,0,0,0\n"
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
        pmpname = s[1]
        speed = str(int(int(s[3:-1])/255 * 12300))
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
