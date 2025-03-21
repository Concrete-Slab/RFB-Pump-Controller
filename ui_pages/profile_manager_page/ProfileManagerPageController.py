from ui_pages import ProfileEdit
from microcontroller import read_profiles, overwrite_profiles, InvalidProfileException
from .PROFILE_MANAGER_EVENTS import PrEvents
from support_classes import PumpConfig
from ui_root import UIController

class ProfileManagerPageController(UIController):

    def __init__(self, root, debug=False):
        super().__init__(root, debug)

        self.__current_profiles = []
        self.add_listener(PrEvents.RequestProfiles,self.__get_profiles)
        self.add_listener(PrEvents.Back,lambda event: self._back())
        self.add_listener(PrEvents.NewProfile,lambda event: self._next_page(ProfileEdit(None,PumpConfig.allowable_values)))
        self.add_listener(PrEvents.EditProfile,lambda event: self._next_page(ProfileEdit(event.profile_name,PumpConfig.allowable_values)))
        self.add_listener(PrEvents.DeleteProfile,self.__delete_profile)

    def __delete_profile(self,event: PrEvents.DeleteProfile):
        profile_names = [p.profile_name for p in self.__current_profiles]
        if event.profile_name not in profile_names:
            self.notify_event(PrEvents.Error(ValueError(f"{event.profile_name} not found in profile list")))
            return
        idx = profile_names.index(event.profile_name)
        self.__current_profiles.pop(idx)
        profile_names.pop(idx)
        try:
            overwrite_profiles(self.__current_profiles)
        except InvalidProfileException as ipe:
            self.notify_event(PrEvents.Error(ipe))
        self.notify_event(PrEvents.UpdateProfiles(profile_names))

    def __get_profiles(self, event: PrEvents.RequestProfiles):
        new_list = read_profiles(self.debug)
        if new_list != self.__current_profiles:
            self.__current_profiles = new_list
        self.notify_event(PrEvents.UpdateProfiles([p.profile_name for p in self.__current_profiles]))

