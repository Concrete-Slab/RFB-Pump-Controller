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
            transport: serial_asyncio.SerialTransport = self.writer.transport
            transport.abort()
            self.is_established = False

    async def readbuffer(self) -> str:
        if self.is_established:
            outstr = (await self.reader.readline()).decode('utf-8').strip().rstrip("\n").rstrip("\r")
            print(outstr)
            return outstr
        else:
            raise InterfaceException("Interface not established")

    async def write(self,val: str):
        if self.is_established:
            try:
                loop = asyncio.get_running_loop()
                writefut = loop.run_in_executor(None,lambda: self.writer.write(val.encode('utf-8')))
                await asyncio.wait_for(writefut,timeout=1)
            except asyncio.TimeoutError:
                raise InterfaceException("Write timeout")
            print(f"Writing: {val}")
        else:
            raise InterfaceException("Interface not established")
        