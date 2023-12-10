import customtkinter as ctk
from .ui_widgets import PumpWidget,BoolSwitch,SwitchState,ApplicationTheme
from .UIController import UIController
from .PAGE_EVENTS import CEvents
from .process_controllers import ProcessName
from pump_control import PumpNames,PID_PUMPS



class ControllerPage(ctk.CTkFrame):

    def __init__(self, parent, controller: UIController, width: int = 200, height: int = 200, corner_radius: int | str | None = None, border_width: int | str | None = None, bg_color: str | tuple[str, str] = "transparent", fg_color: str | tuple[str, str] | None = None, border_color: str | tuple[str, str] | None = None, background_corner_colors: tuple[str | tuple[str, str]] | None = None, overwrite_preferred_drawing_method: str | None = None, **kwargs):
        super().__init__(parent, width, height, corner_radius, border_width, bg_color, fg_color, border_color, background_corner_colors, overwrite_preferred_drawing_method, **kwargs)
        
        self.UIcontroller = controller
        
        self.pump_map: dict[PumpNames, PumpWidget] = {}
        nColumns = len(ProcessName) + 2
        nInitialRows = 2
        self.columnconfigure(list(range(1,nColumns-1)),weight=1,uniform="col")
        self.columnconfigure([0,nColumns-1],weight=1)
        i=nInitialRows

        for identifier in PumpNames:
            pump = PumpWidget(self,identifier.value, duty_callback = lambda duty, ident=identifier: self.__manual_duty_set(ident,duty))
            self.pump_map[identifier] = pump
            pump.grid(row=i,column=0,columnspan=nColumns,padx=10,pady=5,sticky="nsew")
            i += 1
        self.rowconfigure([0]+list(range(nInitialRows,i)),weight=1,uniform="row")

        
        self.status_label = ctk.CTkLabel(self,
                                         text = "Ready",
                                         text_color=ApplicationTheme.WHITE,
                                         font=ctk.CTkFont(family=ApplicationTheme.FONT, 
                                                          size=ApplicationTheme.STATUS_FONT_SIZE
                                                          ),
                                         
                                        )
        self.status_label.grid(row=1,column=0,columnspan=nColumns,padx=10,pady=5)

        self.process_states: dict[ProcessName,ctk.IntVar] = {}
        self.process_boxes: dict[ProcessName,BoolSwitch] = {}

        for j,process in enumerate(ProcessName):
            process_state_var = ctk.IntVar(value=0)
            if process.value.get_instance().has_settings:
                settings_fun = lambda process_name = process: self.UIcontroller.notify_event(CEvents.OPEN_SETTINGS,process_name)
            else:
                settings_fun = None
            process_box = BoolSwitch(self,process_state_var,str(process.value.get_instance().name), state_callback = lambda state, process_name = process: self.__switch_pressed(state,process_name), settings_callback = settings_fun)
            process_box.grid(row=0,column=j+1,padx=10,pady=5,sticky="nsew")
            self.process_states[process] = process_state_var
            self.process_boxes[process] = process_box

        # TODO make this less copy/paste - maybe use a map or some kind of private class/function
        # self.pid_state = ctk.IntVar(value=0)
        # self.pid_settings = ctk.BooleanVar(value=True)
        # pid_box = BoolSwitch(self,self.pid_state,"PID", state_callback = lambda state: self.__switch_pressed(state,ProcessName.PID), settings_callback = lambda : self.__settings_pressed(ProcessName.PID))
        # pid_box.grid(row=0,column=3,padx=10,pady=5,sticky="nsew")
        # self.level_state = ctk.IntVar(value=0)
        # self.level_settings = ctk.BooleanVar(value=True)
        # level_box = BoolSwitch(self,self.level_state,"Level Sensing", state_callback = lambda state: self.__switch_pressed(state,ProcessName.LEVEL), settings_callback = lambda : self.__settings_pressed(ProcessName.LEVEL))
        # level_box.grid(row=0,column=1,padx=10,pady=5,sticky="nsew")
        # self.data_state = ctk.IntVar(value=0)
        # self.data_settings = ctk.BooleanVar(value=True)
        # data_box = BoolSwitch(self,self.data_state,"Data Logging", state_callback = lambda state: self.__switch_pressed(state,ProcessName.DATA), settings_callback = lambda : self.__settings_pressed(ProcessName.DATA))
        # data_box.grid(row=0,column=2,padx=10,pady=5,sticky="nsew")

        # add remaining controller listeners

        self.UIcontroller.add_listener(CEvents.ERROR,self.__on_error)
        self.UIcontroller.add_listener(CEvents.ERROR,self.__on_ready)
        self.UIcontroller.add_listener(CEvents.PROCESS_STARTED, lambda prefix: self.__set_switch_state(prefix,SwitchState.ON))
        self.UIcontroller.add_listener(CEvents.PROCESS_CLOSED, lambda prefix: self.__set_switch_state(prefix,SwitchState.OFF))
        self.UIcontroller.add_listener(CEvents.AUTO_DUTY_SET,self.__auto_duty_set)
        self.UIcontroller.add_listener(CEvents.AUTO_SPEED_SET,self.__auto_speed_set)

        self.UIcontroller.add_listener(CEvents.CLOSE_SETTINGS,lambda process_name: self.process_boxes[process_name].set_settings_button_active(True))

        

    def __auto_duty_set(self,identifier: PumpNames,duty: int):
        self.pump_map[identifier].dutyVar.set(duty)

    def __auto_speed_set(self,identifier: PumpNames ,speed):
        self.pump_map[identifier].speedVar.set(speed)

    def __manual_duty_set(self,identifier:PumpNames,duty: int):
        self.UIcontroller.notify_event(CEvents.MANUAL_DUTY_SET,identifier,duty)

    def __switch_pressed(self,new_state: SwitchState, switch_prefix: str):
        if new_state == SwitchState.STARTING:
            self.UIcontroller.notify_event(CEvents.START_PROCESS,switch_prefix)
        elif new_state == SwitchState.CLOSING:
            self.UIcontroller.notify_event(CEvents.CLOSE_PROCESS,switch_prefix)

    def __set_switch_state(self,switch_prefix: ProcessName,state: SwitchState):
        self.process_states[switch_prefix].set(int(state.value))
        if switch_prefix == ProcessName.PID:
            if state == SwitchState.ON:
                self.__set_pid_colors(ApplicationTheme.AUTO_PUMP_COLOR)
            elif state == SwitchState.OFF:
                self.__set_pid_colors(ApplicationTheme.MANUAL_PUMP_COLOR)
        # match switch_prefix:
        #     case ProcessName.PID:
        #         self.pid_state.set(int(state.value))
        #         if state == SwitchState.ON:
        #             self.__set_pid_colors(ApplicationTheme.AUTO_PUMP_COLOR)
        #         elif state == SwitchState.OFF:
        #             self.__set_pid_colors(ApplicationTheme.MANUAL_PUMP_COLOR)
        #     case ProcessName.LEVEL:
        #         self.level_state.set(int(state.value))
        #     case ProcessName.DATA:
        #         self.data_state.set(int(state.value))
        #     case _:
        #         raise ValueError(f"Device prefix \"{switch_prefix}\" not accounted for")


            
    def __on_error(self,error):
        self.status_label.configure(text = f"Error: {str(error)}",text_color=ApplicationTheme.ERROR_COLOR)

    def __on_ready(self):
        self.status_label.configure(text="Ready",text_color=ApplicationTheme.WHITE)
            
    def __set_pid_colors(self,new_color):
        for pmp in PID_PUMPS.values():
            if pmp is not None:
                self.pump_map[pmp].set_bgcolor(new_color)

    def destroy(self):
        # self.controller.close()
        return super().destroy()