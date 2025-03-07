from typing import Callable
from .GenericInterface import GenericInterface, InterfaceException
from serial import Serial
import asyncio
import threading
import queue
from support_classes import SharedState, Timer
import time

SERIAL_WRITE_PAUSE = 2
"""Seconds until a subsequent write command is sent. Allows the microcontroller some processing time"""

class _ThreadsafeAsyncEvent(threading.Event):

    def __init__(self, event_loop: asyncio.AbstractEventLoop|None = None):
        super().__init__()
        self.__loop = event_loop
        self.async_event = asyncio.Event()

    def set_loop(self,loop: asyncio.AbstractEventLoop):
        self.__loop = loop

    def set(self):
        if self.__loop:
            self.__loop.call_soon_threadsafe(self.async_event.set)
        return super().set()
    
    def clear(self):
        if self.__loop:
            self.__loop.call_soon_threadsafe(self.async_event.clear)
        return super().clear()

class SerialInterface(GenericInterface):

    def __init__(self,port: str,baudrate: int = 9600,**kwargs) -> None:
        super().__init__(port,baudrate=baudrate,**kwargs)
        self._thread_alive = _ThreadsafeAsyncEvent()
        self._thread_error = SharedState[BaseException|None](None)
        self.port = port

        # threadsafe awaitable flag to signal when new data is on the read queue
        self._data_available = _ThreadsafeAsyncEvent()
         
        
        self._read_queue = queue.Queue(1)
        self._write_queue = queue.Queue()
        self._thread = threading.Thread(target = serial_loop, args = (self.port,self._read_queue,self._write_queue,self._thread_alive,self._thread_error,self._data_available))
        port_desc = GenericInterface.get_serial_ports()
        if port not in port_desc[0]:
            raise InterfaceException("Serial port not found")

    async def establish(self):
        # attach event loop to threadsafe events
        event_loop = asyncio.get_event_loop()
        self._thread_alive.set_loop(event_loop)
        self._data_available.set_loop(event_loop)

        if not self._thread_alive.is_set():
            self._thread.start()
            try:
                successful_start = await asyncio.wait_for(self._thread_alive.async_event.wait(),4.0)
            except TimeoutError:
                successful_start = False
            # successful_start = self._thread_alive.wait(timeout=1.0)
            err = self._thread_error.get_value()
            if not successful_start:
                self._thread_alive.clear()
                self._thread.join()
                raise InterfaceException("Serial port not found")
            elif err is not None:
                self._thread.join()
                raise err

    def close(self):
        if self._thread_alive.is_set():
            self._thread_alive.clear()
            self._thread.join()

    async def readbuffer(self) -> str:
        if self._thread_alive.is_set():
            await self._data_available.async_event.wait()
            data = self._read_queue.get()
            self._data_available.clear()
            return data
        else:
            err = self._thread_error.get_value()
            raise (InterfaceException("Interface not established") if err is None else err)

    def write(self,val: str):
        if self._thread_alive.is_set():
            self._write_queue.put(val)
        else:
            err = self._thread_error.get_value()
            raise (InterfaceException("Interface not established") if err is None else err)

  
def serial_loop(port, read_queue: queue.Queue[str], write_queue: queue.Queue[str], alive_event: _ThreadsafeAsyncEvent, error_state: SharedState[BaseException|None], data_event: _ThreadsafeAsyncEvent):
    serial_inst = None
    write_timer = Timer(SERIAL_WRITE_PAUSE)
    try:
        serial_inst = Serial(port,timeout=0,baudrate=9600)
        alive_event.set()
        while alive_event.is_set():
            ## WRITE TO PORT FROM QUEUE
            write_loop(serial_inst,write_queue,write_timer)
            ## READ FROM PORT TO QUEUE
            read_loop(serial_inst,read_queue)
            ## NOTIFY IF NEW DATA
            if not read_queue.empty():
                data_event.set()
            time.sleep(0.1)
    except BaseException as e:
        error_state.set_value(e)
    finally:
        alive_event.clear()
        flush_write_buffer(serial_inst,write_queue,write_timer)
        if serial_inst is not None:
            serial_inst.close()

def write_loop(serial_inst: Serial, write_queue: queue.Queue[str], write_timer: Timer):
    newwrite = not write_queue.empty()
    # only proceed if there are new commands AND the minimum period between writes is exceeded
    # Sometimes, the microcontroller may not be able to process a flood of write commands, so SERIAL_WRITE_PAUSE is used to implement a minimum time between writes.
    # Instead of using time.sleep(SERIAL_WRITE_PAUSE), which would block the thread (e.g. from reading speeds), this allows writes to be conditioned on elapsing SERIAL_WRITE_PAUSE since the previous write.
    if newwrite and write_timer.check():
        write_timer.reset()
        nextqueue = write_queue.get()
        command = get_first_command(nextqueue)
        nextqueue = nextqueue.removeprefix(command)
        if get_first_command(nextqueue) != "":
            write_queue.put(nextqueue)
        if command != "":
            serial_inst.write(command.encode())
            serial_inst.reset_output_buffer()
        nextqueue = nextqueue.removeprefix(command)
        if get_first_command(nextqueue) != "":
            write_queue.put(nextqueue)

def flush_write_buffer(serial_inst: Serial, write_queue: queue.Queue[str], write_timer: Timer):
    """This function runs once the thread is ready to stop. It is a simpler loop that only writes any remaining commands to the serial port"""
    while not write_queue.empty():
        write_loop(serial_inst,write_queue,write_timer)
        time.sleep(0.1)
    
    

def read_loop(serial_inst: Serial, read_queue: queue.Queue[str]):
    currentbytes = bytearray()
    while serial_inst.in_waiting:
        nextbyte = serial_inst.read()
        if len(nextbyte) == 0:
            break
        elif nextbyte in (b"\n", b"\r"):
            serial_inst.reset_input_buffer()
            if read_queue.full():
                read_queue.get()
            read_queue.put(currentbytes.decode())
            currentbytes = bytearray()
        else:
            currentbytes += nextbyte

def get_first_command(comstr: str):
    outstr = ""
    incommand = False
    for char in comstr:
        if char == "<":
            incommand=True
        elif char == ">":
            incommand = False
            outstr += char
            break
        if incommand:
            outstr += char
    if len(outstr)>0 and outstr[-1] == ">":
        return outstr
    return ""