from .GenericInterface import GenericInterface, InterfaceException
from support_classes import PumpNames
import asyncio
import random

class DummyInterface(GenericInterface):
    # Test class for serial interfaces

    def __init__(self,port,**kwargs):
        super().__init__(port,**kwargs)
        self.port=port
        self.applied_duties = {pmp:0 for pmp in PumpNames}

    async def establish(self):
        await asyncio.sleep(1.0)

    async def readbuffer(self) -> str:
        await asyncio.sleep(1)
        out = [""]*6
        for i,duty in enumerate(self.applied_duties.values):
            out[i] = str(int(duty/255*12300) + random.random()*100)
        outstr = ",".join(out)
        return outstr
    
    async def write(self,val: str):
        await asyncio.sleep(0.1)
        
        try:
            pmp = PumpNames(val[1])
            duty = int(val[3])
            self.applied_duties[pmp] = duty
        except:
            pass
        print("Writing",val)

    def close(self):
        pass