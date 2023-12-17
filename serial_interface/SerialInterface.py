from .GenericInterface import GenericInterface, InterfaceException
from serial import Serial
import asyncio
import threading
import queue
from support_classes import SharedState
import time

SERIAL_WRITE_PAUSE = 1.5
"""Seconds until a subsequent write command is sent. Allows the Teensyduino controller some processing time"""

class SerialInterface(GenericInterface):

    def __init__(self,port: str,baudrate: int = 9600,**kwargs) -> None:
        super().__init__(port,baudrate=baudrate,**kwargs)
        self.__thread_alive = threading.Event()
        self.__thread_error = SharedState[BaseException|None](None)
        self.port = port
        self.__read_queue = queue.Queue(1)
        self.__write_queue = queue.Queue()
        self.__thread = threading.Thread(target = serial_loop, args = (self.port,self.__read_queue,self.__write_queue,self.__thread_alive,self.__thread_error))
        port_desc = GenericInterface.get_serial_ports()
        if port not in port_desc[0]:
            raise InterfaceException("Serial port not found")

    async def establish(self):
        if not self.__thread_alive.is_set():
            self.__thread.start()
            successful_start = self.__thread_alive.wait(timeout=1.0)
            err = self.__thread_error.get_value()
            if not successful_start:
                self.__thread.join()
                raise InterfaceException("Serial port not found")
            elif err is not None:
                self.__thread.join()
                raise err

    def close(self):
        if self.__thread_alive.is_set():
            while not self.__write_queue.empty():
                time.sleep(0.1)
            self.__thread_alive.clear()
            self.__thread.join()

    async def readbuffer(self) -> str:
        if self.__thread_alive.is_set():
            while self.__read_queue.empty():
                await asyncio.sleep(0.1)
            return self.__read_queue.get()
        else:
            err = self.__thread_error.get_value()
            raise (InterfaceException("Interface not established") if err is None else err)

    async def write(self,val: str):
        if self.__thread_alive.is_set():
            self.__write_queue.put(val)
            await asyncio.sleep(0.1)
            while not self.__write_queue.empty():
                await asyncio.sleep(0.1)
        else:
            err = self.__thread_error.get_value()
            raise (InterfaceException("Interface not established") if err is None else err)
  
def serial_loop(port, read_queue: queue.Queue[str], write_queue: queue.Queue[str], alive_event: threading.Event, error_state: SharedState[BaseException|None]):
    serial_inst = None
    try:
        serial_inst = Serial(port,timeout=0,baudrate=9600)
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

def write_loop(serial_inst: Serial, write_queue: queue.Queue[str]):
    newwrite = not write_queue.empty()
    if newwrite:
        nextqueue = write_queue.get()
        command = get_first_command(nextqueue)
        nextqueue = nextqueue.removeprefix(command)
        if get_first_command(nextqueue) != "":
            write_queue.put(nextqueue)
        if command != "":
            serial_inst.write(command.encode())
            serial_inst.reset_output_buffer()
            print(f"Writing: {command}")
            time.sleep(SERIAL_WRITE_PAUSE)
        nextqueue = nextqueue.removeprefix(command)
        if get_first_command(nextqueue) != "":
            write_queue.put(nextqueue)
    
    

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
