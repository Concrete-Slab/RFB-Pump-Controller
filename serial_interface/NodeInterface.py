import serial.tools.list_ports
from serial import Serial
import time
import csv
import serial
import subprocess
from multiprocessing import Process
from enum import Enum
import asyncio
from .GenericInterface import GenericInterface, InterfaceException

class NodeInterface(GenericInterface):

    # Maximum seconds without response during nodeforwarder initialisation
    node_timeout = 10
    # Time delay between nodeforwarder response checks
    node_read_period = 0.1
    # Time delay between

    def __init__(self,port: str,local_port: int = None,baud: int = 9600,buffer_size: int = 10000, **kwargs):
        super().__init__(port)
        self.node_process = Process(target=self.__open_connection)
        self.serial_port = port
        if local_port is None:
            raise InterfaceException("No local port specified to Node Forwarder")
        self.local_port = local_port
        self.baud = baud
        self.buffer = buffer_size
        self.state = NodeState.CLOSED

    def __open_connection(self):
        self.state = NodeState.STARTING
        secs_elapsed = 0
        nodescript = subprocess.Popen(['node', 'nodeforwarder.js', str(self.local_port), self.serial_port, str(self.baud), str(self.buffer)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        
        
        

    async def establish(self) -> None:
        await self.__open_connection()
            
        # 
        
        
        # script is now running. periodically check for 
            

        
                

        

    @staticmethod
    def get_ports():
        ports = serial.tools.list_ports.comports()
        ports_list = [""]*len(ports)
        print(ports[0].location)
        for i in range(0,len(ports)):
            ports_list[i] = str(ports[i])
            
        return ports_list
    

class NodeState(Enum):
    CLOSED = 1
    STARTING = 2
    RUNNING = 3
    CLOSING = 4

class NodeForwarderException(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)