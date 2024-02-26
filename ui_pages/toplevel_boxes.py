import customtkinter as ctk
from PIL import Image
import cv2
from ui_root import UIRoot, EventFunction, StateFunction, CallbackRemover
from support_classes import capture, CaptureException, read_settings, modify_settings, Settings, PID_SETTINGS, LOGGING_SETTINGS, PumpNames, PID_PUMPS, LEVEL_SETTINGS, SharedState, Capture, PygameCapture, DEFAULT_SETTINGS, CaptureBackend, CV2Capture
# #TODO make independent of model class
# from serial_interface.SerialInterface import SERIAL_WRITE_PAUSE
from typing import Generic,ParamSpec,Callable,Any,TypeVar, Protocol
from pathlib import Path
from .ui_widgets.themes import ApplicationTheme
import threading
import copy
import pynput.keyboard as pyin
import time

SuccessSignature = ParamSpec("SuccessSignature")

class AlertBox(ctk.CTkToplevel,Generic[SuccessSignature]):
    def __init__(self, master: UIRoot, *args, on_success: Callable[SuccessSignature,None] | None = None, on_failure: Callable[[None],None] | None = None, fg_color: str | tuple[str, str] | None = None, **kwargs):
        super().__init__(master,*args, fg_color=fg_color, **kwargs)
        self.__root = master
        self.__on_failure = on_failure
        self.__on_success = on_success
        self.__event_listeners: dict[str, list[Callable[...,None]]] = {}
        # bring alert box to fromt
        self.bring_forward()
    
    def destroy_successfully(self,*args: SuccessSignature.args, **kwargs: SuccessSignature.kwargs) -> None:
        if self.__on_success is not None:
            self.__on_success(*args,**kwargs)
        super().destroy()

    def destroy(self) -> None:
        if self.__on_failure is not None:
            self.__on_failure()
        super().destroy()

    def add_listener(self,event: str, callback: Callable[...,None]) -> Callable[[None],None]:
        try:
            self.__event_listeners[event].append(callback)
        except KeyError:
            self.__event_listeners[event] = [callback]
        def unregister():
            self.__event_listeners[event].remove(callback)
            if len(self.__event_listeners[event]) == 0:
                self.__event_listeners.pop(event)
        return unregister
    
    def notify_event(self,event: str,*args,**kwargs) -> None:
        if event in self.__event_listeners.keys():
            for cb in self.__event_listeners[event]:
                cb(*args,**kwargs)

    def _add_event(self, event: threading.Event, callback: EventFunction,single_call=False) -> CallbackRemover:
        return self.__root.register_event(event,callback,single_call=single_call)
    
    T = TypeVar("T")
    def _add_state(self, state: SharedState[T], callback: StateFunction[T]):
        return self.__root.register_state(state,callback)

    def bring_forward(self):
        self.attributes('-topmost', 1)
        self.after(400,lambda: self.attributes('-topmost', 0))

    def generate_layout(self,*segment_names: list[str],confirm_command: Callable[[None],None] = lambda: None) -> list[ctk.CTkFrame]:
        nFrames = len(segment_names)
        cols = list(range(0,nFrames+1))
        self.columnconfigure(cols,weight=1)
        self.rowconfigure([0,1],weight=1)
        frmlst = [ctk.CTkFrame(self)]*nFrames
        for col_number,segment_name in enumerate(segment_names):
            # generate the segment
            current_frame = ctk.CTkFrame(self)
            current_frame.columnconfigure([1],weight=1)
            current_frame.rowconfigure([1],weight=1)
            # add a label
            lbl = ctk.CTkLabel(current_frame,text=segment_name)
            lbl.grid(row=0,column=0,columnspan=2,padx=10,pady=5,sticky="nsew")
            # add a frame to add items to later
            items_frame = ctk.CTkFrame(current_frame)
            frmlst[col_number] = items_frame
            items_frame.grid(row=1,column=0,padx=0,pady=0,sticky="nsew")
            # add the segment to the view
            current_frame.grid(row=0,column=col_number,padx=10,pady=5,sticky="nsew")
        # add a "Confirm" and "Cancel" button to the base of the view
        confirm_button = ctk.CTkButton(self,text="Confirm",command=confirm_command)
        confirm_button.grid(row=1,column=1,padx=10,pady=5,sticky="nse")
        cancel_button = ctk.CTkButton(self,text="Cancel",command=self.destroy)
        cancel_button.grid(row=1,column=0,padx=10,pady=5,sticky="nsw")
        # return the frames for other code to add items to
        return frmlst

class DataSettingsBox(AlertBox[dict[Settings,Any]]):

    ALERT_TITLE = "Data Logging Settings"

    def __init__(self, master: ctk.CTk, *args, on_success: Callable[..., None] | None = None, on_failure: Callable[[None], None] | None = None, fg_color: str | tuple[str, str] | None = None, **kwargs):
        super().__init__(master, *args, on_success=on_success, on_failure=on_failure, fg_color=fg_color, **kwargs)
        self.title(self.ALERT_TITLE)
        ## READ THE CURRENT SETTINGS
        # with open("settings.json","r") as f:
        #     settings: dict[str,Any] = dict(json.load(f))
        
        # self.__prev_logging_settings = {k:settings[k] for k in (Settings.LOG_LEVELS,Settings.LOG_PID,Settings.LOG_SPEEDS) if k in settings.keys()}
        
        self.__prev_logging_settings = read_settings(*LOGGING_SETTINGS)
        prev_log_levels: bool = self.__prev_logging_settings[Settings.LOG_LEVELS]
        prev_log_pid: bool = self.__prev_logging_settings[Settings.LOG_PID]
        prev_log_speeds: bool = self.__prev_logging_settings[Settings.LOG_SPEEDS]
        prev_log_images: bool = self.__prev_logging_settings[Settings.LOG_IMAGES]
        prev_level_directory: Path|None = self.__prev_logging_settings[Settings.LEVEL_DIRECTORY]

        try:
            self.__initial_directory = prev_level_directory.parent if prev_level_directory is not None else Path().absolute()
        except:
            self.__initial_directory = Path().absolute()
        
        switch_frame = ctk.CTkFrame(self,fg_color=self._fg_color)
        switch_frame.rowconfigure([0,1,2],weight=1,uniform="switch_rows")
        directory_frame = ctk.CTkFrame(self,fg_color=self._fg_color)
        directory_frame.rowconfigure([0,1],weight=1,uniform="directory_rows")
        directory_frame.columnconfigure(0,weight=1,uniform="directory_col0")

        def cast_b2s(state: bool):
            return "on" if state else "off"

        self.__level_var = ctk.StringVar(value = cast_b2s(prev_log_levels))
        level_switch = ctk.CTkSwitch(switch_frame,onvalue="on",offvalue="off",variable=self.__level_var,text="Level Logging",width=50)
        level_switch.grid(row=0,column=1,padx=10,pady=5,sticky="nsew")
        self.__pid_var = ctk.StringVar(value = cast_b2s(prev_log_pid))
        pid_switch = ctk.CTkSwitch(switch_frame,onvalue="on",offvalue="off",variable=self.__pid_var,text="PID Duty Logging",width=50)
        pid_switch.grid(row=1,column=1,padx=10,pady=5,sticky="nsew")
        self.__speed_var = ctk.StringVar(value = cast_b2s(prev_log_speeds))
        speed_switch = ctk.CTkSwitch(switch_frame,onvalue="on",offvalue="off",variable=self.__speed_var,text="Pump Speed Logging",width=50)
        speed_switch.grid(row=2,column=1,padx=10,pady=5,sticky="nsew")
        self.__image_var = ctk.StringVar(value = cast_b2s(prev_log_images))
        image_switch = ctk.CTkSwitch(switch_frame,onvalue="on",offvalue="off",variable=self.__image_var,text="Image Logging",width=50)
        image_switch.grid(row=3,column=1,padx=10,pady=5,sticky="nsew")

        directory_label = ctk.CTkLabel(directory_frame, text = "Data Storage Directory:")
        directory_label.grid(row=0,column=0,columnspan = 2,padx=10,pady=5,sticky="sew")
        self.__directory_var = ctk.StringVar(value=self.__initial_directory)
        directory_entry = ctk.CTkEntry(directory_frame,
                                   textvariable=self.__directory_var,
                                   justify='center',
                                   corner_radius=ApplicationTheme.BUTTON_CORNER_RADIUS)
        directory_entry.grid(row=1,column=0,padx=10,pady=5,sticky="new")
        directory_button = ctk.CTkButton(directory_frame,corner_radius=ApplicationTheme.BUTTON_CORNER_RADIUS,
                                         text = "Browse",
                                         command = self.__select_from_explorer)
        directory_button.grid(row=1,column=1,padx=10,pady=5,sticky="ne")

        self.columnconfigure([0],weight = 1, uniform = "col")
        directory_frame.grid(row=0,column=0,padx=5,pady=5,sticky="nsew")
        switch_frame.grid(row=0,column=1,padx=5,pady=5,sticky="nsew")

        confirm_button = ctk.CTkButton(self, corner_radius= ApplicationTheme.BUTTON_CORNER_RADIUS, text = "Confirm", command = self.__confirm_settings)
        cancel_button = ctk.CTkButton(self,corner_radius=ApplicationTheme.BUTTON_CORNER_RADIUS,text = "Cancel",command = self.destroy)
        confirm_button.grid(row=1,column=1,padx=5,pady=5,sticky="e")
        cancel_button.grid(row=1,column=0,padx=5,pady=5,sticky="w")
        
    def __select_from_explorer(self):
        new_directory = ctk.filedialog.askdirectory(initialdir = self.__initial_directory,mustexist=True)
        self.bring_forward()
        if new_directory != "":
            self.__directory_var.set(new_directory)
            self.__initial_directory = Path(new_directory)

    def __confirm_settings(self):
        def cast_s2b(state: str):
            return True if state == "on" else False
        
        try:
            new_logging_directory = Path(self.__directory_var.get)
        except:
            new_logging_directory = self.__initial_directory

        new_logging_settings = {
            Settings.LOG_LEVELS: cast_s2b(self.__level_var.get()),
            Settings.LOG_PID: cast_s2b(self.__pid_var.get()),
            Settings.LOG_SPEEDS: cast_s2b(self.__speed_var.get()),
            Settings.LOG_IMAGES: cast_s2b(self.__image_var.get()),
            Settings.LEVEL_DIRECTORY: (new_logging_directory / "levels"),
            Settings.PID_DIRECTORY: (new_logging_directory / "duties"),
            Settings.SPEED_DIRECTORY: (new_logging_directory / "speeds"),
            Settings.IMAGE_DIRECTORY: (new_logging_directory / "images"),
        }

    
        modifications = modify_settings(new_logging_settings)
        ## close the window by notifying of modified changes
        self.destroy_successfully(modifications)

class PIDSettingsBox(AlertBox[dict[Settings,Any]]):

    ALERT_TITLE = "PID Settings"

    def __init__(self, master: ctk.CTk, *args, on_success: Callable[..., None] | None = None, on_failure: Callable[[None], None] | None = None, fg_color: str | tuple[str, str] | None = None, **kwargs):
        super().__init__(master, *args, on_success=on_success, on_failure=on_failure, fg_color=fg_color, **kwargs)
        self.title(self.ALERT_TITLE)

        default_options = ["None"]
        for pmpname in PumpNames:
            default_options.append(pmpname.value.lower())

        pid_settings = read_settings(*PID_SETTINGS)
        pump_settings: dict[Settings,PumpNames|None] = {key:pid_settings[key] for key in PID_PUMPS}
        # an_var = ctk.StringVar(value=_json2str(pump_settings[Settings.ANOLYTE_PUMP]))
        # cath_var = ctk.StringVar(value=_json2str(pump_settings[Settings.CATHOLYTE_PUMP]))
        # an_re_var = ctk.StringVar(value=_json2str(pump_settings[Settings.ANOLYTE_REFILL_PUMP]))
        # cath_re_var = ctk.StringVar(value=_json2str(pump_settings[Settings.CATHOLYTE_REFILL_PUMP]))
        # self.__vars = [an_var,cath_var,an_re_var,cath_re_var]

        # self.columnconfigure([0,1],weight=1)
        # self.rowconfigure([0,1],weight=1)
        # pump_frame = ctk.CTkFrame(self)
        # pump_lbl = ctk.CTkLabel(pump_frame,text="Pump Assignments")
        # pump_lbl.grid(row=0,column=0,columnspan=2,padx=10,pady=5,sticky="nsew")
        # control_frame = ctk.CTkFrame(self)
        # control_lbl = ctk.CTkLabel(control_frame,text="Control Parameters")
        # control_lbl.grid(row=0,column=1,columnspan=2,padx=10,pady=5,sticky="nsew")
        # pump_frame.grid(row=0,column=0,padx=10,pady=5,sticky="nsew")
        # control_frame.grid(row=0,column=1,padx=10,pady=5,sticky="nsew")

        frame_list = self.generate_layout("Pump Assignments","Control Parameters",confirm_command=self.__confirm_selections)
        pump_frame = frame_list[0]
        control_frame = frame_list[1]

        self.pump_group = _WidgetGroup(initial_row=0)
        an_var = _make_and_group(_make_menu,
                                 pump_frame,
                                 "Anolyte Pump",
                                 Settings.ANOLYTE_PUMP,
                                 _json2str(pump_settings[Settings.ANOLYTE_PUMP]),
                                 self.pump_group,
                                 map_fun=_str2json,
                                 values=default_options
                                 )
        cath_var = _make_and_group(_make_menu,
                                 pump_frame,
                                 "Catholyte Pump",
                                 Settings.CATHOLYTE_PUMP,
                                 _json2str(pump_settings[Settings.CATHOLYTE_PUMP]),
                                 self.pump_group,
                                 map_fun=_str2json,
                                 values=default_options
                                 )
        an_re_var = _make_and_group(_make_menu,
                                 pump_frame,
                                 "Anolyte Refill Pump",
                                 Settings.ANOLYTE_REFILL_PUMP,
                                 _json2str(pump_settings[Settings.ANOLYTE_REFILL_PUMP]),
                                 self.pump_group,
                                 map_fun=_str2json,
                                 values=default_options
                                 )
        cath_re_var = _make_and_group(_make_menu,
                                 pump_frame,
                                 "Catholyte Refill Pump",
                                 Settings.CATHOLYTE_REFILL_PUMP,
                                 _json2str(pump_settings[Settings.CATHOLYTE_REFILL_PUMP]),
                                 self.pump_group,
                                 map_fun=_str2json,
                                 values=default_options
                                 )
        pump_vars = self.pump_group.get_vars()

        for i,var in enumerate(pump_vars):
            var.trace_add("write",lambda *args,index=i: self.__update_selections(index,*args))
        self.pump_group.show()

        # anolyte_selection = ctk.CTkOptionMenu(self,values=self.__default_options,variable=an_var)
        # catholyte_selection = ctk.CTkOptionMenu(self,values=self.__default_options,variable=cath_var)
        # anolyte_refill_selection = ctk.CTkOptionMenu(self,values=self.__default_options,variable=an_re_var)
        # catholyte_refill_selection = ctk.CTkOptionMenu(self,values=self.__default_options,variable=cath_re_var)
        # self.__boxes = [anolyte_selection,catholyte_selection,anolyte_refill_selection,catholyte_refill_selection]

        # an_label = ctk.CTkLabel(self,text="Anolyte Pump")
        # cath_label = ctk.CTkLabel(self,text="Catholyte Pump")
        # an_refill_label = ctk.CTkLabel(self,text="Anolyte Refill Pump")
        # cath_refill_label = ctk.CTkLabel(self,text="Catholyte Refill Pump")
        # labels = [an_label,cath_label,an_refill_label,cath_refill_label]

            # self.__boxes[i].grid(row=i,column=1,padx=10,pady=5,sticky="nsew")
            # labels[i].grid(row=i,column=0,padx=10,pady=5,sticky="nsew")
        self.control_group = _WidgetGroup(initial_row=0)
        base_duty_var = _make_and_group(_make_entry,
                                        control_frame,
                                        "Equilibrium Control Duty",
                                        Settings.BASE_CONTROL_DUTY,
                                        pid_settings[Settings.BASE_CONTROL_DUTY],
                                        self.control_group,
                                        map_fun=int,
                                        entry_validator = _validate_duty,
                                        on_return = self.__confirm_selections
                                        )
        rf_time_var = _make_and_group(_make_entry,
                                        control_frame,
                                        "Refill Time",
                                        Settings.REFILL_TIME,
                                        pid_settings[Settings.REFILL_TIME],
                                        self.control_group,
                                        map_fun=float,
                                        units="s",
                                        entry_validator = _validate_time_float,
                                        on_return = self.__confirm_selections
                                        )
        rf_duty_var = _make_and_group(_make_entry,
                                        control_frame,
                                        "Refill Duty",
                                        Settings.REFILL_DUTY,
                                        pid_settings[Settings.REFILL_DUTY],
                                        self.control_group,
                                        map_fun=int,
                                        entry_validator = _validate_duty,
                                        on_return = self.__confirm_selections
                                        )
        rf_percent_var = _make_and_group(_make_entry,
                                        control_frame,
                                        "Refill Percent Trigger",
                                        Settings.REFILL_PERCENTAGE_TRIGGER,
                                        pid_settings[Settings.REFILL_PERCENTAGE_TRIGGER],
                                        self.control_group,
                                        map_fun=int,
                                        units="%",
                                        entry_validator = _validate_percent,
                                        on_return = self.__confirm_selections
                                        )
        rf_cooldown_var = _make_and_group(_make_entry,
                                        control_frame,
                                        "Refill Cooldown Period",
                                        Settings.PID_REFILL_COOLDOWN,
                                        pid_settings[Settings.PID_REFILL_COOLDOWN],
                                        self.control_group,
                                        map_fun=float,
                                        units = "s",
                                        entry_validator = _validate_time_float,
                                        on_return = self.__confirm_selections
                                        )
        kp_var = _make_and_group(_make_entry,
                                 control_frame,
                                 "Proportional Gain",
                                 Settings.PROPORTIONAL_GAIN,
                                 pid_settings[Settings.PROPORTIONAL_GAIN],
                                 self.control_group,
                                 map_fun=float,
                                 entry_validator = _validate_gain,
                                 on_return = self.__confirm_selections)
        
        ki_var = _make_and_group(_make_entry,
                                 control_frame,
                                 "Integral Gain",
                                 Settings.INTEGRAL_GAIN,
                                 pid_settings[Settings.INTEGRAL_GAIN],
                                 self.control_group,
                                 map_fun=float,
                                 entry_validator = _validate_gain,
                                 on_return = self.__confirm_selections)
        
        kd_var = _make_and_group(_make_entry,
                                 control_frame,
                                 "Derivative Gain",
                                 Settings.DERIVATIVE_GAIN,
                                 pid_settings[Settings.DERIVATIVE_GAIN],
                                 self.control_group,
                                 map_fun=float,
                                 entry_validator = _validate_gain,
                                 on_return = self.__confirm_selections)
        
        self.control_group.show()
        


        # base_duty_label = ctk.CTkLabel(self,text="Equilibrium Control Duty")
        # rf_time_label = ctk.CTkLabel(self,text="Refill Time")
        # rf_duty_label = ctk.CTkLabel(self,text="Refill Duty")
        # rf_percent_label = ctk.CTkLabel(self,text="Refill Solvent Loss Trigger")

        # entry_labels = [base_duty_label,rf_time_label,rf_duty_label,rf_percent_label]

        # base_duty_frame = ctk.CTkFrame(self,corner_radius=0)
        # self.__base_duty_var = ctk.StringVar(value=pid_settings[Settings.BASE_CONTROL_DUTY])
        # base_duty_box = ctk.CTkEntry(base_duty_frame, textvariable=self.__base_duty_var, validate='key', validatecommand = (self.register(_validate_duty),"%P"))
        # base_duty_box.grid(row=0,column=0,padx=5,pady=5,sticky="nsew")

        # rf_time_frame = ctk.CTkFrame(self,corner_radius=0)
        # self.__rf_time_var = ctk.StringVar(value=pid_settings[Settings.REFILL_TIME])
        # rf_time_box = ctk.CTkEntry(rf_time_frame, textvariable=self.__rf_time_var, validate='key', validatecommand = (self.register(_validate_time),"%P"))
        # seconds_label = ctk.CTkLabel(rf_time_frame,text="s")
        # rf_time_box.grid(row=0,column=0,padx=5,pady=5,sticky="nsew")
        # seconds_label.grid(row=0,column=1,padx=5,pady=5,sticky="nsew")

        # rf_duty_frame = ctk.CTkFrame(self,corner_radius=0)
        # self.__rf_duty_var = ctk.StringVar(value=pid_settings[Settings.REFILL_DUTY])
        # rf_duty_box = ctk.CTkEntry(rf_duty_frame, textvariable=self.__rf_duty_var, validate='key', validatecommand = (self.register(_validate_time),"%P"))
        # rf_duty_box.grid(row=0,column=0,padx=5,pady=5,sticky="nsew")

        # rf_percent_frame = ctk.CTkFrame(self,corner_radius=0)
        # self.__rf_percent_var = ctk.StringVar(value=pid_settings[Settings.REFILL_PERCENTAGE_TRIGGER])
        # rf_percent_box = ctk.CTkEntry(rf_percent_frame, textvariable=self.__rf_percent_var ,validate='key', validatecommand = (self.register(_validate_percent),"%P"))
        # percent_label = ctk.CTkLabel(rf_percent_frame,text="%")
        # rf_percent_box.grid(row=0,column=0,padx=5,pady=5,sticky="nsew")
        # percent_label.grid(row=0,column=1,padx=5,pady=5,sticky="nsew")
        # self.__refill_entries = [rf_time_box,rf_duty_box,rf_percent_box]
        # entry_frames = [base_duty_frame,rf_time_frame,rf_duty_frame,rf_percent_frame]

        # currRow = len(self.__vars)

        # for j in range(0,len(entry_frames)):
        #     entry_labels[j].grid(row=j+currRow,column=0,padx=10,pady=5,sticky="nsew")
        #     entry_frames[j].grid(row=j+currRow,column=1,padx=5,pady=0,sticky="nsew")

        # currRow = currRow + len(entry_frames)
        
        # currRow = max(self.control_group.current_row,self.pump_group.current_row)
        # confirm_button = ctk.CTkButton(self,command=self.__confirm_selections,text="Confirm",corner_radius=ApplicationTheme.BUTTON_CORNER_RADIUS)
        # confirm_button.grid(row=currRow,column=1,padx=10,pady=5,sticky="nes")
        # cancel_button = ctk.CTkButton(self,command=self.destroy,text="Cancel",corner_radius=ApplicationTheme.BUTTON_CORNER_RADIUS)
        # cancel_button.grid(row=currRow,column=0,padx=10,pady=5,sticky="new")
        

    def __update_selections(self,var_index,*args):
        # make sure there are no duplicate selections
        vars_copy = copy.copy(self.pump_group.get_vars())
        selected_value = vars_copy.pop(var_index).get()
        if selected_value != "None":
            for var in vars_copy:
                value = var.get()
                if value == selected_value:
                    var.set("None")

        
    def __confirm_selections(self):
        # pump_settings = {
        #     Settings.ANOLYTE_PUMP: _str2json(self.__vars[0].get()),
        #     Settings.CATHOLYTE_PUMP: _str2json(self.__vars[1].get()),
        #     Settings.ANOLYTE_REFILL_PUMP: _str2json(self.__vars[2].get()),
        #     Settings.CATHOLYTE_REFILL_PUMP: _str2json(self.__vars[3].get())
        # }
        pump_settings = {var.setting:var.get_mapped() for var in self.pump_group.get_vars()}
        # final check that there are no duplicates (except None values)
        prev_values = []
        bad_values = False
        for var in self.pump_group.get_vars():
            if var.get_mapped() is not None and var.get_mapped() in prev_values:
                var.widget.configure(fg_color = ApplicationTheme.ERROR_COLOR)
                var.widget.after(1000,lambda *args: var.widget.configure(fg_color=ApplicationTheme.MANUAL_PUMP_COLOR))
                bad_values = True

            prev_values.append(var.get_mapped())
        if bad_values:
            return

        is_valid = [var.is_valid() for var in self.control_group.get_vars()]

        if all(is_valid):
            refill_settings = {var.setting:var.get_mapped() for var in self.control_group.get_vars()}
            modifications = modify_settings({**pump_settings,**refill_settings})
            self.destroy_successfully(modifications)
        else:
            for var in self.control_group.get_vars():
                entry_bgcolor = ApplicationTheme.MANUAL_PUMP_COLOR if var.is_valid() else ApplicationTheme.ERROR_COLOR
                var.widget.configure(border_color=entry_bgcolor)

def _json2str(json_result: PumpNames|None) -> str:
    if json_result is None:
        out = "None"
    else:
        out = json_result.value
    return out

def _str2json(str_result: str) -> PumpNames|None:
    res: str|None = copy.copy(str_result)
    if res == "None":
        out = None
    else:
        out = PumpNames(res)
    return out

Rect = tuple[int,int,int,int] 

class LevelSelect(AlertBox[Rect,Rect,Rect,float]):

    ALERT_TITLE = "Level sensing prompt"

    #TODO this code is perhaps rather rushed...

    def __init__(self, master: ctk.CTk,*args, on_success: Callable[[int,Rect,Rect,Rect,float],None] | None = None, on_failure: Callable[[None],None] | None, fg_color: str | tuple[str, str] | None = None, **kwargs):
        super().__init__(master,*args, on_success=on_success, on_failure=on_failure, fg_color=fg_color, **kwargs)
        self.title(self.ALERT_TITLE)
        self.__video_device = Capture.from_settings()
        
        self.__cv2_exit_condition = threading.Event()
        self.__unregister_exit_condition: Callable[[None],None]|None = None
        self.__cv2_shared_state: SharedState[tuple[Rect,Rect,Rect]] = SharedState()
        self.__error_state: SharedState[BaseException] = SharedState()
        self.__cv2_thread: threading.Thread = threading.Thread(target=_select_regions,args=[self.__video_device,self.__cv2_exit_condition,self.__cv2_shared_state,self.__error_state])

        self.__r1: tuple[int,int,int,int]|None = None
        self.__r2: tuple[int,int,int,int]|None = None
        self.__h: tuple[int,int,int,int]|None = None

        self.initial_frame = ctk.CTkFrame(self)

        self.volume_frame = ctk.CTkFrame(self)
        
        # set up initial page
        instructions_label = ctk.CTkLabel(self.initial_frame,
                                          text = """Finish the selection process by pressing ESC!\nSelect a region and then press SPACE or ENTER\nCancel the selection process by pressing c""")
        self.lblvar = ctk.StringVar(value="Select the anolyte tank, catholyte tank, and finally a reference height")
        self.msg_lbl = ctk.CTkLabel(self.initial_frame, textvariable = self.lblvar)

        self.confirm_button = ctk.CTkButton(self.initial_frame,text="Confirm",command=self.__confirm_initial)
        
        instructions_label.grid(row=0,column=0,columnspan=2,padx=10,pady=5,sticky="nsew")
        self.msg_lbl.grid(row=1,column=0,columnspan=2,padx=10,pady=10,sticky="ns")
        self.confirm_button.grid(row=2,column=1,padx=10,pady=10,sticky="nsw")

        # volume select page
        self.refvar = ctk.StringVar(value="0")
        reflabel = ctk.CTkLabel(self.volume_frame,text="Enter reference volume:")
        self.__refentry = ctk.CTkEntry(self.volume_frame,textvariable=self.refvar,validate="key",validatecommand=(self.register(_validate_volume),"%P"))
        self.__refentry.bind('<Return>', command=lambda event: self.__confirm_volumes())
        self.__refentry.bind('<FocusOut>', command=lambda event: self.focus_set(), add="+")
        ml2 = ctk.CTkLabel(self.volume_frame,text="mL")
        button_frame = ctk.CTkFrame(self.volume_frame)
        volbutton = ctk.CTkButton(button_frame,text="Confirm",command=self.__confirm_volumes)
        redobutton = ctk.CTkButton(button_frame,text="Retake",command=self.__initial_screen)
        button_frame.columnconfigure([0,1],weight=1,uniform="col")
        volbutton.grid(row=0,column=1,padx=10,pady=10,sticky="ns")
        redobutton.grid(row=0,column=0,padx=10,pady=10,sticky="ns")

        reflabel.grid(row=1,column=0,padx=10,pady=10,sticky="w")
        self.__refentry.grid(row=1,column=1,padx=10,pady=10,sticky="ns")
        ml2.grid(row=1,column=2,padx=10,pady=10,sticky="w")
        button_frame.grid(row=3,column=0,columnspan=3,sticky="nsew")

        # Change to initial_frame
        self.__initial_screen()

    def __confirm_initial(self):
        if self.confirm_button._state == ctk.NORMAL:
            self.confirm_button.configure(state=ctk.DISABLED)
            self.__cv2_thread.start()
            self.__unregister_exit_condition = self._add_event(self.__cv2_exit_condition,self.__check_regions)

    def __bad_regions(self,error: BaseException | None):
            errormsg = str(error) if error else "Please select exactly 3 regions"
            self.lblvar.set(errormsg)
            self.msg_lbl.configure(text_color=ApplicationTheme.ERROR_COLOR)
            self.confirm_button.configure(state=ctk.NORMAL)

    def __initial_screen(self):
        self.__r1, self.__r2, self.__h = None,None,None
        self.volume_frame.pack_forget()
        self.confirm_button.configure(state=ctk.NORMAL)
        self.msg_lbl.configure(text_color=ApplicationTheme.WHITE)
        self.initial_frame.pack()

    def __check_regions(self):
        self.__teardown_thread()
        rects = self.__cv2_shared_state.get_value()
        error = self.__error_state.get_value()
        if rects is not None and len(rects) == 3 and error is None:
            self.__r1 = rects[0]
            self.__r2 = rects[1]
            self.__h = rects[2]
            self.__select_volumes()
        else:
            self.__bad_regions(error)

    def __select_volumes(self):
        self.initial_frame.pack_forget()
        self.volume_frame.pack()
        self.__refentry.configure(border_color = ApplicationTheme.MANUAL_PUMP_COLOR)
        self.__refentry.focus_set()

    def __teardown_thread(self):
        if self.__unregister_exit_condition:
            self.__unregister_exit_condition()
            self.__unregister_exit_condition = None
        if self.__cv2_thread.is_alive():
            self.__cv2_exit_condition.set()
            # mock a press of the ESC button to trick the cv2 thread into continuing past the selectROIs() block
            keyboard = pyin.Controller()
            keyboard.press(pyin.Key.esc)
            time.sleep(0.1)
            keyboard.release(pyin.Key.esc)
            try:
                cv2.waitKey(1)
                cv2.destroyWindow("Select Regions")
            except:
                pass
            self.__cv2_thread.join()
            self.__cv2_exit_condition.clear()
        self.__cv2_thread = threading.Thread(target=_select_regions,args=[self.__video_device,self.__cv2_exit_condition,self.__cv2_shared_state,self.__error_state])

    def __confirm_volumes(self):
        ref_vol_str = self.refvar.get()
        if _validate_volume(ref_vol_str,allow_empty=False):
            self.__teardown_thread()
            self.destroy_successfully(self.__r1,self.__r2,self.__h,float(ref_vol_str))
        else:
            self.__refentry.configure(border_color=ApplicationTheme.ERROR_COLOR)
            
    def destroy(self):
        super().destroy()
        self.__teardown_thread()

def _select_regions(capture_device: Capture, exit_condition: threading.Event, shared_state: SharedState[tuple[Rect,Rect,Rect]],error_state:SharedState[BaseException]):
    try:
        img = capture(capture_device)
    except CaptureException as ce:
        exit_condition.set()
        error_state.set_value(ce)
    if exit_condition.is_set():
        return
    cv2.namedWindow("Select Regions")
    if exit_condition.is_set():
        cv2.destroyAllWindows()
        return
    try:
        rects = cv2.selectROIs("Select Regions",img)
        if len(rects) != 3:
            error_state.set_value(_ROIException("Exactly 3 regions were not selected"))
        else:
            shared_state.set_value(rects)
    finally:
        exit_condition.set()
        cv2.destroyAllWindows()
        return
class _ROIException(BaseException): ...

class LevelSettingsBox(AlertBox[dict[Settings,Any]]):


    __NUM_CAMERA_SETTINGS = 3
    ALERT_TITLE = "Level Sensing Settings"

    def __init__(self, master: ctk.CTk, *args, on_success: Callable[[dict[Settings,Any]], None] | None = None, on_failure: Callable[[None], None] | None = None, fg_color: str | tuple[str, str] | None = None, **kwargs):
        super().__init__(master, *args, on_success=on_success, on_failure=on_failure, fg_color=fg_color, **kwargs)
        self.title(self.ALERT_TITLE)
        all_settings = read_settings(*LEVEL_SETTINGS)
        prev_interface: str = all_settings[Settings.CAMERA_INTERFACE_MODULE]
        prev_vd: int = all_settings[Settings.VIDEO_DEVICE]
        prev_auto_exposure: bool = all_settings[Settings.AUTO_EXPOSURE]
        prev_exposure_time: int = all_settings[Settings.EXPOSURE_TIME]
        prev_sensing_period: float = all_settings[Settings.SENSING_PERIOD]
        prev_average_period: float = all_settings[Settings.AVERAGE_WINDOW_WIDTH]
        prev_stabilisation_period = all_settings[Settings.LEVEL_STABILISATION_PERIOD]
        prev_backend: CaptureBackend = all_settings[Settings.CAMERA_BACKEND]
        prev_rescale_factor: float = all_settings[Settings.IMAGE_RESCALE_FACTOR]
        prev_period: float = all_settings[Settings.IMAGE_SAVE_PERIOD]

        segment_frames = self.generate_layout("Camera Settings","Computer Vision Settings",confirm_command=self.__confirm_selections)
        camera_frame = segment_frames[0]
        cv_frame = segment_frames[1]
        
        self.rescale_var = _make_and_grid(_make_entry,camera_frame,"Image Rescaling Factor",Settings.IMAGE_RESCALE_FACTOR,prev_rescale_factor,1,map_fun=float,entry_validator = _validate_scale_factor, on_return = self.__confirm_selections)
        self.save_period_var = _make_and_grid(_make_entry, camera_frame, "Period Between Image Saves", Settings.IMAGE_SAVE_PERIOD, prev_period, 2, map_fun=float, entry_validator = _validate_time_float, on_return = self.__confirm_selections, units="s")
        self.interface_var = _make_and_grid(_make_menu,camera_frame,"Camera Module Interface",Settings.CAMERA_INTERFACE_MODULE,prev_interface,3,values=Capture.SUPPORTED_INTERFACES)
        self.interface_var.trace_add(self.__interface_changed)

        self.sense_period_var = _make_and_grid(_make_entry,cv_frame,"Image Capture Period",Settings.SENSING_PERIOD,str(prev_sensing_period),1,entry_validator = _validate_time_float,units="s",map_fun=float,on_return=self.__confirm_selections)
        self.average_var = _make_and_grid(_make_entry,cv_frame,"Moving Average Period",Settings.AVERAGE_WINDOW_WIDTH, str(prev_average_period),2,entry_validator = _validate_time_float,units = "s",map_fun=float,on_return=self.__confirm_selections)
        self.stabilisation_var = _make_and_grid(_make_entry,cv_frame,"Stabilisation Period",Settings.LEVEL_STABILISATION_PERIOD, str(prev_stabilisation_period),3,entry_validator = _validate_time_float,units="s",map_fun=float,on_return=self.__confirm_selections)

        self.permanent_vars = [self.rescale_var,self.save_period_var,self.interface_var,self.sense_period_var,self.average_var,self.stabilisation_var]
        
        #----------CV2 Settings-------------
        self.cv2_widget_group = _WidgetGroup(initial_row=self.__NUM_CAMERA_SETTINGS)

        cv2_available_backends = [be.value for be in CV2Capture.get_backends()]
        cv2_display_backend = prev_backend.value if prev_backend.value in cv2_available_backends else cv2_available_backends[0]
        self.cv2_backend_var = _make_and_group(_make_menu,
                                               camera_frame,
                                               "Camera Backend Provider",
                                               Settings.CAMERA_BACKEND,
                                               cv2_display_backend,
                                               self.cv2_widget_group,
                                               map_fun=lambda be: CaptureBackend(be),
                                               values=cv2_available_backends)

        self.cv2_vd_var = _make_and_group(_make_entry,
                                          camera_frame,
                                          "Camera Device Number",
                                          Settings.VIDEO_DEVICE,
                                          prev_vd,
                                          self.cv2_widget_group,
                                          map_fun=int,
                                          entry_validator=_validate_device,
                                          on_return = self.__confirm_selections
                                          )
        
        self.cv2_exposure_method_var = _make_and_group(_make_segmented_button,
                                                       camera_frame,
                                                       "Camera Exposure Determination",
                                                       Settings.AUTO_EXPOSURE,
                                                       "Auto" if prev_auto_exposure else "Manual",
                                                       self.cv2_widget_group,
                                                       map_fun= lambda str_in: str_in == "Auto",
                                                       values=["Auto","Manual"],
                                                       command=self.__exposure_method_changed
                                                       )
        current_row = self.cv2_widget_group.current_row
        self.cv2_manual_exposure_group = _WidgetGroup(initial_row=current_row+1,parent=self.cv2_widget_group)
        self.exposure_time_var = _make_and_group(_make_entry,
                                                 camera_frame,
                                                 "Manual Exposure Time",
                                                 Settings.EXPOSURE_TIME,
                                                 str(prev_exposure_time),
                                                 self.cv2_manual_exposure_group,
                                                 map_fun=int,
                                                 entry_validator=_validate_exposure,
                                                 on_return=self.__confirm_selections)
        
        #-----------Pygame Settings--------------
        self.pygame_widget_group = _WidgetGroup(initial_row=self.__NUM_CAMERA_SETTINGS)
        # backend selection dropdown menu
        pygame_available_backends = [be.value for be in PygameCapture.get_backends()]
        pygame_display_backend = prev_backend.value if prev_backend.value in pygame_available_backends else CaptureBackend.ANY.value
        self.pygame_backend_var = _make_and_group(_make_menu,
                                                  camera_frame,
                                                  "Camera Backend Provider",
                                                  Settings.CAMERA_BACKEND,
                                                  pygame_display_backend,
                                                  self.pygame_widget_group,
                                                  map_fun=lambda str_in: CaptureBackend(str_in),
                                                  values=pygame_available_backends)
        self.pygame_backend_var.trace_add(self.__maybe_refresh_pygame_cameras)

        # camera selection dropdown menu
        if prev_interface == "Pygame":
            device_list = PygameCapture.get_cameras(backend=prev_backend)
            if prev_vd < len(device_list):
                selected_device = device_list[prev_vd]
            else:
                selected_device = device_list[0]
        else:
            selected_device = "Loading..."
            device_list = ["Loading..."]
        self.pygame_vd_var = _make_and_group(_make_menu,
                                             camera_frame,
                                             "Camera Device",
                                             Settings.VIDEO_DEVICE,
                                             selected_device,
                                             self.pygame_widget_group,
                                             map_fun = self.__cast_pygame_camera,
                                             values=device_list,
                                             refresh_function=self.__refresh_pygame_cameras)

        self.widget_dict: dict[str,_WidgetGroup] = {"OpenCV": self.cv2_widget_group,"Pygame":self.pygame_widget_group}

        self.__interface_changed()

    def __validate_pygame_camera(self,selected_camera):
        selected_backend = CaptureBackend(self.pygame_backend_var.get())
        return selected_camera in PygameCapture.get_cameras(backend=selected_backend)
    def __cast_pygame_camera(self,selected_camera):
        selected_backend = CaptureBackend(self.pygame_backend_var.get())
        current_device_list = PygameCapture.get_cameras(backend=selected_backend)
        if selected_camera in current_device_list:
            return current_device_list.index(selected_camera)
        return DEFAULT_SETTINGS[Settings.VIDEO_DEVICE]

    def __maybe_refresh_pygame_cameras(self,*args):
        selected_backend = CaptureBackend(self.pygame_backend_var.get())
        selected_camera = self.pygame_vd_var.get()
        try:
            self.pygame_vd_var.widget.configure(values=["Loading..."])
            self.pygame_vd_var.widget.set("Loading")
            new_cameras = PygameCapture.get_cameras(backend=selected_backend)
            self.pygame_vd_var.widget.configure(values=new_cameras)
            if selected_camera not in new_cameras:
                self.pygame_vd_var.widget.set(new_cameras[0])
            else:
                self.pygame_vd_var.widget.set(selected_camera)
            
        except RuntimeError:
            self.pygame_backend_var.set(CaptureBackend.ANY.value)
            self.pygame_backend_var.widget.configure(fg_color = ApplicationTheme.ERROR_COLOR)
            self.after(1000,lambda: self.pygame_backend_var.widget.configure(fg_color = ctk.ThemeManager.theme["CTkOptionMenu"]["fg_color"]))
            self.pygame_backend_var.widget.set(CaptureBackend.ANY.value)
            self.__maybe_refresh_pygame_cameras()
    def __refresh_pygame_cameras(self):
        selected_backend = CaptureBackend(self.pygame_backend_var.get())
        selected_camera = self.pygame_vd_var.get()
        try:
            self.pygame_vd_var.widget.configure(values=["Loading..."])
            self.pygame_vd_var.widget.set("Loading")
            new_cameras = PygameCapture.get_cameras(force_newlist=True,backend=selected_backend)
            self.pygame_vd_var.widget.configure(values=new_cameras)
            if selected_camera not in new_cameras:
                self.pygame_vd_var.widget.set(new_cameras[0])
            else:
                self.pygame_vd_var.widget.set(selected_camera)
        except RuntimeError:
            self.pygame_backend_var.set(CaptureBackend.ANY.value)
            self.pygame_backend_var.widget.configure(fg_color = ApplicationTheme.ERROR_COLOR)
            self.after(1000,lambda: self.pygame_backend_var.widget.configure(fg_color = ctk.ThemeManager.theme["CTkOptionMenu"]["fg_color"]))
            self.pygame_backend_var.widget.set(CaptureBackend.ANY.value)
            self.__maybe_refresh_pygame_cameras()
    def __pygame_refresh_with_label(self):
        menu = self.cv2_vd_var.widget
        loading_label = ctk.CTkLabel(menu,text="Loading...")
        loading_label.place(x=0, y=0, anchor="nw", relwidth=1.0, relheight=1.0)
        def process_refresh(*args):
            self.__maybe_refresh_pygame_cameras()
            loading_label.destroy()
        self.after(500,process_refresh)

    def __interface_changed(self,*args):
        new_interface = self.interface_var.get()
        group_of_interest = self.widget_dict[new_interface]
        for interface_group in self.widget_dict.values():
            if interface_group != group_of_interest:
                interface_group.hide()
        group_of_interest.show()
        self.visible_group = group_of_interest
        if new_interface == "OpenCV":
            self.__exposure_method_changed()
        elif new_interface == "Pygame":
            call_will_block = PygameCapture.will_block(CaptureBackend(self.pygame_backend_var.get()))
            if call_will_block:
                self.__pygame_refresh_with_label()
            else:
                self.__maybe_refresh_pygame_cameras()

    def __exposure_method_changed(self,*args):
        new_method = self.cv2_exposure_method_var.get()
        if new_method == "Auto":
            self.cv2_manual_exposure_group.hide()
            self.exposure_time_var.widget.configure(border_color=ApplicationTheme.MANUAL_PUMP_COLOR)
        else:
            self.cv2_manual_exposure_group.show()

    def __confirm_selections(self):

        all_valid = True
        temp_vars = self.visible_group.get_vars()
        all_vars = [*self.permanent_vars,*temp_vars]
        for var in all_vars:
            if not var.is_valid():
                all_valid = False
                break
        if all_valid:
            all_settings = {var.setting:var.get_mapped() for var in all_vars}
            modifications = modify_settings(all_settings)
            self.destroy_successfully(modifications)
            return

        for var in all_vars:
            if isinstance(var.widget,ctk.CTkEntry):
                entry_fgcolor = ApplicationTheme.MANUAL_PUMP_COLOR if var.is_valid() else ApplicationTheme.ERROR_COLOR
                var.widget.configure(border_color=entry_fgcolor)

class _WidgetGroup:
    def __init__(self,initial_row = 0, widgets: list[ctk.CTkBaseClass] = [], rows: list[int] = [], columns: list[int] = [], vars: list["_SettingVariable"] = [],children: list["_WidgetGroup"]|None = [], parent: "_WidgetGroup" = None):
        max_index = min(len(widgets),len(rows),len(columns))
        self.group: list[tuple[ctk.CTkBaseClass,int,int]] = copy.copy([[widgets[i],rows[i],columns[i]] for i in range(0,max_index)])
        self.current_row = initial_row
        self.is_displayed = False
        self.__is_showing = False
        self.__children = copy.copy(children)
        self.__vars = copy.copy(vars)
        self.__parent: _WidgetGroup|None = None
        if parent is not None:
            parent.add_child(self)

    def add_at_position(self,widget: ctk.CTkBaseClass, row: int, column: int):
        self.group.append([widget,row,column])
    
    def add_widget(self,widget: ctk.CTkBaseClass, column: int):
        self.group.append([widget,self.current_row,column])

    def nextrow(self):
        self.current_row += 1
    
    def show(self):
        self.__is_showing = True
        # only display if the parent group is displayed
        if self.__parent is None or self.__parent.__is_showing:
            # display all child groups
            for child in self.__children:
                if child.__is_showing:
                    child.show()
            # display all widgets in this group
            for widget_info in self.group:
                widget = widget_info[0]
                row = widget_info[1]
                column = widget_info[2]
                widget.grid(row=row,column = column, padx=10, pady=5,sticky="nsew")
    
    def hide(self):
        self.__hide_with_state()
        self.__is_showing = False
    
    def __hide_with_state(self):
        if not self.__is_showing:
            return
        # hide all child groups
        for child in self.__children:
            child.__hide_with_state()
        # hide all widgets in this group
        for widget_info in self.group:
            widget_info[0].grid_remove()

    def add_child(self,child: "_WidgetGroup"):
        if child.__parent is None:
            self.__children.append(child)
            child.__parent = self
        else:
            raise Exception(f"Group {child} already has a parent group!")
    
    def add_var(self,var: "_SettingVariable"):
        if var not in self.__vars:
            self.__vars.append(var)
    
    def get_vars(self) -> list["_SettingVariable"]:
        if not self.__is_showing:
            return []
        vars_out = self.__vars
        for child in self.__children:
            childvars = child.get_vars()
            vars_out = [*vars_out,*childvars]
        return vars_out

T = TypeVar("T")
class _SettingVariable(Generic[T]):
    def __init__(self,var: ctk.StringVar,setting: Settings,validator: Callable[[T],bool] = lambda _: True, map_fun: Callable[[str],T]|None = None) -> None:
        self.__var = var
        self.__setting = setting
        self.fun = map_fun
        self.__validator = validator
        self.widget: ctk.CTkBaseClass|None = None
    def get(self) -> str:
        return self.__var.get()
    def set(self,value: str) -> None:
        self.__var.set(value)
    def get_mapped(self) -> T:
        if self.fun:
            return self.fun(self.get())
        return self.get()
    def is_valid(self) -> bool:
        val = self.get()
        return self.__validator(val)
    def trace_add(self,callback: Callable[[str,str,str],None]):
        self.__var.trace_add("write",callback)
    @property
    def setting(self) -> Settings:
        return self.__setting

class _MakerFunction(Protocol):
    def __call__(self,frame: ctk.CTkFrame, name: str, settings: Settings, initial_value: str, **kwargs) -> tuple[ctk.CTkLabel,"_SettingVariable",ctk.CTkFrame]: ...

def _makerfunction(fn: _MakerFunction) -> _MakerFunction: return fn

@_makerfunction
def _make_entry(frame: ctk.CTkFrame,
                name: str, 
                setting: Settings, 
                initial_value: str,
                entry_validator: Callable[...,bool] = lambda *args,**kwargs: True,
                units: str|None = None,
                map_fun: Callable[[str],Any]|None = None, 
                on_return: Callable[[None],None] = None,
                **kwargs
                ) -> tuple[ctk.CTkLabel,"_SettingVariable",ctk.CTkFrame]:
    lbl = ctk.CTkLabel(frame,text=name)
    ctkvar = ctk.StringVar(value=initial_value)
    var = _SettingVariable(ctkvar,setting,validator=lambda val: entry_validator(val,allow_empty=False),map_fun=map_fun)
    entryparent = ctk.CTkFrame(frame)
    entry = ctk.CTkEntry(entryparent,textvariable=ctkvar, validate='key', validatecommand = (frame.register(entry_validator),"%P"))
    entry.bind("<Return>",lambda *args: on_return() if on_return else None)
    var.widget = entry
    frame.columnconfigure([0],weight=1)
    frame.columnconfigure([1],weight=0)
    if units:
        entry.grid(row=0,column=0,padx=0,pady=0,sticky="nsew")
        unit_label = ctk.CTkLabel(entryparent,text=units)
        unit_label.grid(row=0,column=1,padx=10,pady=0,sticky="nse")
    else:
        entry.grid(row=0,column=0,columnspan=2,padx=0,pady=0,sticky="nsew")
    return lbl,var,entryparent

@_makerfunction
def _make_menu(frame: ctk.CTkFrame,
                name: str, 
                setting: Settings, 
                initial_value: str,
                map_fun: Callable[[str],Any] | None = None,
                values: list[str] = ["Please Select a Value"],
                refresh_function: Callable[[None],None] | None = None
                ) -> tuple[ctk.CTkLabel,"_SettingVariable",ctk.CTkFrame]:
    lbl = ctk.CTkLabel(frame,text=name)
    ctkvar = ctk.StringVar(value=initial_value)
    var = _SettingVariable(ctkvar,setting,map_fun=map_fun)
    menuparent = ctk.CTkFrame(frame,corner_radius=ApplicationTheme.BUTTON_CORNER_RADIUS)
    menu = ctk.CTkOptionMenu(menuparent,variable=ctkvar,values=values,corner_radius=ApplicationTheme.BUTTON_CORNER_RADIUS)
    var.widget=menu
    ctkvar.set(initial_value)
    if refresh_function:
        menuparent.columnconfigure([0],weight=1)
        fullpath = Path().absolute() / "ui_pages/ui_widgets/assets/refresh_label.png"
        pilimg = Image.open(fullpath.as_posix())
        refresh_image = ctk.CTkImage(light_image=pilimg,size=(20,20))
        refresh_button = ctk.CTkButton(menuparent,text=None,image=refresh_image,command=refresh_function,width=21)
        menu.grid(row=0,column=0,padx=0,pady=0,sticky="nsew")
        refresh_button.grid(row=0,column=1,padx=(10,0),pady=0,sticky="nse")
    else:
        menuparent.columnconfigure(0,weight=1)
        menu.grid(row=0,column=0,columnspan=2,padx=0,pady=0,sticky="nsew")
    return lbl,var,menuparent

@_makerfunction
def _make_segmented_button(frame: ctk.CTkFrame,
                           name: str,
                           setting: Settings,
                           initial_value: str,
                           map_fun: Callable[[str],None]|None = None,
                           values: list[str] = ["Please Select a Value"],
                           command: Callable[[None],None] = lambda: None,
                           **kwargs
                           ) -> tuple[ctk.CTkLabel,_SettingVariable,ctk.CTkFrame]:
    lbl = ctk.CTkLabel(frame,text=name)
    ctkvar = ctk.StringVar(value=initial_value)
    var = _SettingVariable(ctkvar,setting,map_fun=map_fun)
    segmentparent = ctk.CTkFrame(frame)
    button = ctk.CTkSegmentedButton(segmentparent,variable=ctkvar,values=values,command=command)
    segmentparent.columnconfigure(0,weight=1)
    button.grid(row=0,column=0,padx=0,pady=0,sticky="nsew")
    return lbl,var,segmentparent

def _make_and_grid(maker_function: _MakerFunction,
                   frame: ctk.CTkFrame,
                   name: str, 
                   setting: Settings,
                   initial_value: str,
                   grid_row: int,
                   map_fun: Callable[[str],Any]|None = None,
                   **kwargs) -> "_SettingVariable":
    lbl,var,widgetframe = maker_function(frame,name,setting,initial_value,map_fun=map_fun,**kwargs)
    lbl.grid(row=grid_row,column=0,padx=10,pady=5,sticky="nsew")
    widgetframe.grid(row=grid_row,column=1,padx=10,pady=5,sticky="nsew")
    return var

def _make_and_group(maker_function: _MakerFunction,
                    frame: ctk.CTkFrame,
                    name: str,
                    setting: Settings,
                    initial_value: str,
                    group: "_WidgetGroup",
                    map_fun: Callable [[str],Any] | None = None,
                    **kwargs
                    ) -> "_SettingVariable":
    lbl,var,widgetframe = maker_function(frame,name,setting,initial_value,map_fun=map_fun,**kwargs)
    group.add_widget(lbl,0)
    group.add_widget(widgetframe,1)
    group.add_var(var)
    group.nextrow()
    return var


class _ValidatorFunction():
    def __call__(a: str,allow_true = True) -> bool: ...

def validator_function(fn: _ValidatorFunction) -> _ValidatorFunction: return fn

@validator_function
def _validate_device(p: str, allow_empty = True):
    try:
        nump = int(p)
        if nump >= 0:
            return True
        return False
    except ValueError:
        if p == "" and allow_empty:
            return True
        return False
@validator_function
def _validate_volume(p: str,allow_empty = True):
    try:
        nump = float(p)
        if nump > 0:
            return True
        if nump == 0 and allow_empty:
            return True
        return False
    except ValueError:
        if p == "" and allow_empty:
            return True
        return False
@validator_function
def _validate_time_float(timestr: str, allow_empty = True):
    if timestr == "":
        return allow_empty
    try:
        t = float(timestr)
        if t>0 or (t==0 and allow_empty):
            return True
        return False
    except:
        return False
@validator_function
def _validate_exposure(exp: str, allow_empty: bool = True) -> bool:
    if exp in ("","-",".") and allow_empty:
        return True
    try:
        int(exp)
        return True
    except:
        return False
@validator_function
def _validate_time(timestr: str, allow_empty = True):
    if timestr == "":
        return allow_empty
    try:
        t = int(timestr)
        if t>0:
            return True
        return False
    except:
        return False
@validator_function
def _validate_duty(dutystr: str, allow_empty = True):
    if dutystr == "":
        return allow_empty
    try:
        d = int(dutystr)
        if d>=0 and d<=255:
            return True
        return False
    except:
        return False
@validator_function
def _validate_percent(percentstr: str, allow_empty = True):
    if percentstr == "":
        return allow_empty
    try:
        p = int(percentstr)
        if p>0 and p<100:
            return True
        return False
    except:
        return False
@validator_function
def _validate_scale_factor(sf: str, allow_empty = True):
    MAX_FACTOR = 10
    if sf == "":
        return allow_empty
    try:
        f = float(sf)
        if f>(1/MAX_FACTOR) and f<MAX_FACTOR or (f>=0 and allow_empty):
            return True
        return False
    except:
        return False
@validator_function
def _validate_gain(str_in: str, allow_empty = True) -> bool:
    if str_in in ("","-"):
        return True
    try:
        float(str_in)
        return True
    except:
        return False
    
    
