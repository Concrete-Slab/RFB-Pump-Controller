import customtkinter as ctk
from ui_root import UIRoot, page
from ui_pages import *
from pump_control import Pump, PumpNames
from support_classes import TDExecutor


class App(UIRoot):

    def __init__(self,*args,debug = False, **kwargs):
        super().__init__(*args, **kwargs)
        self.debug = debug
        self.add_page("port_select_page",self.port_select_page)
        self.add_page("pump_control_page",self.pump_control_page)
        self.switch_page("port_select_page")

    @page
    def port_select_page(self,*args,**kwargs) -> ctk.CTkFrame:
        controller = PortSelectController(self,*args,debug=self.debug,**kwargs)
        return PortSelectPage(self,controller,*args,**kwargs)
    
    @page
    def pump_control_page(self,pump: Pump,*args,**kwargs) -> ctk.CTkFrame:
        controller = ControllerPageController(self, pump)
        return ControllerPage(self,controller)


if __name__ == '__main__':
    application = App(debug=True)
    application.mainloop()
    TDExecutor.execute()
