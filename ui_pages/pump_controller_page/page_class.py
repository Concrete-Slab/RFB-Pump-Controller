from ui_root import Page, UIRoot
from pump_control import Pump
from .ControllerPageController import ControllerPageController
from .ControllerPage import ControllerPage

class PumpController(Page):

    def __init__(self, pump: Pump, auto_resize=True):
        super().__init__(auto_resize=auto_resize)
        self.pump = pump

    def create(self, root: UIRoot):
        controller = ControllerPageController(root,self.pump)
        return ControllerPage(root,controller)