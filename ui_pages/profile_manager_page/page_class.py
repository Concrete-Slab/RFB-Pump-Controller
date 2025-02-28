from ui_root import UIRoot, Page
from .ProfileManagerPage import ProfileManagerPage
from .ProfileManagerPageController import ProfileManagerPageController

class ProfileManager(Page):
    def create(self, root):
        controller = ProfileManagerPageController(root, debug=root.debug)
        return ProfileManagerPage(root,controller)
    