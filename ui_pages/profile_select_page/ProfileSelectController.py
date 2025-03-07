from serial_interface import GenericInterface, InterfaceException, DummyInterface, SerialInterface
from support_classes.settings_interface import Settings, modify_settings, read_setting
from ui_root import UIRoot, UIController
from pump_control import Pump, PumpState, ErrorState, ReadyState
from .PROFILE_SELECT_EVENTS import PSEvents
from microcontroller import MicrocontrollerProfile, read_profiles
from ui_pages import ProfileManager, PumpController


# class OldPortSelectController(UIController):
    
#     def __init__(self,root: UIRoot,*args,debug=False,**kwargs) -> None:
#         super().__init__(root,debug=debug)
#         self.__root_callbacks = []
#         self.__current_ports = []
#         if debug:
#             self.__supported_interfaces = DEBUG_SUPPORTED_INTERFACES
#         else:
#             self.__supported_interfaces = SUPPORTED_INTERFACES
        
        
#         self.add_listener(PSEvents.UPDATE_PORTS,self.__update_serial_list)
#         self.add_listener(PSEvents.SERIAL_CONFIG,self.__serial_config)
#         self.add_listener(PSEvents.UPDATE_INTERFACES,self.__update_interface_list)

#     def __update_serial_list(self):
#         new_list,descriptions = GenericInterface.get_serial_ports(self.debug)
#         if sorted(new_list)!=sorted(self.__current_ports):
#             self.__current_ports = new_list
#             self.notify_event(PSEvents.NEW_PORTS,new_list,descriptions)

#     def __update_interface_list(self):
#         self.notify_event(PSEvents.NEW_INTERFACES,list(self.__supported_interfaces.keys()),None)

#     def __serial_config(self,interface_name,port,**kwargs):
#         try:
#             interface = self.__supported_interfaces[interface_name](port,**kwargs)
#             #TODO this is blocking, but it is probably alright in this case?
#             # asyncio.run(interface.establish())
#             pump = Pump(interface)
#             remove_event_callback = self._add_event(pump.join_event,pump.stop_event_loop,single_call=True)

#             def __on_response(state: PumpState):
#                 if isinstance(state,ReadyState):
#                     self.__remove_root_callbacks()
#                     #TODO remove and change
#                     self._nextpage("pump_control_page",pump)
#                 elif isinstance(state,ErrorState):
#                     self.notify_event(PSEvents.ERROR,state.error)
#                     self.__remove_root_callbacks()
                
                
#             remove_queue_callback = self._add_state(pump.state,__on_response)

#             self.__root_callbacks = self.__root_callbacks + [remove_queue_callback]

            
#             pump.initialise(6)

#             # everything has worked! save the settings if they are not debug-specific:
#             modifications: dict[Settings,Any] = {}
#             ports,_ = GenericInterface.get_serial_ports()
#             if port in ports:
#                 modifications = {Settings.RECENT_SERIAL_PORT:str(port)}
#             if interface_name in SUPPORTED_INTERFACES.keys():
#                 modifications = {**modifications,Settings.RECENT_SERIAL_INTERFACE:str(interface_name)}
#             modify_settings(modifications)
#         except KeyError:
#             self.notify_event(PSEvents.ERROR,NotEstablishedException("Selected interface not available"))
#         except InterfaceException as e:
#             self.notify_event(PSEvents.ERROR,e)

#     def __remove_root_callbacks(self):
#         for cb in self.__root_callbacks:
#             cb()

class ProfileSelectController(UIController):

    def __init__(self,root: UIRoot,*args,debug=False,**kwargs) -> None:
        super().__init__(root,debug=debug)
        self.__root_callbacks = []
        self.__current_profiles: list[MicrocontrollerProfile] = []
        

        self.add_listener(PSEvents.RequestProfiles, self.__get_profiles)
        self.add_listener(PSEvents.ConfirmProfile, self.__confirm_profile)
        self.add_listener(PSEvents.ManageProfiles,lambda event: self._next_page(ProfileManager()))

    def __get_profiles(self, event: PSEvents.RequestProfiles):
        prev_profile: str = read_setting(Settings.RECENT_MICROCONTROLLER_PROFILE)
        new_list = read_profiles(self.debug)
        if new_list != self.__current_profiles:
            self.__current_profiles = new_list
        if prev_profile not in [p.profile_name for p in new_list]:
            prev_profile = None
        self.notify_event(PSEvents.UpdateProfiles([p.profile_name for p in self.__current_profiles],prev_profile))

    def __confirm_profile(self, event: PSEvents.ConfirmProfile):
        try:
            profile = self.__get_profile_from_name(event.profile)
            
            selected_port = profile.serial_port
            num_pumps = profile.num_pumps

            if self.__requires_debug(profile):
                save_profile = False
                if not self.debug:
                    raise ValueError("Invalid profile - debug mode only")
                interface = DummyInterface(num_pumps,selected_port)
            else:
                save_profile = True
                interface = SerialInterface(selected_port)

            pump = Pump(interface)

            def __on_response(state: PumpState):
                if isinstance(state,ReadyState):
                    self.__remove_root_callbacks()
                    self._next_page(PumpController(pump))
                elif isinstance(state,ErrorState):
                    self.notify_event(PSEvents.NotifyError(state.error))
                    self.__remove_root_callbacks()
                
            remove_queue_callback = self._add_queue(pump.queue,__on_response)
            self.__root_callbacks = self.__root_callbacks + [remove_queue_callback]

            pump.initialise(num_pumps)
            
            # everything has worked! save the settings if they are not debug-specific:
            if save_profile:
                modifications = {Settings.RECENT_MICROCONTROLLER_PROFILE: event.profile}
                modify_settings(modifications)

        except (ValueError, InterfaceException) as e:
            self.notify_event(PSEvents.NotifyError(str(e)))

    def __get_profile_from_name(self, profile_name: str):
        for profile in self.__current_profiles:
            if profile.profile_name == profile_name:
                return profile
        raise ValueError("Profile not found")
    
    def __requires_debug(self, profile: str|MicrocontrollerProfile):
        if not isinstance(profile,MicrocontrollerProfile):
            profile = self.__get_profile_from_name(profile)
        port = profile.serial_port
        # if the port is not in the real serial port list, then it is a dummy port that requires debug mode for usage
        if port not in GenericInterface.get_serial_ports(debug = False)[0]:
            if port in GenericInterface.get_serial_ports(debug=True)[0]:
                return True
            raise InterfaceException("Serial Port Not Found")
        return False
        
    
    def __remove_root_callbacks(self):
        for cb in self.__root_callbacks:
            cb()


class NotEstablishedException(BaseException):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)
