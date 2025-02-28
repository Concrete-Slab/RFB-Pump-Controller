from ui_root import Page
from .ProfileEditPage import ProfileEditPage
from .ProfileEditPageController import ProfileEditPageController, NewProfilePageController

class ProfileEdit(Page):

    def __init__(self, profile_name: str|None, pump_names: list[str]):
        super().__init__()
        self.profile_name = profile_name
        self.is_new = profile_name is None
        self.pump_names = pump_names

    def create(self, root):
        if self.is_new:
            controller = NewProfilePageController(root,debug=root.debug)
        else:
            controller = ProfileEditPageController(root,self.profile_name,debug=root.debug)
        return ProfileEditPage(root,controller,self.is_new,self.pump_names)