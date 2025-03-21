from ui_root import MVPPage
from .ProfileManagerPage import ProfileManagerPage
from .ProfileManagerPageController import ProfileManagerPageController

class ProfileManager(MVPPage):
    def create(self, root):
        root.title("Microcontroller Profile Manager")
        self.controller = ProfileManagerPageController(root, debug=root.debug)
        return ProfileManagerPage(root,self.controller)
    