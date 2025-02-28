import customtkinter as ctk
from ..ui_widgets import PumpWidget,BoolSwitch,SwitchState,ApplicationTheme,LevelBoolSwitch
from ui_root import UIController
from .CONTROLLER_EVENTS import CEvents, ProcessName
from .process_controllers import BaseProcess
from support_classes import read_settings, Settings, PumpNames, PumpConfig, PID_PUMPS
import copy


class ControllerPage(ctk.CTkFrame):

    def __init__(self, parent, controller: UIController, width: int = 200, height: int = 200, corner_radius: int | str | None = None, border_width: int | str | None = None, bg_color: str | tuple[str, str] = "transparent", fg_color: str | tuple[str, str] | None = None, border_color: str | tuple[str, str] | None = None, background_corner_colors: tuple[str | tuple[str, str]] | None = None, overwrite_preferred_drawing_method: str | None = None, **kwargs):
        super().__init__(parent, width, height, corner_radius, border_width, bg_color, fg_color, border_color, background_corner_colors, overwrite_preferred_drawing_method, **kwargs)

        self.UIcontroller = controller

        self.auto_pumps: dict[Settings,PumpNames] = read_settings(Settings.ANOLYTE_PUMP,Settings.CATHOLYTE_PUMP,Settings.ANOLYTE_REFILL_PUMP,Settings.CATHOLYTE_REFILL_PUMP)
        self.pump_map: dict[PumpNames, PumpWidget] = {}
        nColumns = len(ProcessName)
        nInitialRows = 2
        self.columnconfigure(list(range(0,nColumns)),weight=1,uniform="col")
        i=nInitialRows

        for identifier in PumpConfig().pumps:
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
        self.stop_button = ctk.CTkButton(self,
                                         text="Stop All",
                                         font=ctk.CTkFont(family=ApplicationTheme.FONT,
                                                          size=ApplicationTheme.INPUT_FONT_SIZE),
                                         text_color=ApplicationTheme.BLACK,
                                         fg_color=ApplicationTheme.ERROR_COLOR,
                                         hover_color=ApplicationTheme.GRAY,
                                         corner_radius=ApplicationTheme.BUTTON_CORNER_RADIUS,
                                         command=lambda: self.UIcontroller.notify_event(CEvents.StopAll()),
                                        )
        
        self.apply_button = ctk.CTkButton(self,
                                          text="Apply All",
                                          font=ctk.CTkFont(family=ApplicationTheme.FONT,
                                                           size=ApplicationTheme.INPUT_FONT_SIZE),
                                          text_color=ApplicationTheme.BLACK,
                                          fg_color=ApplicationTheme.GREEN,
                                          hover_color=ApplicationTheme.GRAY,
                                          corner_radius=ApplicationTheme.BUTTON_CORNER_RADIUS,
                                          command=self.__apply_all
                                        )
        self.stop_button.grid(row=1,column=0,padx=10,pady=5,sticky="ns")
        self.status_label.grid(row=1,column=1,padx=10,pady=5,sticky="ns")
        self.apply_button.grid(row=1,column=2,padx=10,pady=5,sticky="ns")

        self.process_states: dict[ProcessName,ctk.IntVar] = {}
        self.process_boxes: dict[ProcessName,BoolSwitch] = {}

        for j,process in enumerate(ProcessName):
            process_state_var = ctk.IntVar(value=0)
            if BaseProcess.instanceof(process).has_settings:
                settings_fun = lambda process_name = process: self.UIcontroller.notify_event(CEvents.OpenSettings(process_name))
            else:
                settings_fun = None
            if process == ProcessName.LEVEL:
                process_box = LevelBoolSwitch(self,process_state_var,str(BaseProcess.instanceof(process).name),state_callback=lambda state,process_name = process: self.__switch_pressed(state,process_name),settings_callback=settings_fun,ROI_callback=self.__open_ROI_selection)
                pass
            else:
                process_box = BoolSwitch(self,process_state_var,str(BaseProcess.instanceof(process).name), state_callback = lambda state, process_name = process: self.__switch_pressed(state,process_name), settings_callback = settings_fun)
            
            process_box.grid(row=0,column=len(ProcessName)-1-j,padx=10,pady=5,sticky="nsew")
            self.process_states[process] = process_state_var
            self.process_boxes[process] = process_box

        # add remaining controller listeners

        self.UIcontroller.add_listener(CEvents.Error,self.__on_error)
        self.UIcontroller.add_listener(CEvents.Ready,self.__on_ready)
        self.UIcontroller.add_listener(CEvents.ProcessStarted, lambda event: self.__set_switch_state(event.process_name,SwitchState.ON))
        self.UIcontroller.add_listener(CEvents.ProcessClosed, lambda event: self.__set_switch_state(event.process_name,SwitchState.OFF))
        self.UIcontroller.add_listener(CEvents.AutoDutySet,self.__auto_duty_set)
        self.UIcontroller.add_listener(CEvents.AutoSpeedSet,self.__auto_speed_set)
        self.UIcontroller.add_listener(CEvents.CloseSettings,lambda event: self.process_boxes[event.process_name].set_settings_button_active(True))
        self.UIcontroller.add_listener(CEvents.SettingsModified,self.__maybe_change_pumps)
        self.UIcontroller.add_listener(CEvents.CloseROISelection, self.__close_ROI_selection)

        self.UIcontroller.add_listener(CEvents.StartProcess,self.__on_levels_start)
        self.UIcontroller.add_listener(CEvents.ProcessClosed,self.__on_levels_closed)


    def __on_levels_start(self,event: CEvents.StartProcess):
        if event.process_name == ProcessName.LEVEL:
            lvlswitch: LevelBoolSwitch = self.process_boxes[ProcessName.LEVEL]
            lvlswitch.set_ROI_button_active(False,with_callback=False)

    def __on_levels_closed(self,event: CEvents.ProcessClosed):
        if event.process_name == ProcessName.LEVEL:
            lvlswitch: LevelBoolSwitch = self.process_boxes[ProcessName.LEVEL]
            lvlswitch.set_ROI_button_active(True,with_callback=False)

    def __auto_duty_set(self, event: CEvents.AutoDutySet):
        self.pump_map[event.pump_id].dutyVar.set(event.new_duty)

    def __auto_speed_set(self, event: CEvents.AutoSpeedSet):
        self.pump_map[event.pump_id].speedVar.set(event.new_speed)

    def __manual_duty_set(self,identifier:PumpNames,duty: int):
        self.UIcontroller.notify_event(CEvents.ManualDutySet(identifier,duty))

    def __open_ROI_selection(self):
        self.UIcontroller.notify_event(CEvents.OpenROISelection())
    
    def __close_ROI_selection(self, event: CEvents.CloseROISelection):
        lvlswitch: LevelBoolSwitch = self.process_boxes[ProcessName.LEVEL]
        lvlswitch.set_ROI_button_active(True)

    def __switch_pressed(self,new_state: SwitchState, switch_prefix: ProcessName):
        if new_state == SwitchState.STARTING:
            self.UIcontroller.notify_event(CEvents.StartProcess(switch_prefix))
        elif new_state == SwitchState.CLOSING:
            self.UIcontroller.notify_event(CEvents.CloseProcess(switch_prefix))

    def __set_switch_state(self,switch_prefix: ProcessName,state: SwitchState):
        self.process_states[switch_prefix].set(int(state.value))
        if switch_prefix == ProcessName.PID:
            if state == SwitchState.ON:
                self.__set_pid_colors(ApplicationTheme.AUTO_PUMP_COLOR)
            elif state == SwitchState.OFF:
                self.__set_pid_colors(ApplicationTheme.MANUAL_PUMP_COLOR)

    def __on_error(self,error_event: CEvents.Error):
        self.status_label.configure(text = f"Error: {str(error_event.err)}",text_color=ApplicationTheme.ERROR_COLOR)

    def __on_ready(self,*args):
        self.status_label.configure(text="Ready",text_color=ApplicationTheme.WHITE)
            
    def __set_pid_colors(self,new_color):
        for pmp in self.auto_pumps.values():
            if pmp is not None:
                self.pump_map[pmp].set_bgcolor(new_color)

    def __maybe_change_pumps(self, event: CEvents.SettingsModified):
        modified_settings = event.modifications
        pumps_changed = False
        new_auto_pumps = copy.copy(self.auto_pumps)
        for setting in PID_PUMPS:
            if setting in set(modified_settings.keys()):
                pumps_changed = True
                new_auto_pumps[setting] = modified_settings[setting]
        if pumps_changed:
            self.__set_pid_colors(ApplicationTheme.MANUAL_PUMP_COLOR)
            self.auto_pumps = new_auto_pumps

    def __apply_all(self):
        for pmp,widget in self.pump_map.items():
            duty = widget.apply()
            

    def destroy(self):
        # self.controller.close()
        return super().destroy()