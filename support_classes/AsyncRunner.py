import asyncio
import threading
from typing import Coroutine, Any, TypeVar, Callable, Dict, Iterable
from concurrent.futures import Future
from abc import ABC, abstractmethod
from .Teardown import Teardown

T = TypeVar("T")

class AsyncRunner(ABC):

    # Class that has its own threaded asyncio event loop
    # Used for a class that wants to call async methods from synchronous code (e.g. a main thread that runs tkinter)
    # When the class is constructed, a new thread is created with its own event loop
    # the run_async method calls coroutines to this separate thread, where they enter the event loop
    # to end the loop and shut down the thread, call the stop_event_loop method

    def __init__(self,*args,**kwargs) -> None:
        super().__init__()
        self.__loop = asyncio.new_event_loop()
        self.__thread = threading.Thread(target=self.__start_event_loop,args=(self.__loop,))
        self.join_event = threading.Event()
        self.__active_coroutines: set[asyncio.Future] = set()
        self.__thread.start()

    def __start_event_loop(self, loop: asyncio.BaseEventLoop):
        asyncio.set_event_loop(loop)
        loop.run_forever()
        # ---------------------------------- #
        # Teardowns: after the loop is stopped
        loop.close()
        # signal that the thread is ready to be joined
        self.join_event.set()
        # run the asynchronous teardown function in a new temporary loop
        # teardowns = self._async_teardowns()
        # temp_loop = asyncio.new_event_loop()
        # asyncio.set_event_loop(temp_loop)
        # try:
        #     temp_loop.run_until_complete(asyncio.gather(*teardowns))
        # finally:
        #     # close the temporary loop
        #     temp_loop.stop()
        #     temp_loop.close()
        

    def run_async(self, coroutine: Coroutine[Any,Any,T], callback: Callable[[Future[T]],None] | list[Callable[[Future[T]],None]] = None) -> Future[T]:
        # Returns a future:
        # Assign a callback on completion for the calling thread with asyncio.Future.add_done_callback()
        try:
            future = asyncio.run_coroutine_threadsafe(coroutine,self.__loop)
            # register callback function(s) if they are provided
            if callback is not None and isinstance(callback,list):
                for cb in callback:
                    future.add_done_callback(cb)
            elif callback is not None:
                future.add_done_callback(callback)
            
            # Finally, register the future with the __active_coroutines set:
            self.__active_coroutines.add(future)
            future.add_done_callback(self.__active_coroutines.remove)

            return future
        except BaseException as e:
            self.stop_event_loop()
            raise e
        
    def run_sync(self, callable: Callable[[None],Any], args: Iterable[Any] = None):
        try:
            self.__loop.call_soon_threadsafe(callable,*args)
            #
        except Exception as e:
            print(e)
    
    def stop_event_loop(self, now=False):

        async def wait_for_completion():
            try:
                
                if self.__active_coroutines:
                    asyncio_futs: set[asyncio.Future] = set()
                    for conc_fut in self.__active_coroutines:
                        asyncio_futs.add(asyncio.wrap_future(conc_fut))
                    # Finish all running coroutines
                    await asyncio.gather(*asyncio_futs)
                    # Finish all teardown coroutines
                    astd = self._async_teardowns()
                    await asyncio.gather(*astd)
                    self._sync_teardown()
            finally:
                self.__loop.stop()
        
        if self.__loop.is_running():
            if now:
                # abruptly end the loop without waiting for coroutines to finish
                self.__loop.call_soon_threadsafe(self.__loop.stop)
            else:
                # wait for all futures in __active_coroutines to complete and then shut the loop
                asyncio.run_coroutine_threadsafe(wait_for_completion(), self.__loop)
        # ensure thread.join is not called from the asyncio thread, which would cause deadlock
        if threading.current_thread() is threading.main_thread():
            self.__thread.join()

    @abstractmethod
    def _async_teardowns(self) -> Iterable[Coroutine[None,None,None]]:
        """Async methods to be called once the loop has shut down. Avoids race condition from calling them before loop shuts and hoping they will be run before call_soon initiates shutdown"""
        pass

    @abstractmethod
    def _sync_teardown(self) -> None:
        """Sync methods to be called after async teardowns complete"""
        pass 
