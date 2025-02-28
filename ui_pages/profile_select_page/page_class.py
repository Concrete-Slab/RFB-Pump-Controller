from ui_root import UIRoot, Page
from .ProfileSelectController import ProfileSelectController
from .ProfileSelectPage import ProfileSelectPage

class ProfileSelect(Page):
    def create(self,root: UIRoot):
        controller = ProfileSelectController(root,debug=root.debug)
        return ProfileSelectPage(root,controller)