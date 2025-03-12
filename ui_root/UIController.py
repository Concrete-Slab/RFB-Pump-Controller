from ui_root import UIRoot, EventFunction, StateFunction, QueueFunction, CallbackRemover, Page, AlertBoxBase, AlertBox
from threading import Event
import queue
from typing import TypeVar, Callable, Any, Dict, ParamSpec, Type
import warnings
from support_classes import SharedState
import inspect

T = TypeVar("T")
Q = TypeVar("Q")

class UIEvent:
    pass

E = TypeVar("E", bound=UIEvent)

def event_group(cls):
    for name, attr in cls.__dict__.items():
        if inspect.isclass(attr) and not issubclass(attr.__class__,UIEvent):
            new_class = type(name, (attr, UIEvent), dict(attr.__dict__))
            setattr(cls,name,new_class)
    return cls

class UIController:

    def __init__(self,root: UIRoot,debug = False):
        super().__init__()
        self.__root = root
        self.debug = debug
        self.__event_listeners: Dict[Type[UIEvent],list[Callable[[Any],None]]] = {}

    # PROTECTED METHODS
    # def _nextpage(self,key,*args,**kwargs):
    #     self.__root.switch_page(key,*args,**kwargs)

    def _back(self):
        self.__root.back_page()

    def _next_page(self,page: Page):
        self.__root.switch_page(page)

    def _back_custom(self,page: Page):
        self.__root.back_custom(page)

    def _add_event(self, event: Event, callback: EventFunction,single_call=False) -> CallbackRemover:
        return self.__root.register_event(event,callback,single_call=single_call)
    
    def _add_state(self, state: SharedState[T], callback: StateFunction[T], single_call = False) -> CallbackRemover:
        return self.__root.register_state(state,callback,single_call = single_call)
    
    def _add_queue(self, qu: queue.Queue[Q], callback: QueueFunction[Q], single_call = False) -> CallbackRemover:
        return self.__root.register_queue(qu,callback, single_call = single_call)
    
    def _create_alert(self,toplevel: AlertBox):
        # alert = toplevel(self.__root,self,*args,on_success = on_success,on_failure = on_failure,**kwargs)
        alert = toplevel.create(self.__root)
        alert.focus_set()
        return alert
    
    # PUBLIC METHODS
    def add_listener(self,event_type: Type[E], callback: Callable[[E],None]|list[Callable[[E],None]]) -> Callable[[], None]:
        if callback is list:
            try:
                self.__event_listeners[event_type] = self.__event_listeners[event_type] + callback
            except ValueError:
                self.__event_listeners[event_type] = callback
            return lambda: self.__unregister_list(event_type,callback)
        else:
            try:
                self.__event_listeners[event_type].append(callback)
            except KeyError:
                self.__event_listeners[event_type] = [callback]
            return lambda: self.__unregister_single(event_type,callback)

    def notify_event(self,event: UIEvent) -> None:
        if event.__class__ in self.__event_listeners.keys():
            for fun in self.__event_listeners[event.__class__]:
                fun(event)

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
