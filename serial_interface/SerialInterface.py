from .GenericInterface import GenericInterface, InterfaceException
from serial import Serial,SerialException,SerialTimeoutException
from concurrent.futures import ThreadPoolExecutor
import asyncio
import serial_asyncio

class SerialInterface(GenericInterface):

    def __init__(self,port: str,baudrate: int = 9600,**kwargs) -> None:
        super().__init__(port,baudrate=baudrate,**kwargs)
        self.is_established = False
        self.port = port
        try:
            Serial(port)
        except SerialException:
            raise InterfaceException("Serial port not found")
        self.reader: asyncio.StreamReader = None
        self.writer: asyncio.StreamWriter = None

    async def establish(self):
        if not self.is_established:
            try:
                self.reader, self.writer= await serial_asyncio.open_serial_connection(url=self.port)
                self.is_established = True
            except FileNotFoundError:
                raise InterfaceException("Serial port not found")

    def close(self):
        if self.is_established:
            self.writer.close()
            self.is_established = False

    async def readbuffer(self) -> str:
        if self.is_established:
            return (await self.reader.readline()).decode('utf-8').strip().rstrip("\n").rstrip("\r")
        else:
            raise InterfaceException("Interface not established")

    async def write(self,val: str):
        if self.is_established:
            try:
                val_send = val + "\r\n"
                await asyncio.wait_for(self.writer.write(val.encode('utf-8')),timeout=1)
            except asyncio.TimeoutError:
                raise InterfaceException("Write timeout")
        else:
            raise InterfaceException("Interface not established")
        