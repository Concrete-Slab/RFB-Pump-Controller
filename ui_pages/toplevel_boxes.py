import customtkinter as ctk
import cv2
from support_classes import open_cv2_window, capture, CaptureException, read_settings, modify_settings, Settings, PID_SETTINGS, LOGGING_SETTINGS, PumpNames, PID_PUMPS
from typing import Generic,ParamSpec,Callable,Any
from pathlib import Path
from .ui_widgets.themes import ApplicationTheme
import copy
import json

SuccessSignature = ParamSpec("SuccessSignature")

class AlertBox(ctk.CTkToplevel,Generic[SuccessSignature]):
    def __init__(self, master: ctk.CTk, *args, on_success: Callable[SuccessSignature,None] | None = None, on_failure: Callable[[None],None] | None = None, fg_color: str | tuple[str, str] | None = None, **kwargs):
        super().__init__(master,*args, fg_color=fg_color, **kwargs)
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

    def bring_forward(self):
        self.attributes('-topmost', 1)
        self.after(400,lambda: self.attributes('-topmost', 0))
    
class DataSettingsBox(AlertBox[dict[str,Any]]):

    ALERT_TITLE = "Data Logging Settings"

    def __init__(self, master: ctk.CTk, *args, on_success: Callable[..., None] | None = None, on_failure: Callable[[None], None] | None = None, fg_color: str | tuple[str, str] | None = None, **kwargs):
        super().__init__(master, *args, on_success=on_success, on_failure=on_failure, fg_color=fg_color, **kwargs)
        
        ## READ THE CURRENT SETTINGS
        # with open("settings.json","r") as f:
        #     settings: dict[str,Any] = dict(json.load(f))
        
        # self.__prev_logging_settings = {k:settings[k] for k in (Settings.LOG_LEVELS,Settings.LOG_PID,Settings.LOG_SPEEDS) if k in settings.keys()}
        
        self.__prev_logging_settings = read_settings(*LOGGING_SETTINGS)
        prev_log_levels: bool = self.__prev_logging_settings[Settings.LOG_LEVELS]
        prev_log_pid: bool = self.__prev_logging_settings[Settings.LOG_PID]
        prev_log_speeds: bool = self.__prev_logging_settings[Settings.LOG_SPEEDS]
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

        self.columnconfigure([0,1],weight = 1, uniform = "col")
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
            Settings.LEVEL_DIRECTORY: (new_logging_directory / "levels"),
            Settings.PID_DIRECTORY: (new_logging_directory / "duties"),
            Settings.SPEED_DIRECTORY: (new_logging_directory / "speeds"),
        }

    
        modifications = modify_settings(new_logging_settings)
        ## close the window by notifying of modified changes
        self.destroy_successfully(modifications)

class PIDSettingsBox(AlertBox[dict[str,Any]]):

    def __init__(self, master: ctk.CTk, *args, on_success: Callable[..., None] | None = None, on_failure: Callable[[None], None] | None = None, fg_color: str | tuple[str, str] | None = None, **kwargs):
        super().__init__(master, *args, on_success=on_success, on_failure=on_failure, fg_color=fg_color, **kwargs)
        
        self.__default_options = ["None"]
        for pmpname in PumpNames:
            self.__default_options.append(pmpname.value.lower())

        pid_settings = read_settings(*PID_SETTINGS)
        pump_settings: dict[Settings,PumpNames|None] = {key:pid_settings[key] for key in PID_PUMPS}
        an_var = ctk.StringVar(value=_json2str(pump_settings[Settings.ANOLYTE_PUMP]))
        cath_var = ctk.StringVar(value=_json2str(pump_settings[Settings.CATHOLYTE_PUMP]))
        an_re_var = ctk.StringVar(value=_json2str(pump_settings[Settings.ANOLYTE_REFILL_PUMP]))
        cath_re_var = ctk.StringVar(value=_json2str(pump_settings[Settings.CATHOLYTE_REFILL_PUMP]))
        self.__vars = [an_var,cath_var,an_re_var,cath_re_var]
        
        anolyte_selection = ctk.CTkOptionMenu(self,values=self.__default_options,variable=an_var)
        catholyte_selection = ctk.CTkOptionMenu(self,values=self.__default_options,variable=cath_var)
        anolyte_refill_selection = ctk.CTkOptionMenu(self,values=self.__default_options,variable=an_re_var)
        catholyte_refill_selection = ctk.CTkOptionMenu(self,values=self.__default_options,variable=cath_re_var)
        self.__boxes = [anolyte_selection,catholyte_selection,anolyte_refill_selection,catholyte_refill_selection]

        an_label = ctk.CTkLabel(self,text="Anolyte Pump")
        cath_label = ctk.CTkLabel(self,text="Catholyte Pump")
        an_refill_label = ctk.CTkLabel(self,text="Anolyte Refill Pump")
        cath_refill_label = ctk.CTkLabel(self,text="Catholyte Refill Pump")
        labels = [an_label,cath_label,an_refill_label,cath_refill_label]

        for i,var in enumerate(self.__vars):
            var.trace("w",lambda *args,index=i: self.__update_selections(index,*args))
            self.__boxes[i].grid(row=i,column=1,padx=10,pady=5,sticky="nsew")
            labels[i].grid(row=i,column=0,padx=10,pady=5,sticky="nsew")


        base_duty_label = ctk.CTkLabel(self,text="Equilibrium Control Duty")
        rf_time_label = ctk.CTkLabel(self,text="Refill Time")
        rf_duty_label = ctk.CTkLabel(self,text="Refill Duty")
        rf_percent_label = ctk.CTkLabel(self,text="Refill Solvent Loss Trigger")

        entry_labels = [base_duty_label,rf_time_label,rf_duty_label,rf_percent_label]

        base_duty_frame = ctk.CTkFrame(self,corner_radius=0)
        self.__base_duty_var = ctk.StringVar(value=pid_settings[Settings.BASE_CONTROL_DUTY])
        base_duty_box = ctk.CTkEntry(base_duty_frame, textvariable=self.__base_duty_var, validate='key', validatecommand = (self.register(_validate_duty),"%P"))
        base_duty_box.grid(row=0,column=0,padx=5,pady=5,sticky="nsew")

        rf_time_frame = ctk.CTkFrame(self,corner_radius=0)
        self.__rf_time_var = ctk.StringVar(value=pid_settings[Settings.REFILL_TIME])
        rf_time_box = ctk.CTkEntry(rf_time_frame, textvariable=self.__rf_time_var, validate='key', validatecommand = (self.register(_validate_time),"%P"))
        seconds_label = ctk.CTkLabel(rf_time_frame,text="s")
        rf_time_box.grid(row=0,column=0,padx=5,pady=5,sticky="nsew")
        seconds_label.grid(row=0,column=1,padx=5,pady=5,sticky="nsew")

        rf_duty_frame = ctk.CTkFrame(self,corner_radius=0)
        self.__rf_duty_var = ctk.StringVar(value=pid_settings[Settings.REFILL_DUTY])
        rf_duty_box = ctk.CTkEntry(rf_duty_frame, textvariable=self.__rf_duty_var, validate='key', validatecommand = (self.register(_validate_time),"%P"))
        rf_duty_box.grid(row=0,column=0,padx=5,pady=5,sticky="nsew")

        rf_percent_frame = ctk.CTkFrame(self,corner_radius=0)
        self.__rf_percent_var = ctk.StringVar(value=pid_settings[Settings.REFILL_PERCENTAGE_TRIGGER])
        rf_percent_box = ctk.CTkEntry(rf_percent_frame, textvariable=self.__rf_percent_var ,validate='key', validatecommand = (self.register(_validate_percent),"%P"))
        percent_label = ctk.CTkLabel(rf_percent_frame,text="%")
        rf_percent_box.grid(row=0,column=0,padx=5,pady=5,sticky="nsew")
        percent_label.grid(row=0,column=1,padx=5,pady=5,sticky="nsew")
        self.__refill_entries = [rf_time_box,rf_duty_box,rf_percent_box]
        entry_frames = [base_duty_frame,rf_time_frame,rf_duty_frame,rf_percent_frame]

        currRow = len(self.__vars)

        for j in range(0,len(entry_frames)):
            entry_labels[j].grid(row=j+currRow,column=0,padx=10,pady=5,sticky="nsew")
            entry_frames[j].grid(row=j+currRow,column=1,padx=5,pady=0,sticky="nsew")

        currRow = currRow + len(entry_frames)
        

        confirm_button = ctk.CTkButton(self,command=self.__confirm_selections,text="Confirm",corner_radius=ApplicationTheme.BUTTON_CORNER_RADIUS)
        confirm_button.grid(row=currRow,column=1,padx=10,pady=5,sticky="nes")
        

    def __update_selections(self,var_index,*args):
        # make sure there are no duplicate selections
        vars_copy = copy.copy(self.__vars)
        selected_value = vars_copy.pop(var_index).get()
        if selected_value != "None":
            for var in vars_copy:
                value = var.get()
                if value == selected_value:
                    var.set("None")

        
    def __confirm_selections(self):
        pump_settings = {
            Settings.ANOLYTE_PUMP: _str2json(self.__vars[0].get()),
            Settings.CATHOLYTE_PUMP: _str2json(self.__vars[1].get()),
            Settings.ANOLYTE_REFILL_PUMP: _str2json(self.__vars[2].get()),
            Settings.CATHOLYTE_REFILL_PUMP: _str2json(self.__vars[3].get())
        }
        # final check that there are no duplicates (except None values)
        prev_values = []
        for key,value in pump_settings.items():
            if value is not None and value in prev_values:
                pump_settings[key] = None
            prev_values.append(pump_settings[key])

        base_duty = self.__base_duty_var.get()
        rf_time = self.__rf_time_var.get()
        rf_duty = self.__rf_duty_var.get()
        rf_percent = self.__rf_percent_var.get()

        valid_input = [_validate_duty(base_duty,allow_empty=False),_validate_time(rf_time,allow_empty=False),_validate_duty(rf_duty,allow_empty=False),_validate_percent(rf_percent,allow_empty=False)]

        if all(valid_input):
            refill_settings = {
                Settings.BASE_CONTROL_DUTY: int(base_duty),
                Settings.REFILL_TIME: int(rf_time),
                Settings.REFILL_DUTY: int(rf_duty),
                Settings.REFILL_PERCENTAGE_TRIGGER: int(rf_percent)
            }
            modifications = modify_settings({**pump_settings,**refill_settings})
            self.destroy_successfully(modifications)
        else:
            for i in range(0,len(valid_input)):
                entry_bgcolor = ApplicationTheme.MANUAL_PUMP_COLOR if valid_input[i] else ApplicationTheme.ERROR_COLOR
                self.__refill_entries[i].configure(fg_color=entry_bgcolor)





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
    
            

            

            

Rect = tuple[int,int,int,int] 


class LevelSelect(AlertBox[int,Rect,Rect,Rect,float]):

    ALERT_TITLE = "Level sensing prompt"

    VALID_REGIONS = "valid_regions"
    INVALID_REGIONS = "invalid_regions"
    

    #TODO this code is perhaps rather rushed...

    def __init__(self, master: ctk.CTk,*args, on_success: Callable[[int,Rect,Rect,Rect,float],None] | None = None, on_failure: Callable[[None],None] | None, fg_color: str | tuple[str, str] | None = None, **kwargs):
        super().__init__(master,*args, on_success=on_success, on_failure=on_failure, fg_color=fg_color, **kwargs)
        self.title(self.ALERT_TITLE)
        with open("settings.json","r") as f:
            settings = json.load(f)
        try:
            default_video_device = settings["default_video_device"]
            if default_video_device is not None and isinstance(default_video_device,int) and default_video_device>=0:
                self.default_device = default_video_device
        except:
            self.default_device = 0

        self.__r1: tuple[int,int,int,int]|None = None
        self.__r2: tuple[int,int,int,int]|None = None
        self.__h: tuple[int,int,int,int]|None = None

        self.initial_frame = ctk.CTkFrame(self)

        self.volume_frame = ctk.CTkFrame(self)
        
        # set up initial page

        self.lblvar = ctk.StringVar(value="Select video device (positive int): ")
        lbl = ctk.CTkLabel(self.initial_frame, textvariable = self.lblvar)
        self.current_device = ctk.StringVar(value=str(default_video_device))
        device_selector = ctk.CTkEntry(self.initial_frame, textvariable=self.current_device, validate='key', validatecommand = (self.register(_validate_device),"%P"))
        device_selector.bind('<Return>', command=lambda event: self.__confirm_device())
        device_selector.bind('<FocusOut>', command=lambda event: self.focus_set(), add="+")

        self.confirm_button = ctk.CTkButton(self.initial_frame,text="Confirm",command=self.__confirm_device)
        

        lbl.grid(row=0,column=0,columnspan=2,padx=10,pady=10,sticky="ns")
        device_selector.grid(row=1,column=0,padx=10,pady=10,sticky="nsew")
        self.confirm_button.grid(row=1,column=1,padx=10,pady=10,sticky="nsew")

        # volume select page

        # self.initvar = ctk.StringVar(value="0")
        self.refvar = ctk.StringVar(value="0")
        # initlabel = ctk.CTkLabel(self.volume_frame,text="Enter combined initial volume:")
        reflabel = ctk.CTkLabel(self.volume_frame,text="Enter reference volume:")
        # initentry = ctk.CTkEntry(self.volume_frame,textvariable=self.initvar,validate="key",validatecommand=(self.register(_validate_volume),"%P"))
        # initentry.bind('<Return>', command=lambda event: self.__confirm_volumes())
        # initentry.bind('<Tab>', command=lambda event: refentry.focus_set())
        # initentry.bind('<FocusOut>', command=lambda event: self.focus_set(), add="+")
        self.__refentry = ctk.CTkEntry(self.volume_frame,textvariable=self.refvar,validate="key",validatecommand=(self.register(_validate_volume),"%P"))
        self.__refentry.bind('<Return>', command=lambda event: self.__confirm_volumes())
        # refentry.bind('<Tab>', command=lambda event: initentry.focus_set())
        self.__refentry.bind('<FocusOut>', command=lambda event: self.focus_set(), add="+")
        # ml1 = ctk.CTkLabel(self.volume_frame,text="mL")
        ml2 = ctk.CTkLabel(self.volume_frame,text="mL")
        button_frame = ctk.CTkFrame(self.volume_frame)
        volbutton = ctk.CTkButton(button_frame,text="Confirm",command=self.__confirm_volumes)
        redobutton = ctk.CTkButton(button_frame,text="Retake",command=self.__select_device)
        button_frame.columnconfigure([0,1],weight=1,uniform="col")
        volbutton.grid(row=0,column=1,padx=10,pady=10,sticky="ns")
        redobutton.grid(row=0,column=0,padx=10,pady=10,sticky="ns")

        # initlabel.grid(row=0,column=0,padx=10,pady=10,sticky="w")
        # initentry.grid(row=0,column=1,padx=10,pady=10,sticky="ns")
        # ml1.grid(row=0,column=2,padx=10,pady=10,sticky="w")
        reflabel.grid(row=1,column=0,padx=10,pady=10,sticky="w")
        self.__refentry.grid(row=1,column=1,padx=10,pady=10,sticky="ns")
        ml2.grid(row=1,column=2,padx=10,pady=10,sticky="w")
        button_frame.grid(row=3,column=0,columnspan=3,sticky="nsew")

        # Change to initial_frame
        self.__select_device()
        
        


    def __confirm_device(self):
        if self.confirm_button._state == ctk.NORMAL:
            device_num = self.current_device.get()
            if device_num == "":
                self.lblvar.set("Please enter a valid device number")
            else:
                self.confirm_button.configure(state=ctk.DISABLED)
                # self.UIcontroller.notify_event("launch_cv2",int(self.current_device.get()))
                self.__launch_cv2(int(device_num))

    def __bad_device(self):
            self.lblvar.set("Choose a different device")
            self.confirm_button.configure(state=ctk.NORMAL)

    def __select_device(self):
        self.__r1, self.__r2, self.__h = None,None,None
        self.volume_frame.pack_forget()
        self.confirm_button.configure(state=ctk.NORMAL)
        self.initial_frame.pack()

    def __select_volumes(self):
        self.initial_frame.pack_forget()
        self.volume_frame.pack()
        self.__refentry.focus_set()

    def __bad_regions(self):
        self.lblvar.set("Please select 3 regions")
        self.confirm_button.configure(state=ctk.NORMAL)

    def __confirm_volumes(self):
        # init_vol_str = self.initvar.get()
        ref_vol_str = self.refvar.get()
        # if init_vol_str != "" and ref_vol_str not in  "" and float(init_vol_str)>0 and float(ref_vol_str)>0:
        if ref_vol_str != "" and float(ref_vol_str)>0:
            
            # self.UIcontroller.notify_event(CEvents.LEVEL_DATA_ACQUIRED,self.default_device,self.__r1,self.__r2,self.__h,float(ref_vol_str))
            self.destroy_successfully(self.default_device,self.__r1,self.__r2,self.__h,float(ref_vol_str))

    def __launch_cv2(self,device: int):
        try:
            cap = capture(device)
            self.default_device = device
            with open_cv2_window("rectfeed") as wind:
                try:
                    self.__r1, self.__r2, self.__h = cv2.selectROIs(wind,cap)
                except ValueError:
                    self.__r1, self.__r2, self.__h = None, None, None
            if any((self.__r1 is None, self.__r2 is None, self.__h is None)):
                # TODO change these back to parameterless
                self.__bad_regions()
            else:
                self.__select_volumes()
        except CaptureException:
            self.__bad_device()

    def destroy(self):
        cv2.destroyAllWindows()
        super().destroy()

def _validate_device(p: str):
    try:
        nump = int(p)
        if nump >= 0:
            return True
        return False
    except ValueError:
        if p == "":
            return True
        return False
    
def _validate_volume(p: str):
    try:
        nump = float(p)
        if nump >= 0:
            return True
        return False
    except ValueError:
        if p == "":
            return True
        return False