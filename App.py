from ui_root import UIRoot
from ui_pages import ProfileSelect

class App(UIRoot):

    APP_NAME = "RFB Pump Controller"

    def __init__(self,*args, debug = False, **kwargs):
        super().__init__(*args, debug=debug, **kwargs)
        self.title(self.APP_NAME)
        self.switch_page(ProfileSelect())