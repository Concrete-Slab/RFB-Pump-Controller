from typing import Tuple, TypeVar, Callable, Dict, ParamSpec, Generic
import customtkinter as ctk
from typing import Callable,Any
from support_classes import SharedState
import threading
import copy
from abc import ABC, abstractmethod

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
    def __init__(self, debug=False, fg_color: str | Tuple[str, str] | None = None, **kwargs):
        super().__init__(fg_color, **kwargs)
        self.debug = debug
        self.__states: Dict[SharedState[Any],list[tuple[StateFunction[Any],bool]]] = {}
        self.__events: Dict[threading.Event, list[tuple[EventFunction,bool]]] = {}
        self.__page_hierarchy: list[Page] = []
        self._alert_boxes: list[AlertBox] = []
        self.__current_frame: ctk.CTkFrame|None = None
        self.protocol("WM_DELETE_WINDOW", self._on_closing)
        self.__poll()

    def _on_closing(self):
        self.withdraw()
        self.quit()

    def register_event(self, event: threading.Event, callback: EventFunction, single_call = False) -> CallbackRemover:
        new_tuple = (callback, single_call)
        if event in self.__events.keys():
            self.__events[event].append(new_tuple)
        else:
            self.__events = {
                **self.__events,
                event: [new_tuple]
            }
            
        def __unregister_single(ev = event, tp = new_tuple):
            try:
                self.__events[ev].remove(tp)
                if len(self.__events[ev]) == 0:
                    self.__events.pop(ev)
            except (IndexError,ValueError):
                # warnings.warn(str(ev.__hash__()) + " event has already been removed")
                pass
        return __unregister_single

    def register_state(self,state: SharedState[T], callback: StateFunction[T], single_call = False) -> CallbackRemover:
        new_tuple = (callback, single_call)
        if state in self.__states.keys():
            self.__states[state].append(new_tuple)
        else:
            self.__states = {
                **self.__states,
                state: [new_tuple]
            }
        def __unregister_single(st = state, tp = new_tuple):
            try:
                self.__states[st].remove(tp)
                if len(self.__states[st]) == 0:
                    self.__states.pop(st)
            except (ValueError, IndexError,KeyError):
                # warnings.warn(str(st.__hash__()) + " queue has already been removed")
                pass
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

    def __attach_frame(self,page_frame: ctk.CTkFrame) -> None:
        if self.__current_frame is not None:
            self.__current_frame.destroy()
        self.__current_frame = page_frame
        self.columnconfigure(0,weight=1)
        self.rowconfigure(0,weight=1)
        self.__current_frame.grid(row=0,column=0,padx=0,pady=0,sticky="nsew")

    def back_page(self):
        if len(self.__page_hierarchy)>0:
            # remove top page
            self.__page_hierarchy.pop()
        # load the new top page
        next_page = self.__page_hierarchy[-1]
        page_frame = next_page.create(self)
        if next_page.auto_resize:
            self.geometry(None)
        self.__attach_frame(page_frame)

    def switch_page(self, page: "Page"):
        if page.auto_resize and len(self.__page_hierarchy)>0:
            self.geometry(None)
        self.__page_hierarchy.append(page)
        page_frame = page.create(self)
        self.__attach_frame(page_frame)
        

    def destroy(self):
        for box in self._alert_boxes:
            box._destroy_quietly()
        super().destroy()

SuccessSignature = ParamSpec("SuccessSignature")

class AlertBox(ctk.CTkToplevel,Generic[SuccessSignature]):
    def __init__(self, master: UIRoot, *args, on_success: Callable[SuccessSignature,None] | None = None, on_failure: Callable[[None],None] | None = None, fg_color: str | tuple[str, str] | None = None, **kwargs):
        super().__init__(master,*args, fg_color=fg_color, **kwargs)
        self.__root = master
        self.__on_failure = on_failure
        self.__on_success = on_success
        self.__event_listeners: dict[str, list[Callable[...,None]]] = {}
        # register alert box with the root
        self.__root._alert_boxes.append(self)
        # bring alert box to front
        self.bring_forward()

    def destroy_successfully(self,*args: SuccessSignature.args, **kwargs: SuccessSignature.kwargs) -> None:
        self._destroy_quietly()
        if self.__on_success is not None:
            self.__on_success(*args,**kwargs)

    def destroy(self) -> None:
        self._destroy_quietly()
        if self.__on_failure is not None:
            self.__on_failure()

    def _destroy_quietly(self):
        if self in self.__root._alert_boxes:
            self.__root._alert_boxes.remove(self)
        super().destroy()

    def add_listener(self,event: str, callback: Callable[...,None]) -> Callable[[None],None]:
        try:
            self.__event_listeners[event].append(callback)
        except KeyError:
            self.__event_listeners[event] = [callback]
        def unregister():
            self.__event_listeners[event].remove(callback)
            if len(self.__event_listeners[event]) == 0:
                self.__event_listeners.pop(event)
        return unregister
    
    def notify_event(self,event: str,*args,**kwargs) -> None:
        if event in self.__event_listeners.keys():
            for cb in self.__event_listeners[event]:
                cb(*args,**kwargs)

    def _add_event(self, event: threading.Event, callback: EventFunction,single_call=False) -> CallbackRemover:
        return self.__root.register_event(event,callback,single_call=single_call)
    
    T = TypeVar("T")
    def _add_state(self, state: SharedState[T], callback: StateFunction[T]):
        return self.__root.register_state(state,callback)

    def bring_forward(self):
        self.attributes('-topmost', 1)
        self.after(400,lambda: self.attributes('-topmost', 0))

    def generate_layout(self,*segment_names: list[str],confirm_command: Callable[[None],None] = lambda: None) -> list[ctk.CTkFrame]:
        nFrames = len(segment_names)
        cols = list(range(0,nFrames+1))
        self.columnconfigure(cols,weight=1)
        self.rowconfigure([0,1],weight=1)
        frmlst = [ctk.CTkFrame(self)]*nFrames
        for col_number,segment_name in enumerate(segment_names):
            # generate the segment
            current_frame = ctk.CTkFrame(self)
            current_frame.columnconfigure([1],weight=1)
            current_frame.rowconfigure([1],weight=1)
            # add a label
            lbl = ctk.CTkLabel(current_frame,text=segment_name)
            lbl.grid(row=0,column=0,columnspan=2,padx=10,pady=5,sticky="nsew")
            # add a frame to add items to later
            items_frame = ctk.CTkFrame(current_frame)
            frmlst[col_number] = items_frame
            items_frame.grid(row=1,column=0,padx=0,pady=0,sticky="nsew")
            # add the segment to the view
            current_frame.grid(row=0,column=col_number,padx=10,pady=5,sticky="nsew")
        # add a "Confirm" and "Cancel" button to the base of the view
        confirm_button = ctk.CTkButton(self,text="Confirm",command=confirm_command)
        confirm_button.grid(row=1,column=1,padx=10,pady=5,sticky="nse")
        cancel_button = ctk.CTkButton(self,text="Cancel",command=self.destroy)
        cancel_button.grid(row=1,column=0,padx=10,pady=5,sticky="nsw")
        # return the frames for other code to add items to
        return frmlst


class Page(ABC):

    def __init__(self, auto_resize=True):
        super().__init__()
        self.auto_resize=auto_resize
    
    @abstractmethod
    def create(self, root: UIRoot) -> ctk.CTkFrame:
        pass


class UIError(KeyError):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)