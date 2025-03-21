from ui_root import UIRoot, MVPPage
from .ProfileSelectController import ProfileSelectController
from .ProfileSelectPage import ProfileSelectPage

class ProfileSelect(MVPPage):
    def create(self,root: UIRoot):
        root.title("Microcontroller Profile Select")
        self.controller = ProfileSelectController(root,debug=root.debug)
        return ProfileSelectPage(root,self.controller)