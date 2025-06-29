from ui_root import UIController
from microcontroller import MicrocontrollerProfile, AutoGeneratedProfile, save_profile, read_profile, profile_names, CodeGenerationException, maybe_generate_code
from serial_interface import GenericInterface, DUMMY_PORT
from .PROFILE_EDIT_EVENTS import MEvents
import os
import platform
import subprocess


class NewProfilePageController(UIController):
    

    def __init__(self, root, debug=False):
        super().__init__(root, debug)

        self._current_ports = []

        self.add_listener(MEvents.RequestPorts,self._update_serial_list)
        self.add_listener(MEvents.Cancel,self._cancel)
        self.add_listener(MEvents.SaveAutoProfile,self._save_profile)
        self.add_listener(MEvents.SaveManualProfile,self._save_profile)
        self.add_listener(MEvents.GenerateCode,self._generate_code)

    def _cancel(self, event: MEvents.Cancel):
        self._back()

    def _update_serial_list(self, event: MEvents.RequestPorts):
        new_list,descriptions = GenericInterface.get_serial_ports(self.debug)
        if sorted(new_list)!=sorted(self._current_ports):
            self._current_ports = new_list
            self.notify_event(MEvents.UpdatePorts(new_list,descriptions))
    
    def _extract_profile(self,event: MEvents.SaveAutoProfile|MEvents.SaveManualProfile|MEvents.GenerateCode):
        if isinstance(event,MEvents.SaveAutoProfile)or isinstance(event,MEvents.GenerateCode):
            return AutoGeneratedProfile(
                event.name,
                event.serial_port,
                event.serial_port == DUMMY_PORT,
                event.pin_assignments,
                code_location=event.code_location
            )
        return MicrocontrollerProfile(
            event.name,
            event.serial_port,
            event.num_pumps,
            event.serial_port == DUMMY_PORT,
        )

    def _save_profile(self,event: MEvents.SaveAutoProfile|MEvents.SaveManualProfile):
        profile = self._extract_profile(event)
        if profile.profile_name in profile_names(debug=True): # debug is true so that it searches ALL profiles
            self.notify_event(MEvents.Error(ValueError("Profile name already in use")))
            return
        save_profile(profile)
        self._back()

    def _generate_code(self,event: MEvents.GenerateCode):
        try:
            pwd = maybe_generate_code(event.name,event.pin_assignments)
            ## open file explorer/finder/equivalent
            if platform.system() == "Windows":
                subprocess.run(["explorer.exe", "/select,", str(pwd)])
            elif platform.system() == "Darwin":  # macOS - NOT TESTED
                subprocess.run(["open", "-R", pwd])
            elif platform.system() == "Linux": # Linux - NOT TESTED
                subprocess.run(["xdg-open", os.path.dirname(pwd)])
            self.notify_event(MEvents.NotifyGenerated(pwd))
        except CodeGenerationException as cge:
            self.notify_event(MEvents.Error(cge))
        

class ProfileEditPageController(NewProfilePageController):

    def __init__(self, root, profile: str, debug=False):
        super().__init__(root, debug)
        self.__profile = read_profile(profile, debug=debug)
        self.add_listener(MEvents.RequestProfile,self._update_profile)

    def _update_profile(self, event: MEvents.RequestProfile):
        profile_event = self.__create_profile_event()
        self.notify_event(profile_event)

    def __create_profile_event(self):
        if isinstance(self.__profile,AutoGeneratedProfile):
            return MEvents.UpdateAutoprofile(
                self.__profile.profile_name,
                self.__profile.serial_port,
                self.__profile.pin_assignments,
                code_location=self.__profile.code_location,
            )
        return MEvents.UpdateManualProfile(
            self.__profile.profile_name,
            self.__profile.serial_port,
            self.__profile.num_pumps
        )
    
    def _save_profile(self,event: MEvents.SaveAutoProfile|MEvents.SaveManualProfile):
        profile = self._extract_profile(event)
        save_profile(profile)
        self._back()

    def _generate_code(self,event: MEvents.GenerateCode):
        try:
            pwd = maybe_generate_code(event.name,event.pin_assignments)
            ## open file explorer/finder/equivalent
            if platform.system() == "Windows":
                subprocess.run(["explorer.exe", "/select,", str(pwd)])
            elif platform.system() == "Darwin":  # macOS - NOT TESTED
                subprocess.run(["open", "-R", pwd])
            elif platform.system() == "Linux": # Linux - NOT TESTED
                subprocess.run(["xdg-open", os.path.dirname(pwd)])
            self.notify_event(MEvents.NotifyGenerated(pwd))
        except CodeGenerationException as cge:
            self.notify_event(MEvents.Error(cge))

    def _update_serial_list(self, event: MEvents.RequestPorts):
        new_list,descriptions = GenericInterface.get_serial_ports(self.debug)
        if self.__profile.serial_port not in new_list:
            new_list.append(self.__profile.serial_port)
            descriptions.append("Not currently available")
        if sorted(new_list)!=sorted(self._current_ports):
            self._current_ports = new_list
            self.notify_event(MEvents.UpdatePorts(new_list,descriptions))

    