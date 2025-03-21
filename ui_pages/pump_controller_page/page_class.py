from ui_root import MVPPage
from pump_control import Pump
from .ControllerPageController import ControllerPageController
from .ControllerPage import ControllerPage

class PumpController(MVPPage):

    def __init__(self, pump: Pump, auto_resize=True):
        super().__init__(auto_resize=auto_resize)
        self.pump = pump

    def create(self, root):
        root.title("RFB Pump Control")
        self.controller = ControllerPageController(root,self.pump)
        page_process_dict = {process_id:(process_obj.name,process_obj.has_settings) for process_id,process_obj in self.controller.PROCESS_MAP.items()}
        return ControllerPage(root,self.controller,page_process_dict)
    
    