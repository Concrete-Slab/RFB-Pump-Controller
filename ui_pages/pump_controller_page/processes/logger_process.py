from ui_pages.pump_controller_page.processes import BaseProcess
from ui_pages.pump_controller_page.CONTROLLER_EVENTS import CEvents, ProcessName
from ui_pages.ui_layout import make_and_grid, make_entry, ApplicationTheme, validator_function
from typing import Any, Callable
from support_classes import Settings, read_settings, LOGGING_SETTINGS, modify_settings
from ui_root import AlertBox, AlertBoxBase
import customtkinter as ctk
from pathlib import Path

class DataProcess(BaseProcess):
    @property
    def name(self) -> str:
        return "Data Logging"
    def start(self):
        state_running = self._pump_context.start_logging()
        if len(self._removal_callbacks) == 0:
            self._removal_callbacks.append(self._controller_context._add_state(state_running,self.__handle_running))
    
    def close(self):
        if self._pump_context and self._controller_context:
            self._pump_context.stop_logging()

    def __handle_running(self,newstate: bool):
        if self._controller_context:
            if newstate:
                self._controller_context.notify_event(CEvents.ProcessStarted(ProcessName.DATA))
            else:
                self._controller_context.notify_event(CEvents.ProcessClosed(ProcessName.DATA))
        

    @property
    def has_settings(self) -> bool:
        return True
    
    def open_settings(self):
        on_success = self.__on_settings_modified
        on_failure = lambda: self._controller_context.notify_event(CEvents.CloseSettings(ProcessName.DATA))
        self._controller_context._create_alert(DataSettingsBox(on_success=on_success,on_failure=on_failure))

    def __on_settings_modified(self,modifications: dict[Settings,Any]):
        if self._controller_context:
            self._controller_context.notify_event(CEvents.SettingsModified(modifications))
            self._controller_context.notify_event(CEvents.CloseSettings(ProcessName.DATA))


class _DataSettingsFrame(AlertBoxBase[dict[Settings,Any]]):

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
        prev_log_period: float = self.__prev_logging_settings[Settings.LOGGING_PERIOD]
        prev_img_period: float = self.__prev_logging_settings[Settings.IMAGE_SAVE_PERIOD]

        try:
            self.__initial_directory = prev_level_directory.parent if prev_level_directory is not None else Path().absolute()
        except:
            self.__initial_directory = Path().absolute()
        
        time_frame = ctk.CTkFrame(self,fg_color=self._fg_color)
        time_frame.rowconfigure([0,1],weight=1,uniform="time_rows")
        time_frame.columnconfigure([0],weight=1,uniform="time_columns")
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

        self.__data_period_var = make_and_grid(
            make_entry,
            time_frame,
            "Data Logging Period",
            Settings.LOGGING_PERIOD,
            prev_log_period,
            0,
            map_fun=float,
            entry_validator=_validate_time_float,
            units="s",
        )
        self.__img_period_var = make_and_grid(
            make_entry,
            time_frame,
            "Image Logging Period",
            Settings.IMAGE_SAVE_PERIOD,
            prev_img_period,
            1,
            map_fun=float,
            entry_validator=_validate_time_float,
            units="s",
        )





        self.columnconfigure([0],weight = 1, uniform = "col")
        directory_frame.grid(row=0,column=0,padx=5,pady=5,sticky="nsew")
        switch_frame.grid(row=0,column=1,padx=5,pady=5,sticky="nsew")
        time_frame.grid(row=0,column=2,padx=5,pady=5,sticky="nsew")

        confirm_button = ctk.CTkButton(self, corner_radius= ApplicationTheme.BUTTON_CORNER_RADIUS, text = "Confirm", command = self.__confirm_settings)
        cancel_button = ctk.CTkButton(self,corner_radius=ApplicationTheme.BUTTON_CORNER_RADIUS,text = "Cancel",command = self.destroy)
        confirm_button.grid(row=1,column=2,padx=5,pady=5,sticky="e")
        cancel_button.grid(row=1,column=0,padx=5,pady=5,sticky="w")
        
    def __select_from_explorer(self):
        init_dir = self.__initial_directory.parent
        new_directory = ctk.filedialog.askdirectory(initialdir = init_dir,mustexist=True)
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
            Settings.LOGGING_PERIOD: self.__data_period_var.get_mapped(),
            Settings.IMAGE_SAVE_PERIOD: self.__img_period_var.get_mapped(),
            Settings.LEVEL_DIRECTORY: (new_logging_directory / "levels"),
            Settings.PID_DIRECTORY: (new_logging_directory / "duties"),
            Settings.SPEED_DIRECTORY: (new_logging_directory / "speeds"),
            Settings.IMAGE_DIRECTORY: (new_logging_directory / "images"),
        }

        modifications = modify_settings(new_logging_settings)
        ## close the window by notifying of modified changes
        self.destroy_successfully(modifications)

class DataSettingsBox(AlertBox[dict[Settings,Any]]):
    def __init__(self, on_success = None, on_failure = None, auto_resize=True):
        super().__init__(on_success, on_failure, auto_resize)
    def create(self, root):
        return _DataSettingsFrame(root,on_success=self.on_success,on_failure=self.on_failure)

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
