import customtkinter as ctk
import cv2
from ui_root import UIRoot, EventFunction, StateFunction, CallbackRemover
from support_classes import capture, CaptureException, read_settings, modify_settings, Settings, PID_SETTINGS, LOGGING_SETTINGS, PumpNames, PID_PUMPS, LEVEL_SETTINGS, SharedState, Capture, PygameCapture, DEFAULT_SETTINGS, CaptureBackend, CV2Capture
from typing import Generic,ParamSpec,Callable,Any,TypeVar
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

class PIDSettingsBox(AlertBox[dict[Settings,Any]]):

    ALERT_TITLE = "PID Settings"

    def __init__(self, master: ctk.CTk, *args, on_success: Callable[..., None] | None = None, on_failure: Callable[[None], None] | None = None, fg_color: str | tuple[str, str] | None = None, **kwargs):
        super().__init__(master, *args, on_success=on_success, on_failure=on_failure, fg_color=fg_color, **kwargs)
        self.title(self.ALERT_TITLE)

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
            var.trace_add("w",lambda *args,index=i: self.__update_selections(index,*args))
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
                self.__refill_entries[i].configure(border_color=entry_bgcolor)

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
        self.__cv2_thread: threading.Thread = threading.Thread(target=_select_regions,args=[self.__video_device,self.__cv2_exit_condition,self.__cv2_shared_state])

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

    def __bad_regions(self):
            self.lblvar.set("Please select exactly 3 regions")
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
        if rects is not None and len(rects) == 3:
            self.__r1 = rects[0]
            self.__r2 = rects[1]
            self.__h = rects[2]
            self.__select_volumes()
        else:
            self.__bad_regions()

    def __select_volumes(self):
        self.initial_frame.pack_forget()
        self.volume_frame.pack()
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
        self.__cv2_thread = threading.Thread(target=_select_regions,args=[self.__video_device,self.__cv2_exit_condition,self.__cv2_shared_state])

    def __confirm_volumes(self):
        ref_vol_str = self.refvar.get()
        if ref_vol_str != "" and float(ref_vol_str)>0:
            self.__teardown_thread()
            self.destroy_successfully(self.__r1,self.__r2,self.__h,float(ref_vol_str))
            
    def destroy(self):
        super().destroy()
        self.__teardown_thread()

def _select_regions(capture_device, exit_condition: threading.Event, shared_state: SharedState[tuple[Rect,Rect,Rect]]):
    try:
        img = capture(capture_device)
    except CaptureException:
        exit_condition.set()
    if exit_condition.is_set():
        return
    cv2.namedWindow("Select Regions")
    if exit_condition.is_set():
        cv2.destroyAllWindows()
        return
    try:
        rects = cv2.selectROIs("Select Regions",img)
        if len(rects) != 3:
            raise Exception("Exactly 3 regions were not selected")
        shared_state.set_value(rects)
    finally:
        exit_condition.set()
        cv2.destroyAllWindows()
        return

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

WidgetGridInfo = tuple[ctk.CTkBaseClass,int,int]

class LevelSettingsBox(AlertBox[dict[Settings,Any]]):


    __NUM_CAMERA_SETTINGS = 2
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

        # frame for holding camera-related settings
        camera_frame = ctk.CTkFrame(self)
        camera_title_label = ctk.CTkLabel(camera_frame,text="Camera Settings")
        camera_title_label.grid(row=0,column=0,columnspan=2,padx=10,pady=5,sticky="nsew")
        # frame for holding computer vision settings
        cv_frame = ctk.CTkFrame(self)
        cv_title_label = ctk.CTkLabel(cv_frame,text="Computer Vision Settings")
        cv_title_label.grid(row=0,column=0,columnspan=2,padx=10,pady=5,sticky="nsew")

        P = TypeVar("P")
        
        
        interface_ctkvar = ctk.StringVar(value=prev_interface)
        self.interface_var = _SettingVariable[str](interface_ctkvar, Settings.CAMERA_INTERFACE_MODULE)
        interface_lbl = ctk.CTkLabel(camera_frame,text="Camera Module Interface")
        interface_dropdown = ctk.CTkOptionMenu(camera_frame,variable=interface_ctkvar,values=Capture.SUPPORTED_INTERFACES())
        self.interface_var.widget = interface_dropdown
        interface_lbl.grid(row=1,column=0,padx=10,pady=5,sticky="nsew")
        interface_dropdown.grid(row=1,column=1,padx=10,pady=5,sticky="nsew")
        self.interface_var.trace_add(self.__interface_changed)

        self.sense_period_var,sense_period_entry = _make_and_grid(cv_frame,"Image Capture Period",Settings.SENSING_PERIOD,str(prev_sensing_period),_validate_time_float,1,units="s",map_fun=float)
        self.average_var,average_entry = _make_and_grid(cv_frame,"Moving Average Period",Settings.AVERAGE_WINDOW_WIDTH,str(prev_average_period),_validate_time_float,2,units = "s",map_fun=float)
        self.stabilisation_var, stabilisation_entry = _make_and_grid(cv_frame,"Stabilisation Period",Settings.LEVEL_STABILISATION_PERIOD,str(prev_stabilisation_period),_validate_time_float,3,units="s",map_fun=float)


        #----------CV2 Settings-------------
        # exposure selection auto/manual switch
        exposure_method_label = ctk.CTkLabel(camera_frame,text="Camera Exposure Determination")
        exposure_method_ctkvar = ctk.StringVar(value="Auto" if prev_auto_exposure else "Manual")
        self.exposure_method_var = _SettingVariable(exposure_method_ctkvar,Settings.AUTO_EXPOSURE,map_fun= lambda str_in: str_in=="Auto")
        exposure_method_button = ctk.CTkSegmentedButton(camera_frame,values=["Auto","Manual"],variable=exposure_method_ctkvar,corner_radius=ApplicationTheme.BUTTON_CORNER_RADIUS,command=self.__exposure_method_changed)
        self.exposure_method_var.widget = exposure_method_button

        # backend selection dropdown menu
        cv2_backend_label = ctk.CTkLabel(camera_frame,text="Camera Backend Provider")
        cv2_available_backends = [be.value for be in CV2Capture.get_backends()]
        cv2_display_backend = prev_backend.value if prev_backend.value in cv2_available_backends else CaptureBackend.ANY.value
        cv2_backend_ctkvar = ctk.StringVar(value = cv2_display_backend)
        self.cv2_backend_var = _SettingVariable(cv2_backend_ctkvar,Settings.CAMERA_BACKEND,map_fun=lambda be: CaptureBackend(be))
        cv2_backend_menu = ctk.CTkOptionMenu(camera_frame,variable=cv2_backend_ctkvar,values=cv2_available_backends)
        self.cv2_backend_var.widget = cv2_backend_menu

        # exposure time entry box
        self.exposure_time_label,self.exposure_time_var,self.exposure_time_entry,self.exposure_time_entryframe= _make_entry(camera_frame,"Manual Exposure Time",Settings.EXPOSURE_TIME,str(prev_exposure_time),_validate_exposure)
        
        # video device number entry box
        vd_label,self.vd_var,vd_entry,vd_entryframe = _make_entry(camera_frame,"Camera Device Number",Settings.VIDEO_DEVICE,str(prev_vd),_validate_device,map_fun=int)

        self.cv2_widgets: WidgetGridInfo = [(vd_label,self.__NUM_CAMERA_SETTINGS,0),
                            (vd_entryframe,self.__NUM_CAMERA_SETTINGS,1),
                            (cv2_backend_label,self.__NUM_CAMERA_SETTINGS+1,0),
                            (cv2_backend_menu,self.__NUM_CAMERA_SETTINGS+1,1),
                            (exposure_method_label,self.__NUM_CAMERA_SETTINGS+2,0),
                            (exposure_method_button,self.__NUM_CAMERA_SETTINGS+2,1),
                            (self.exposure_time_label,self.__NUM_CAMERA_SETTINGS+3,0),
                            (self.exposure_time_entryframe,self.__NUM_CAMERA_SETTINGS+3,1)]
        self.cv2_vars = [self.vd_var,self.cv2_backend_var,self.exposure_method_var,self.exposure_time_var]

        #-----------Pygame Settings--------------
        # backend selection dropdown menu
        pygame_backend_label = ctk.CTkLabel(camera_frame,text="Camera Backend Provider")
        pygame_available_backends = [be.value for be in PygameCapture.get_backends()]
        pygame_display_backend = prev_backend.value if prev_backend.value in pygame_available_backends else CaptureBackend.ANY.value
        pygame_backend_ctkvar = ctk.StringVar(value=pygame_display_backend)
        self.pygame_backend_var = _SettingVariable(pygame_backend_ctkvar,Settings.CAMERA_BACKEND,map_fun=lambda str_in: CaptureBackend(str_in))
        pygame_backend_menu = ctk.CTkOptionMenu(camera_frame,variable=pygame_backend_ctkvar,values = pygame_available_backends)
        self.pygame_backend_var.widget = pygame_backend_menu
        self.pygame_backend_var.trace_add(self.__maybe_refresh_pygame_cameras)

        # camera selection dropdown menu
        pgvd_label = ctk.CTkLabel(camera_frame,text="Camera Device")
        current_list = PygameCapture.get_cameras(backend=pygame_display_backend)
        selected_device = current_list[prev_vd] if prev_vd < len(current_list) else current_list[0]
        pgvd_ctkvar = ctk.StringVar(value=selected_device)
        self.pgvd_var = _SettingVariable(pgvd_ctkvar,Settings.VIDEO_DEVICE,map_fun=self.__cast_pygame_camera,validator=self.__validate_pygame_camera)
        pgvd_frame = ctk.CTkFrame(camera_frame)
        self.pgvd_menu = ctk.CTkOptionMenu(pgvd_frame,variable=pgvd_ctkvar,values=current_list)
        pygame_refresh = ctk.CTkButton(pgvd_frame,text="Refresh",command=self.__refresh_pygame_cameras)
        self.pgvd_menu.grid(row=0,column=0,padx=5,pady=5,sticky="nsew")
        pygame_refresh.grid(row=0,column=1,padx=5,pady=5,sticky="nsew")
        self.pgvd_var.widget = self.pgvd_menu

        self.pygame_widgets: WidgetGridInfo = [(pygame_backend_label,self.__NUM_CAMERA_SETTINGS,0),
                                               (pygame_backend_menu,self.__NUM_CAMERA_SETTINGS,1),
                                               (pgvd_label,self.__NUM_CAMERA_SETTINGS+1,0),
                                               (pgvd_frame,self.__NUM_CAMERA_SETTINGS+1,1)]
        self.pygame_vars = [self.pygame_backend_var,self.pgvd_var]

        self.permanent_vars = [self.interface_var,self.sense_period_var,self.average_var,self.stabilisation_var]

        self.widget_dict: dict[str,tuple[WidgetGridInfo,list[_SettingVariable]]] = {"OpenCV": (self.cv2_widgets,self.cv2_vars),"Pygame": (self.pygame_widgets,self.pygame_vars)}

        self.visible_vars: list[_SettingVariable] = []

        self.columnconfigure([0,1],weight=1,uniform="rootcol")
        camera_frame.grid(row=0,column=0,padx=10,pady=5,sticky="nsew")
        cv_frame.grid(row=0,column=1,padx=10,pady=5,sticky="nsew")

        confirm_button = ctk.CTkButton(self,text="Confirm",command=self.__confirm_selections)
        cancel_button = ctk.CTkButton(self,text="Cancel",command=self.destroy)
        confirm_button.grid(row=1,column=1,padx=10,pady=5,sticky="nse")
        cancel_button.grid(row=1,column=0,padx=10,pady=5,sticky="nsw")
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
        selected_camera = self.pgvd_var.get()
        try:
            new_cameras = PygameCapture.get_cameras(backend=selected_backend)
            self.pgvd_menu.configure(values=new_cameras)
            if selected_camera not in new_cameras:
                self.pgvd_var.set(new_cameras[0])
            
        except RuntimeError:
            self.pygame_backend_var.set(CaptureBackend.ANY.value)
            self.__maybe_refresh_pygame_cameras()
    def __refresh_pygame_cameras(self):
        selected_backend = CaptureBackend(self.pygame_backend_var.get())
        try:
            self.pgvd_menu.configure(values=PygameCapture.get_cameras(force_newlist=True,backend=selected_backend))
        except RuntimeError:
            self.pygame_backend_var.set(CaptureBackend.ANY.value)
        
    def __interface_changed(self,*args):
        new_interface = self.interface_var.get()
        widgets_of_interest = self.widget_dict[new_interface][0]
        vars_of_interest = self.widget_dict[new_interface][1]

        for interface in self.widget_dict.keys():
            if interface != new_interface:
                old_widgets_info = self.widget_dict[interface][0]
                for widgetgridinfo in old_widgets_info:
                    curr_widget: ctk.CTkBaseClass = widgetgridinfo[0]
                    curr_widget.grid_remove()
        for newgridinfo in widgets_of_interest:
            curr_widget: ctk.CTkBaseClass = newgridinfo[0]
            curr_row: int = newgridinfo[1]
            curr_column: int = newgridinfo[2]
            curr_widget.grid(row=curr_row,column=curr_column,padx=10,pady=5,sticky="nsew")
        self.visible_vars = [*self.permanent_vars,*vars_of_interest]
        if new_interface == "OpenCV":
            self.__exposure_method_changed()

    def __confirm_selections(self):

        all_valid = True
        for var in self.visible_vars:
            if not var.is_valid():
                all_valid = False
                break
        if all_valid:
            all_settings = {var.setting:var.get_mapped() for var in self.visible_vars}
            modifications = modify_settings(all_settings)
            self.destroy_successfully(modifications)
            return

        for var in self.visible_vars:
            if isinstance(var.widget,ctk.CTkEntry):
                entry_fgcolor = ApplicationTheme.MANUAL_PUMP_COLOR if var.is_valid() else ApplicationTheme.ERROR_COLOR
                var.widget.configure(border_color=entry_fgcolor)

    def __exposure_method_changed(self,*args):
        new_method = self.exposure_method_var.get()
        if new_method == "Auto":
            self.exposure_time_label.grid_remove()
            self.exposure_time_entryframe.grid_remove()
            try:
                self.visible_vars.remove(self.exposure_time_var)
            except Exception as e:
                print(e)
            self.exposure_time_entry.configure(border_color=ApplicationTheme.MANUAL_PUMP_COLOR)
        else:
            exposure_settings_row = self.__NUM_CAMERA_SETTINGS+3
            self.exposure_time_label.grid(row=exposure_settings_row,column=0,padx=10,pady=5,sticky="nsew")
            self.exposure_time_entryframe.grid(row=exposure_settings_row,column=1,padx=10,pady=5,sticky="nsew")

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

def _make_entry(frame: ctk.CTkFrame,name: str, setting: Settings, initial_value: str,entry_validator: Callable[...,bool],units: str|None = None,map_fun: Callable[[str],Any]|None = None) -> tuple[ctk.CTkLabel,_SettingVariable,ctk.CTkEntry,ctk.CTkFrame]:
    lbl = ctk.CTkLabel(frame,text=name)
    ctkvar = ctk.StringVar(value=initial_value)
    var = _SettingVariable(ctkvar,setting,validator=lambda val: entry_validator(val,allow_empty=False),map_fun=map_fun)
    entryparent = ctk.CTkFrame(frame)
    entry = ctk.CTkEntry(entryparent,textvariable=ctkvar, validate='key', validatecommand = (frame.register(entry_validator),"%P"))
    var.widget = entry
    if units:
        entry.grid(row=0,column=0,padx=0,pady=0,sticky="nsew")
        unit_label = ctk.CTkLabel(entryparent,text=units)
        unit_label.grid(row=0,column=1,padx=10,pady=0,sticky="nsw")
    else:
        entry.grid(row=0,column=0,columnspan=2,padx=0,pady=0,sticky="nsew")
    return lbl,var,entry,entryparent
          
def _make_and_grid(frame: ctk.CTkFrame,name: str, setting: Settings, initial_value: str,entry_validator: Callable[...,bool],grid_row: int,units: str|None = None, map_fun: Callable[[str],Any]|None = None) -> tuple[_SettingVariable,ctk.CTkEntry]:
    lbl,var,entry,entryframe = _make_entry(frame,name,setting,initial_value,entry_validator,units=units,map_fun=map_fun)
    lbl.grid(row=grid_row,column=0,padx=10,pady=5,sticky="nsew")
    entryframe.grid(row=grid_row,column=1,padx=10,pady=5,sticky="nsew")
    return var,entry

def _validate_time_float(timestr: str, allow_empty = True):
    if timestr == "":
        return allow_empty
    try:
        t = float(timestr)
        if t>0:
            return True
        return False
    except:
        return False

def _validate_exposure(exp: str, allow_empty: bool = True) -> bool:
    if exp in ("","-",".") and allow_empty:
        return True
    try:
        int(exp)
        return True
    except:
        return False
