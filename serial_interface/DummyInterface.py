from .GenericInterface import GenericInterface, InterfaceException
import asyncio
import random

class DummyInterface(GenericInterface):
    # Test class for serial interfaces

    def __init__(self,port,**kwargs):
        super().__init__(port,**kwargs)
        self.port=port

    async def establish(self):
        await asyncio.sleep(1.0)
        # raise InterfaceException("HAHAHAHAHAHAHA")

    async def readbuffer(self) -> str:
        await asyncio.sleep(1)
        # raise InterfaceException
        out = [""]*6
        for i in range(0,6):
            out[i] = str(random.random()*12300)
        outstr = ",".join(out)
        return outstr
    
    async def write(self,val: str):
        await asyncio.sleep(0.1)
        print("Writing",val)

    def close(self):
        pass