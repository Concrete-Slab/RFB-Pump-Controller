from ui_root import UIRoot, EventFunction, StateFunction, CallbackRemover
import customtkinter as ctk
from threading import Event
from queue import Queue
from typing import TypeVar, Callable, Any, Dict
import warnings
from support_classes import SharedState


class UIController:

    def __init__(self,root: UIRoot):
        super().__init__()
        self.__root = root
        self.__event_listeners: Dict[str,list[Callable[[Any],None]]] = {}

    # PROTECTED METHODS
    def _nextpage(self,key,*args,**kwargs):
        self.__root.switch_page(key,*args,**kwargs)

    def _add_event(self, event: Event, callback: EventFunction,single_call=False) -> CallbackRemover:
        return self.__root.register_event(event,callback,single_call=single_call)
    
    T = TypeVar("T")
    def _add_state(self, state: SharedState[T], callback: StateFunction[T]):
        return self.__root.register_state(state,callback)
    
    def _create_alert(self,toplevel: Callable[...,ctk.CTkToplevel],*args,**kwargs):
        alert = toplevel(self.__root,self,*args,**kwargs)
        alert.focus_set()
        return alert
    
    # PUBLIC METHODS
    def  add_listener(self,key,callback: Callable[[Any],None]|list[Callable[[Any],None]]) -> Callable[[], None]:
        if callback is list:
            try:
                self.__event_listeners[key] = self.__event_listeners[key] + callback
            except ValueError:
                self.__event_listeners[key] = callback
            return lambda: self.__unregister_list(key,callback)
        else:
            try:
                self.__event_listeners[key].append(callback)
            except KeyError:
                self.__event_listeners[key] = [callback]
            return lambda: self.__unregister_single(key,callback)
        
    def notify_event(self,key,*args,**kwargs) -> None:
        if key in self.__event_listeners.keys():
            for fun in self.__event_listeners[key]:
                fun(*args,**kwargs)

    def __unregister_list(self,key,callbacks: list[Callable[[Any],None]]):
        for cb in callbacks:
            try:
                self.__event_listeners[key].remove(cb)
            except ValueError:
                warnings.warn(str(cb) + " callback was already unregistered")

    def __unregister_single(self,key,callback):
        try:
            self.__event_listeners[key].remove(callback)
        except ValueError:
            warnings.warn(str(callback) + " callback was already unregistered")