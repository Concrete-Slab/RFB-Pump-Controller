from serial_interface import GenericInterface, InterfaceException, DummyInterface, SerialInterface
from support_classes.settings_interface import Settings, modify_settings, read_setting
from ui_root import UIRoot, UIController
from pump_control import Pump, PumpState, ErrorState, ReadyState, LoadingState
from .PROFILE_SELECT_EVENTS import PSEvents
from microcontroller import MicrocontrollerProfile, read_profiles
from ui_pages import ProfileManager, PumpController


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
                elif isinstance(state,LoadingState):
                    self.notify_event(PSEvents.NotifyInfo(state.info))
                
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
            raise InterfaceException(f"""Port "{profile.serial_port}" could not be found""")
        return False
        
    
    def __remove_root_callbacks(self):
        for cb in self.__root_callbacks:
            cb()

