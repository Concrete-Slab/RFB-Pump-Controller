import copy
from ui_pages.pump_controller_page.processes.base_process import BaseProcess
from ui_pages.pump_controller_page.CONTROLLER_EVENTS import ProcessName
from support_classes import PumpNames, Settings, PumpConfig, read_settings, PID_SETTINGS, PID_PUMPS, modify_settings
from typing import Any, Callable
from ui_root import AlertBoxBase, AlertBox
import customtkinter as ctk
from ui_pages.ui_layout import WidgetGroup, make_and_group, make_entry, make_menu, make_segmented_button, validator_function, ApplicationTheme

class PIDProcess(BaseProcess):
    @property
    def name(self):
        return "PID"
    
    def start(self):
        (state_running,_) = self._pump_context.start_pid()
        self._monitor_running(state_running)
    
    def close(self):
        self._pump_context.stop_pid()
    
    @classmethod
    def process_name(cls):
        return ProcessName.PID
    @property
    def settings_constructor(self):
        return PIDSettingsBox.default


class _PIDSettingsFrame(AlertBoxBase[dict[Settings,Any]]):

    ALERT_TITLE = "PID Settings"

    def __init__(self, master: ctk.CTk, *args, on_success: Callable[..., None] | None = None, on_failure: Callable[[None], None] | None = None, fg_color: str | tuple[str, str] | None = None, **kwargs):
        super().__init__(master, *args, on_success=on_success, on_failure=on_failure, fg_color=fg_color, **kwargs)
        self.title(self.ALERT_TITLE)

        default_options = ["None"]
        for pmpname in PumpConfig().pumps:
            default_options.append(pmpname.value.lower())

        pid_settings = read_settings(*PID_SETTINGS)
        pump_settings: dict[Settings,PumpNames|None] = {key:pid_settings[key] for key in PID_PUMPS}


        frame_list, _, _ = self.generate_layout("Pump Assignments","Control Parameters",confirm_command=self.__confirm_selections)
        pump_frame = frame_list[0]
        control_frame = frame_list[1]

        self.pump_group = WidgetGroup(initial_row=0)
        an_var = make_and_group(make_menu,
                                 pump_frame,
                                 "Anolyte Pump",
                                 Settings.ANOLYTE_PUMP,
                                 _json2str(pump_settings[Settings.ANOLYTE_PUMP]),
                                 self.pump_group,
                                 map_fun=_str2json,
                                 values=default_options
                                 )
        cath_var = make_and_group(make_menu,
                                 pump_frame,
                                 "Catholyte Pump",
                                 Settings.CATHOLYTE_PUMP,
                                 _json2str(pump_settings[Settings.CATHOLYTE_PUMP]),
                                 self.pump_group,
                                 map_fun=_str2json,
                                 values=default_options
                                 )
        an_re_var = make_and_group(make_menu,
                                 pump_frame,
                                 "Anolyte Refill Pump",
                                 Settings.ANOLYTE_REFILL_PUMP,
                                 _json2str(pump_settings[Settings.ANOLYTE_REFILL_PUMP]),
                                 self.pump_group,
                                 map_fun=_str2json,
                                 values=default_options
                                 )
        cath_re_var = make_and_group(make_menu,
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

        self.control_group = WidgetGroup(initial_row=0)
        base_duty_var = make_and_group(make_entry,
                                        control_frame,
                                        "Equilibrium Control Duty",
                                        Settings.BASE_CONTROL_DUTY,
                                        pid_settings[Settings.BASE_CONTROL_DUTY],
                                        self.control_group,
                                        map_fun=int,
                                        entry_validator = _validate_duty,
                                        on_return = self.__confirm_selections
                                        )
        kp_var = make_and_group(make_entry,
                                 control_frame,
                                 "Proportional Gain",
                                 Settings.PROPORTIONAL_GAIN,
                                 pid_settings[Settings.PROPORTIONAL_GAIN],
                                 self.control_group,
                                 map_fun=float,
                                 entry_validator = _validate_gain,
                                 on_return = self.__confirm_selections)
        
        ki_var = make_and_group(make_entry,
                                 control_frame,
                                 "Integral Gain",
                                 Settings.INTEGRAL_GAIN,
                                 pid_settings[Settings.INTEGRAL_GAIN],
                                 self.control_group,
                                 map_fun=float,
                                 entry_validator = _validate_gain,
                                 on_return = self.__confirm_selections)
        
        kd_var = make_and_group(make_entry,
                                 control_frame,
                                 "Derivative Gain",
                                 Settings.DERIVATIVE_GAIN,
                                 pid_settings[Settings.DERIVATIVE_GAIN],
                                 self.control_group,
                                 map_fun=float,
                                 entry_validator = _validate_gain,
                                 on_return = self.__confirm_selections)
        rf_duty_var = make_and_group(make_entry,
                                        control_frame,
                                        "Refill Duty",
                                        Settings.REFILL_DUTY,
                                        pid_settings[Settings.REFILL_DUTY],
                                        self.control_group,
                                        map_fun=int,
                                        entry_validator = _validate_duty,
                                        on_return = self.__confirm_selections
                                        )
        rf_percent_var = make_and_group(make_entry,
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
        rf_cooldown_var = make_and_group(make_entry,
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
        
        self.time_cutoff_group = WidgetGroup(initial_row=10,parent=self.control_group)
        rf_time_var = make_and_group(make_entry,
                                        control_frame,
                                        "Refill Time",
                                        Settings.REFILL_TIME,
                                        pid_settings[Settings.REFILL_TIME],
                                        self.time_cutoff_group,
                                        map_fun=float,
                                        units="s",
                                        entry_validator = _validate_time_float,
                                        on_return = self.__confirm_selections
                                        )
        
        self.__rf_stop_method_var = make_and_group(make_segmented_button,
                                        control_frame,
                                        "Cutoff Method",
                                        Settings.REFILL_STOP_ON_FULL,
                                        "Stop when full" if pid_settings[Settings.REFILL_STOP_ON_FULL] else "Stop after time",
                                        self.control_group,
                                        lambda str_in: str_in == "Stop when full",
                                        values = ["Stop when full","Stop after time"],
                                        command = self.__hide_show_time_cutoff
                                        )
        
        self.control_group.show()
        self.__hide_show_time_cutoff()
        

    def __update_selections(self,var_index,*args):
        # make sure there are no duplicate selections
        vars_copy = copy.copy(self.pump_group.get_vars())
        selected_value = vars_copy.pop(var_index).get()
        if selected_value != "None":
            for var in vars_copy:
                value = var.get()
                if value == selected_value:
                    var.set("None")

    def __hide_show_time_cutoff(self,*args,**kwargs):
        if self.__rf_stop_method_var.get_mapped():
            self.time_cutoff_group.hide()
        else:
            self.time_cutoff_group.show()

        
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
        out = PumpConfig().pumps(res)
    return out

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
def _validate_gain(str_in: str, allow_empty = True) -> bool:
    if str_in in ("","-") and allow_empty:
        return True
    try:
        float(str_in)
        return True
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


class PIDSettingsBox(AlertBox[dict[Settings,Any]]):
    def __init__(self, on_success = None, on_failure = None, auto_resize=True):
        super().__init__(on_success, on_failure, auto_resize)
    def create(self, root):
        return _PIDSettingsFrame(root,on_success=self.on_success,on_failure=self.on_failure)
