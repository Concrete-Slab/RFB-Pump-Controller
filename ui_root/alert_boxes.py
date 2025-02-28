from typing import Callable, ParamSpec, Generic, TypeVar
import threading
from ui_root import UIRoot, EventFunction, CallbackRemover, StateFunction
from support_classes import SharedState
import customtkinter as ctk

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