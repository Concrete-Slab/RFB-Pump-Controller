from typing import Optional, Tuple, Union, TypeVar, Callable, Dict
import customtkinter as ctk
from queue import Queue
from typing import Callable,Any
from support_classes import SharedState
import warnings
import threading
import copy

POLL_REFRESH_TIME_MS = 500 # milliseconds between polls of the GUI thread

# Help with typing annotation for page functions
PageFunction = Callable[...,ctk.CTkFrame]
def page(fun: PageFunction) -> PageFunction:
    return fun

EventFunction = Callable[[None],None]
def eventcallback(evf: EventFunction) -> EventFunction:
    return evf
T = TypeVar("T")
StateFunction = Callable[[T],None]
def statecallback(stf: StateFunction) -> StateFunction:
    return stf

CallbackRemover = Callable[[],None]

class UIRoot(ctk.CTk):
    def __init__(self, fg_color: str | Tuple[str, str] | None = None, **kwargs):
        super().__init__(fg_color, **kwargs)
        self.__states: Dict[SharedState[Any],list[tuple[StateFunction[Any],bool]]] = {}
        self.__events: Dict[threading.Event, list[tuple[EventFunction,bool]]] = {}
        self.__pages: Dict[str, PageFunction] = {}
        self.__current_frame: ctk.CTkFrame = None
        self.__poll()

    def register_event(self, event: threading.Event, callback: EventFunction, single_call = False) -> CallbackRemover:
        new_tuple = (callback, single_call)
        try:
            self.__events[event].append(new_tuple)
        except KeyError:
            self.__events = {**self.__events,
                            event: [new_tuple]
                            }
        def __unregister_single():
            try:
                self.__events[event].remove(new_tuple)
                if len(self.__events[event]) == 0:
                    self.__events.pop(event)
            except (IndexError,ValueError):
                warnings.warn(str(event.__hash__()) + " event has already been removed")
        return __unregister_single

    def register_state(self,state: SharedState[T], callback: StateFunction[T], single_call = False) -> CallbackRemover:
        new_tuple = (callback, single_call)
        try:
            self.__states[state].append(new_tuple)
        except:
            self.__states = {**self.__states,
                            state: [new_tuple]
                            }
        def __unregister_single():
            try:
                self.__states[state].remove(new_tuple)
                if len(self.__states[state]) == 0:
                    self.__states.pop(state)
            except (ValueError, IndexError):
                warnings.warn(str(state.__hash__()) + " queue has already been removed")
        return __unregister_single

    # KEY PART: modify the event loop of tkinter to perform polling and event callbacks before updating the UI
    def __poll(self):
        # run queue callbacks
        states_dict = copy.copy(self.__states)
        for sharedstate in states_dict.keys():
            val = sharedstate.get_value()
            if val is not None:
                # if val is not none, it has been updated since last check
                # check through each callback tuple in the shared state
                for tup in states_dict[sharedstate]:
                    # run the callback
                    tup[0](val)
                    # if the callback is set to only run once, remove it
                    if tup[1]:
                        self.__states[sharedstate].remove(tup)
                        if len(self.__states[sharedstate])==0:
                            self.__states.pop(sharedstate)
        # delete the temporary copy
        del states_dict


        # run event callbacks
        events_dict = copy.copy(self.__events)
        for event in events_dict.keys():
            if event.is_set():
                # run callbacks for the event
                for tup in events_dict[event]:
                    tup[0]()
                    if tup[1]:
                        self.__events[event].remove(tup)
                        if len(self.__events[event])==0:
                            self.__events.pop(event)
                # clear the event
                event.clear()
        del events_dict
        self.after(POLL_REFRESH_TIME_MS,self.__poll)

    def add_page(self,key: str,fun: PageFunction):
        if key not in self.__pages.keys():
            self.__pages = {**self.__pages,
                            key: fun,
                            }
        else:
            raise UIError(f"Attempted to add page \"{key}\" which already existed")
    
    def switch_page(self, key: str, *args, **kwargs):
        try:
            page_frame = self.__pages[key](*args,**kwargs)
            if self.__current_frame is not None:
                self.__current_frame.destroy()
            self.__current_frame = page_frame
            self.__current_frame.grid()
        except KeyError:
            raise UIError(f"Page \"{key}\" does not exist")
        # TODO catch other errors


class UIError(KeyError):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)