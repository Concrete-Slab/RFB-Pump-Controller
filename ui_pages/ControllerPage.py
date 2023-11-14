from typing import Optional, Tuple, Union, Dict
import customtkinter as ctk
from .ui_widgets import PumpWidget,BoolSwitch,SwitchState
from .UIController import UIController
from .PAGE_EVENTS import CEvents,ProcessName


class ControllerPage(ctk.CTkFrame):

    def __init__(self, parent, controller: UIController, pumps: list[str], width: int = 200, height: int = 200, corner_radius: int | str | None = None, border_width: int | str | None = None, bg_color: str | Tuple[str, str] = "transparent", fg_color: str | Tuple[str, str] | None = None, border_color: str | Tuple[str, str] | None = None, background_corner_colors: Tuple[str | Tuple[str, str]] | None = None, overwrite_preferred_drawing_method: str | None = None, **kwargs):
        super().__init__(parent, width, height, corner_radius, border_width, bg_color, fg_color, border_color, background_corner_colors, overwrite_preferred_drawing_method, **kwargs)
        
        self.UIcontroller = controller
        
        self.pump_map: Dict[str, PumpWidget] = {}
        nColumns = 5
        nInitialRows = 1
        self.columnconfigure(list(range(1,nColumns-1)),weight=1,uniform="col")
        self.columnconfigure([0,nColumns-1],weight=1)
        i=nInitialRows

        for identifier in pumps:
            duty_cb = lambda duty: self.UIcontroller.notify_event(CEvents.MANUAL_DUTY_SET,identifier,duty)
            pump = PumpWidget(self,identifier, duty_callback = duty_cb)
            self.pump_map[identifier] = pump
            pump.grid(row=i,column=0,columnspan=nColumns,padx=10,pady=10,sticky="nsew")
            i += 1
        self.rowconfigure(list(range(0,i)),weight=1,uniform="row")


        self.pid_state = ctk.IntVar(value=0)
        self.pid_box = BoolSwitch(self,self.pid_state,"PID", state_callback = lambda state: self.__switch_pressed(state,ProcessName.PID))
        self.level_state = ctk.IntVar(value=0)
        self.level_box = BoolSwitch(self,self.level_state,"Level Sensing", state_callback = lambda state: self.__switch_pressed(state,ProcessName.LEVEL))
        self.level_box.grid(row=0,column=1,padx=10,pady=10,sticky="nsew")
        self.pid_box.grid(row=0,column=3,padx=10,pady=10,sticky="nsew")
        self.data_state = ctk.IntVar(value=0)
        self.data_box = BoolSwitch(self,self.data_state,"Data Logging", state_callback = lambda state: self.__switch_pressed(state,ProcessName.DATA))
        self.data_box.grid(row=0,column=2,padx=10,pady=10,sticky="nsew")

        # add remaining controller listeners

        self.UIcontroller.add_listener(CEvents.PROCESS_STARTED, lambda prefix: self.__set_switch_state(prefix,SwitchState.ON))
        self.UIcontroller.add_listener(CEvents.PROCESS_CLOSED, lambda prefix: self.__set_switch_state(prefix,SwitchState.OFF))
        self.UIcontroller.add_listener(CEvents.AUTO_DUTY_SET,self.__auto_duty_set)
        self.UIcontroller.add_listener(CEvents.AUTO_SPEED_SET,self.__auto_speed_set)

    def __auto_duty_set(self,identifier: str,duty):
        self.pump_map[identifier].dutyVar.set(duty)

    def __auto_speed_set(self,identifier:str ,speed):
        self.pump_map[identifier].speedVar.set(speed)

    def __switch_pressed(self,new_state: SwitchState, switch_prefix: str):
        if new_state == SwitchState.STARTING:
            self.UIcontroller.notify_event(CEvents.START_PROCESS,switch_prefix)
        elif new_state == SwitchState.CLOSING:
            self.UIcontroller.notify_event(CEvents.CLOSE_PROCESS,switch_prefix)

    def __set_switch_state(self,switch_prefix: ProcessName,state: SwitchState):
        match switch_prefix:
            case ProcessName.PID:
                self.pid_state.set(int(state.value))
            case ProcessName.LEVEL:
                self.level_state.set(int(state.value))
            case ProcessName.DATA:
                self.data_state.set(int(state.value))
            case _:
                raise ValueError(f"Device prefix \"{switch_prefix}\" not accounted for")
            

    def destroy(self):
        # self.controller.close()
        return super().destroy()