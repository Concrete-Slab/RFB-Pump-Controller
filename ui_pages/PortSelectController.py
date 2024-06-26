from typing import Any
from serial_interface import GenericInterface, InterfaceException,SUPPORTED_INTERFACES, DEBUG_SUPPORTED_INTERFACES
from support_classes.settings_interface import Settings, modify_settings
from .UIController import UIController
from ui_root import UIRoot
from pump_control import Pump, PumpState, ErrorState, ReadyState
from .PAGE_EVENTS import PSEvents


class PortSelectController(UIController):
    
    def __init__(self,root: UIRoot,*args,debug=False,**kwargs) -> None:
        super().__init__(root,debug=debug)
        self.__root_callbacks = []
        self.__current_ports = []
        if debug:
            self.__supported_interfaces = DEBUG_SUPPORTED_INTERFACES
        else:
            self.__supported_interfaces = SUPPORTED_INTERFACES
        self.add_listener(PSEvents.UPDATE_PORTS,self.__update_serial_list)
        self.add_listener(PSEvents.SERIAL_CONFIG,self.__serial_config)
        self.add_listener(PSEvents.UPDATE_INTERFACES,self.__update_interface_list)

    def __update_serial_list(self):
        new_list,descriptions = GenericInterface.get_serial_ports(self.debug)
        if sorted(new_list)!=sorted(self.__current_ports):
            self.__current_ports = new_list
            self.notify_event(PSEvents.NEW_PORTS,new_list,descriptions)

    def __update_interface_list(self):
        self.notify_event(PSEvents.NEW_INTERFACES,list(self.__supported_interfaces.keys()),None)

    def __serial_config(self,interface_name,port,**kwargs):
        try:
            interface = self.__supported_interfaces[interface_name](port,**kwargs)
            #TODO this is blocking, but it is probably alright in this case?
            # asyncio.run(interface.establish())
            pump = Pump(interface)
            remove_event_callback = self._add_event(pump.join_event,pump.stop_event_loop,single_call=True)

            def __on_response(state: PumpState):
                if isinstance(state,ReadyState):
                    self.__remove_root_callbacks()
                    self._nextpage("pump_control_page",pump)
                elif isinstance(state,ErrorState):
                    self.notify_event(PSEvents.ERROR,state.error)
                    self.__remove_root_callbacks()
                
                
            remove_queue_callback = self._add_state(pump.state,__on_response)

            self.__root_callbacks = self.__root_callbacks + [remove_queue_callback]


            pump.initialise()

            # everything has worked! save the settings if they are not debug-specific:
            modifications: dict[Settings,Any] = {}
            ports,_ = GenericInterface.get_serial_ports()
            if port in ports:
                modifications = {Settings.RECENT_SERIAL_PORT:str(port)}
            if interface_name in SUPPORTED_INTERFACES.keys():
                modifications = {**modifications,Settings.RECENT_SERIAL_INTERFACE:str(interface_name)}
            modify_settings(modifications)
        except KeyError:
            self.notify_event(PSEvents.ERROR,NotEstablishedException("Selected interface not available"))
        except InterfaceException as e:
            self.notify_event(PSEvents.ERROR,e)

    def __remove_root_callbacks(self):
        for cb in self.__root_callbacks:
            cb()

class NotEstablishedException(BaseException):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)
