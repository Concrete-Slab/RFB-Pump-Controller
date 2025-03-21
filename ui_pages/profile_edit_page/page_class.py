from ui_root import MVPPage
from .ProfileEditPage import ProfileEditPage
from .ProfileEditPageController import ProfileEditPageController, NewProfilePageController

class ProfileEdit(MVPPage):

    def __init__(self, profile_name: str|None, pump_names: list[str], auto_resize=True):
        super().__init__(auto_resize)
        self.profile_name = profile_name
        self.is_new = profile_name is None
        self.pump_names = pump_names

    def create(self, root):
        if self.is_new:
            root.title("Create Microcontroller Profile")
            self.controller = NewProfilePageController(root,debug=root.debug)
        else:
            root.title("Edit Microcontroller Profile")
            self.controller = ProfileEditPageController(root,self.profile_name,debug=root.debug)
        return ProfileEditPage(root,self.controller,self.is_new,self.pump_names)