import asyncio
import threading
from .GenericInterface import GenericInterface, InterfaceException
from typing import Coroutine, Any
import aiohttp

class NodeInterface(GenericInterface):

    # Maximum seconds without response during nodeforwarder initialisation
    NODE_TIMEOUT = 10

    NODE_WRITE = "/write/"

    NODE_READ = "/read/"

    NODE_SCRIPT_PATH = "./serial_interface/nodeforwarder.js"

    def __init__(self,port: str,local_port: int = None,baud: int = 9600,buffer_size: int = 10000, **kwargs):
        super().__init__(port)
        # self.node_process = Process(target=self.__open_connection)
        self.serial_port = port
        if local_port is None:
            raise InterfaceException("No local port specified to Node Forwarder")
        self.local_port = local_port
        self.__baseurl = f"http://localhost:{local_port}"
        self.baud = baud
        self.buffer = buffer_size
        self.node_process: asyncio.subprocess.Process|None = None
        self.__running_flag = threading.Event()
        self.__session: aiohttp.ClientSession | None = None
        
        



        
        

    async def establish(self) -> None:
        self.node_process = await asyncio.create_subprocess_exec('node', self.NODE_SCRIPT_PATH, str(self.local_port), self.serial_port, str(self.baud), str(self.buffer),stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        self.__session = aiohttp.ClientSession(base_url=self.__baseurl)
        response: tuple[set[asyncio.Task[bool]],set[asyncio.Task[bool]]] = await asyncio.wait((asyncio.create_task(self.__read_stdout()),asyncio.create_task(self.__read_stderr())),return_when=asyncio.FIRST_COMPLETED,timeout=5)
        done = response[0]
        pending = response[1]
        try:
            if len(done)==0:
                # no done futures, timeout exceeded.
                self.node_process.kill()
                if not self.__session.closed:
                    await self.__session.close()
                raise InterfaceException("Node connection timed out")
            for fut in done:
                if fut.result() == False:
                    self.node_process.kill()
                    if not self.__session.closed:
                        await self.__session.close()
                    raise InterfaceException("Node connection finished with error")
        finally:
            for fut in pending:
                fut.cancel()
        # No errors raised, return normally
        # start a task that will read any errors from the process.
        # this function also completes when the process completes
        # this way, we can use it to set the flag and to also ensure cleanup of self.__session from within an async function
        asyncio.create_task(self.__read_stderr())
        self.__running_flag.set()
        return
    
    async def write(self,val: str) -> None:
        if self.__running_flag.is_set():
            async with self.__session.post(self.NODE_WRITE+val) as response:
                pass
        else:
            raise InterfaceException("Connection to node server closed")

    async def readbuffer(self) -> str:
        if self.__running_flag.is_set():
            async with self.__session.get(self.NODE_READ) as response:
                buffer = await response.text()
                return buffer.rstrip("\n").rstrip("\r")
        else:
            raise InterfaceException("Connection to node server closed")

    
    def close(self):
        # this is tricky, because closing the client should be done with async code...
        if self.__running_flag.is_set():
            self.node_process.kill()


    async def __read_stderr(self) -> Coroutine[Any,Any,bool]:
        async for line in self.node_process.stderr:
            decoded_line = line.decode('utf-8').strip()
            if decoded_line != "":
                print(decoded_line)
                self.__running_flag.clear()
                if self.__session:
                    await self.__session.close()
                return False
        self.__running_flag.clear()
        if self.__session:
            await self.__session.close()
        return True
    
    async def __read_stdout(self) -> Coroutine[Any,Any,bool]:
        async for line in self.node_process.stdout:
            decoded_line = line.decode('utf-8').strip()
            if decoded_line == "open":
                return True
        self.__running_flag.clear()
        if self.__session:
            await self.__session.close()
        return False
    

class DummyNodeInterface(NodeInterface):

    NODE_SCRIPT_PATH = "./serial_interface/dummy_nodeforwarder.js"

    def __init__(self, port: str, local_port: int = None, baud: int = 9600, buffer_size: int = 10000, **kwargs):
        super().__init__(port, local_port, baud, buffer_size, **kwargs)

