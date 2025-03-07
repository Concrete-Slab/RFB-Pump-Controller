from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, Generic, TypeVar
from PIL import Image
import customtkinter as ctk
from ui_root import UIController
from .PROFILE_EDIT_EVENTS import MEvents
from ui_pages.ui_widgets import ApplicationTheme
from enum import Enum
from microcontroller import PinDefs

class _ProfileMode(Enum):
    AUTO = "Generate code"
    MANUAL = "Use own code"

class ProfileEditPage(ctk.CTkFrame):

    BOX_WIDTH = 300
    BOX_HEIGHT = 300
    DEFAULT_MODE = _ProfileMode.AUTO
    DEFAULT_PORT_PROMPT = "Select Serial Port"
    DEFAULT_STATUS = "Select a Serial Port and Set Up Pumps"

    def __init__(self, parent, controller: UIController, new_page: bool, pump_names: list[str], *args, **kwargs):
        super().__init__(parent,width=ProfileEditPage.BOX_WIDTH,height=ProfileEditPage.BOX_HEIGHT)

        self.controller = controller
        self.__serial_ports = [self.DEFAULT_PORT_PROMPT]
        self.__serial_descriptions = [""]
        self.__serial_display = self._format_serial()
        self.max_pumps = len(pump_names)
        allowable_pump_names = pump_names

        self.columnconfigure([0,1,2],weight=1,uniform="base_buttons")
        self.rowconfigure([0,1,2],weight=1)

        main_frame = ctk.CTkFrame(self)
        main_frame.columnconfigure([0,2],weight=0)
        main_frame.columnconfigure([1],weight=1)

        # ------- STATUS LABEL -------------------------------------------

        self._status_var = ctk.StringVar(value=self.DEFAULT_STATUS)
        self.status_lbl = ctk.CTkLabel(self,textvariable=self._status_var)

        # ------- NAME BOX -------------------------------------------
        name_lbl = ctk.CTkLabel(main_frame,text="Profile Name:")
        self.name_var = ctk.StringVar(value="")
        self.name_var.trace_add("write",self.__update_statuses)
        if not new_page:
            self.profile_name_display = _NameLabel(main_frame,text="",textvariable=self.name_var)
        else:
            self.profile_name_display = _NameEntry(
                main_frame,
                textvariable=self.name_var,
                justify="center",
                validate="key",
                validatecommand=(self.register(name_validator),"%S")
            )

        # ------- SERIAL PORTS BOX ---------------------------------
        self._serial_dropdown = ctk.CTkComboBox(main_frame,values=self.__serial_ports)
        serial_lbl = ctk.CTkLabel(main_frame,text="Serial Port:")
        fullpath = Path(__file__).absolute().parent.parent/"ui_widgets"/"assets"/"refresh_label.png"
        pilimg = Image.open(fullpath.as_posix())
        refresh_image = ctk.CTkImage(light_image=pilimg,size=(20,20))
        serial_refresh = ctk.CTkButton(main_frame,text=None,image=refresh_image,command=lambda: self.controller.notify_event(MEvents.RequestPorts()),width=21)

        # ------- MODE BOX -----------------------------------------
        self.mode_var = ctk.StringVar(self,value=self.DEFAULT_MODE.value)
        mode_switcher = ctk.CTkSegmentedButton(main_frame,values=[p.value for p in _ProfileMode],variable=self.mode_var,corner_radius=ApplicationTheme.BUTTON_CORNER_RADIUS,)
        self.mode_var.trace_add("write",self.__mode_change)
        self.mode_var.trace_add("write",self.__update_statuses)

        # -------- MANUAL CODE CONFIGURATION BOX -------------------
        self.manual_frame = ctk.CTkFrame(main_frame, fg_color = main_frame.cget("fg_color"))
        self.manual_frame.columnconfigure([0,1],weight=1,uniform="manual_cols")
        pmp_lbl = ctk.CTkLabel(self.manual_frame,text="Number of Pumps:")
        self.num_pumps_var = ctk.StringVar(value="")
        self._pmp_entry = ctk.CTkEntry(
            self.manual_frame,
            textvariable=self.num_pumps_var,
            justify="center",
            validate="key",
            validatecommand=(self.register(self._pump_validator),"%P")
        )
        self.num_pumps_var.trace_add("write",self.__update_statuses)
        pmp_lbl.grid(row=0,column=0,**ApplicationTheme.GRID_STD)
        self._pmp_entry.grid(row=0,column=1,**ApplicationTheme.GRID_STD)




        # -------- AUTO CODE CONFIGURATION BOX ---------------------
        self.auto_frame = ctk.CTkFrame(main_frame, bg_color = main_frame.cget("bg_color"))
        self.auto_pins = _AutoFrame(self.auto_frame,allowable_pump_names, add_remove_command=self.__update_statuses)
        self.auto_pins.trace_add(self.__update_statuses)
        self.auto_pins.grid(row=0,column=0,**ApplicationTheme.GRID_BOX)
        self.generate_section = _GenerateFrame(self.auto_frame,self.__on_generate)
        self.generate_section.grid(row=1,column=0,**ApplicationTheme.GRID_BOX)


        

        # ------- PUTTING IT ALL TOGETHER --------------------------
        name_lbl.grid(row=0,column=0,**ApplicationTheme.GRID_STD)
        self.profile_name_display.grid(row=0,column=1,columnspan=2,**ApplicationTheme.GRID_STD)
        serial_lbl.grid(row=1,column=0,**ApplicationTheme.GRID_STD)
        self._serial_dropdown.grid(row=1,column=1,**ApplicationTheme.GRID_STD)
        serial_refresh.grid(row=1,column=2,**ApplicationTheme.GRID_STD)
        mode_switcher.grid(row=2,column=0,columnspan=3,**ApplicationTheme.GRID_STD)

        # grid the two frames so their grid settings are stored
        self.auto_frame.grid(row=3,column=0,columnspan=3,**ApplicationTheme.GRID_BOX)
        self.auto_frame.grid_remove()
        self.manual_frame.grid(row=3,column=0,columnspan=3,**ApplicationTheme.GRID_BOX)
        self.manual_frame.grid_remove()
        
        main_frame.grid(row=1,column=0,columnspan=3,**ApplicationTheme.GRID_STD)

        self.status_lbl.grid(row=0,column=0,columnspan=2,**ApplicationTheme.GRID_STD)
        self.confirm_button = ctk.CTkButton(self,text="Save",command=self.__confirm)
        cancel_button = ctk.CTkButton(self,text="Cancel",command=self.__cancel)
        cancel_button.grid(row=2,column=0,padx=10,pady=5,sticky="nsw")
        self.confirm_button.grid(row=2,column=2,padx=10,pady=5,sticky="nse")


        self.controller.add_listener(MEvents.UpdatePorts,self.__update_ports)
        self.controller.add_listener(MEvents.NotifyGenerated,self.__after_generate)
        self.controller.add_listener(MEvents.Error,self.__on_error)
        self.controller.notify_event(MEvents.RequestPorts())


        if new_page:
            self.__update_statuses()
            self.__mode_change()
        else:
            self.controller.add_listener(MEvents.UpdateAutoprofile,self.__update_auto_profile)
            self.controller.add_listener(MEvents.UpdateManualProfile,self.__update_manual_profile)
            self.controller.notify_event(MEvents.RequestProfile())

    def __on_error(self, event: MEvents.Error):
        self._status_var.set(f"Error: {str(event.err)}")
        if isinstance(event.err,ValueError):
            self.profile_name_display.show_error()
            self.status_lbl.configure(text_color=ApplicationTheme.ERROR_COLOR)

    def __on_generate(self):
        if not self.auto_pins.check_valid():
            self.generate_section.state = ctk.DISABLED
            return
        name = self.name_var.get()
        if name == "":
            return
        try:
            pins = self.auto_pins.values
            self.controller.notify_event(MEvents.GenerateCode(name,pins))
        except ValueError as ve:
            return

    def __after_generate(self, event: MEvents.NotifyGenerated):
        self.generate_section.code_location = str(event.code_path)

    def __update_auto_profile(self, event: MEvents.UpdateAutoprofile):
        self.name_var.set(event.name)
        self.selected_port = event.serial_port
        self.auto_pins.values=event.pin_assignments
        self.mode_var.set(_ProfileMode.AUTO.value)
        self.__mode_change()

    def __update_manual_profile(self, event: MEvents.UpdateManualProfile):
        self.name_var.set(event.name)
        self.selected_port = event.serial_port
        self.num_pumps_var.set(event.num_pumps)
        self.mode_var.set(_ProfileMode.MANUAL.value)
        self.__mode_change()

    def __cancel(self):
        #TODO the logic for this call stack breaks at the controller for some reason
        self.controller.notify_event(MEvents.Cancel())

    def __mode_change(self,*args):
        new_mode = _ProfileMode(self.mode_var.get())
        match new_mode:
            case _ProfileMode.MANUAL:
                self.auto_frame.grid_remove()
                self.manual_frame.grid()
            case _ProfileMode.AUTO:
                self.manual_frame.grid_remove()
                self.auto_frame.grid()

    def __update_statuses(self,*args):
        # don't always check for name errors, so automatically clear them if the user types something
        self.profile_name_display.clear_error()

        # initialisation
        confirm_state = self.confirm_button.cget("state")
        generate_state = self.generate_section.state
        new_generate_state = ctk.DISABLED
        new_confirm_state = ctk.DISABLED
        
        # validation results
        name_val = self.name_var.get() != ""
        serial_val = True
        auto_val = self.auto_pins.is_ready
        num_pumps_val = self._pump_validator(self.num_pumps_var.get(),allow_empty=False)
        mode_val = auto_val if self.auto_mode else num_pumps_val

        # confirm button on/off
        if name_val and mode_val and serial_val:
            new_confirm_state = ctk.NORMAL
        if confirm_state != new_confirm_state:
            self.confirm_button.configure(state=new_confirm_state)

        # generate button on/off
        if auto_val and name_val:
            new_generate_state = ctk.NORMAL
        if generate_state != new_generate_state:
            self.generate_section.state = new_generate_state

    def __update_ports(self, event: MEvents.UpdatePorts):
        self.__serial_ports = event.ports
        self.__serial_descriptions = event.descriptions

        current_port = self._serial_dropdown.get()
        if current_port not in self.__serial_ports:
            self.__serial_ports.append(self.DEFAULT_PORT_PROMPT)
            self.__serial_descriptions.append("")
        
        self.__serial_display = self._format_serial()

        self._serial_dropdown.configure(values=self.__serial_display,require_redraw=True)

    def __confirm(self):
        serial_port = self.selected_port
        if serial_port == self.DEFAULT_PORT_PROMPT:
            self._serial_dropdown.configure(border_color=ApplicationTheme.ERROR_COLOR)
            return
        else:
            self._serial_dropdown.configure(border_color=ApplicationTheme.BORDER_COLOR)
        
        profile_name = self.name_var.get()
        if profile_name == "" or not all([name_validator(s) for s in profile_name]):
            
            return
        
        if self.auto_mode:
            if not self.auto_pins.check_valid():
                return
            pin_tuples = self.auto_pins.values
            code_loc = self.generate_section.code_location
            self.controller.notify_event(MEvents.SaveAutoProfile(profile_name,serial_port,pin_tuples,code_location=code_loc))
        else:
            num_pumps = self.num_pumps_var.get()
            if self._pump_validator(num_pumps,allow_empty=False):
                self._pmp_entry.configure(border_color=ApplicationTheme.BORDER_COLOR)
            else:
                self._pmp_entry.configure(border_color=ApplicationTheme.ERROR_COLOR)
                return
            self.controller.notify_event(MEvents.SaveManualProfile(profile_name,serial_port,int(num_pumps)))

    @property
    def selected_port(self):
        portdesc = self._serial_dropdown.get()
        i = self.__serial_display.index(portdesc)
        return self.__serial_ports[i]
    @selected_port.setter
    def selected_port(self, port:str):
        try:
            idx = self.__serial_ports.index(port)
            self._serial_dropdown.set(self.__serial_display[idx])
        except ValueError as ve:
            raise ve #TODO change this to something better

    @property
    def auto_mode(self) -> bool:
        return _ProfileMode(self.mode_var.get()) == _ProfileMode.AUTO

    def _format_serial(self):
        return [(f"{self.__serial_ports[i]} - {self.__serial_descriptions[i]}" if self.__serial_descriptions[i] != "" else self.__serial_ports[i]) for i in range(0,len(self.__serial_descriptions))]


    def _pump_validator(self, p, allow_empty=True):
        if str.isdigit(p) and int(p)>0 and int(p) < self.max_pumps:
            return True
        elif p == "" and allow_empty:
            return True
        return False

def pin_validator(p, allow_empty=True):
    if str.isdigit(p) and int(p)>0 and int(p):
        return True
    elif p == "" and allow_empty:
        return True
    return False

def name_validator(s: str):
    if s in set("abcdefghijklmnopqrstuvwxyz1234567890_-"):
        return True
    return False

class _GenerateFrame(ctk.CTkFrame):

    _DISPLAY = "Code Location: "

    def __init__(self, master: ctk.CTkFrame, on_generate: Callable[[None],None]):
        super().__init__(master,bg_color=master.cget("bg_color"),corner_radius=0)
        self._generate_button = ctk.CTkButton(self,text="Generate Code",command = on_generate)
        self.columnconfigure([0,1,2], weight=1)
        self._generate_button.grid(row=0,column=0,**ApplicationTheme.GRID_NS,columnspan=3)
        self._generate_textvar = ctk.StringVar(value=self._DISPLAY)
        self._generate_label = ctk.CTkLabel(self,textvariable=self._generate_textvar)

    @property
    def state(self):
        return self._generate_button.cget("state")
    @state.setter
    def state(self,new_state):
        self._generate_button.configure(state=new_state)

    @property
    def code_location(self) -> str|None:
        loc_and_disp = self._generate_textvar.get()
        if len(loc_and_disp) <= len(self._DISPLAY):
            return None
        return loc_and_disp[len(self._DISPLAY):]
    @code_location.setter
    def code_location(self, new_code_location: str):
        self._generate_textvar.set(self._DISPLAY+new_code_location)
        if len(new_code_location) > 0:
            self._generate_label.grid(row=1,column=0,**ApplicationTheme.GRID_STD)

class _AutoFrame(ctk.CTkFrame):
    _PUMP_TEXT = "Pump Name"
    _TACHO_TEXT = "Tacho Pin"
    _PWM_TEXT = "Duty Pin"

    _TACHO_COLUMN = 2
    _PWM_COLUMN = 1

    def __init__(self, master: ctk.CTkFrame, allowable_pump_names: list[str], add_remove_command: Callable[[None],None] = lambda: None):
        super().__init__(master, bg_color = master.cget("bg_color"), corner_radius=0)

        def add_command():
            self._add()
            add_remove_command()
        
        def remove_command():
            self._remove()
            add_remove_command()


        self._names = allowable_pump_names
        self.widget_list: list[_AutoWidgetGroup] = [_AutoWidgetGroup(self,self._names[0])]
        self._trace_fns: list[Callable[[str,str,str],None]] = []

        self._add_button = ctk.CTkButton(self,text="+",width=21,height=21,command=add_command)
        self._remove_button = ctk.CTkButton(self,text="-",width=21,height=21,command=remove_command)
        self.columnconfigure([0,1,2],weight=1,uniform="pins")
        self.columnconfigure([3,4],weight=0,uniform="addremove")
        pmp_lbl = ctk.CTkLabel(self,text=self._PUMP_TEXT)
        tacho_lbl = ctk.CTkLabel(self,text=self._TACHO_TEXT)
        pwm_lbl = ctk.CTkLabel(self,text=self._PWM_TEXT)
        pmp_lbl.grid(row=0,column=0,**ApplicationTheme.GRID_STD)
        tacho_lbl.grid(row=0,column=_AutoFrame._TACHO_COLUMN,**ApplicationTheme.GRID_STD)
        pwm_lbl.grid(row=0,column=_AutoFrame._PWM_COLUMN,**ApplicationTheme.GRID_STD)
        self._regrid()

    def _regrid(self):
        for i in range(0,len(self.widget_list)):
            self.widget_list[i].grid(i+1)
        self._place_addremove()

    def _place_addremove(self):
        index = len(self.widget_list)
        self._add_button.grid_remove()
        self._remove_button.grid_remove()
        self._add_button.grid(row=index,column=3,**ApplicationTheme.GRID_STD)
        self._remove_button.grid(row=index,column=4,**ApplicationTheme.GRID_STD)
        if len(self.widget_list) <= 1:
            self._remove_button.configure(state=ctk.DISABLED)
        else:
            self._remove_button.configure(state=ctk.NORMAL)

        if len(self.widget_list) >= len(self._names):
            self._add_button.configure(state=ctk.DISABLED)
        else:
            self._add_button.configure(state=ctk.NORMAL)

    def _add(self):
        idx = len(self.widget_list)
        next_name = self._names[idx]
        next_widget = _AutoWidgetGroup(self,next_name)
        for fun in self._trace_fns:
            next_widget.pwm_var.trace_add("write",fun)
            next_widget.tacho_var.trace_add("write",fun)
        next_widget.grid(idx+1)
        self.widget_list.append(next_widget)
        self._place_addremove()

    def _remove(self):
        self.widget_list.pop().grid_forget()
        self._place_addremove()

    def trace_add(self,tracefun: Callable[[str,str,str],None]):
        self._trace_fns.append(tracefun)
        for w_group in self.widget_list:
            w_group.pwm_var.trace_add("write",tracefun)
            w_group.tacho_var.trace_add("write",tracefun)


    @property
    def values(self):
        return [w.pins for w in self.widget_list]
    
    @values.setter
    def values(self, new_values: list[PinDefs]):
        self.widget_list = [_AutoWidgetGroup(self,self._names[i]) for i in range(0,len(new_values))]

        for i in range(0,len(new_values)):
            self.widget_list[i].pins = new_values[i]
        self._regrid()

    def check_valid(self):
        return all([w.check_ready() for w in self.widget_list])

    @property
    def is_ready(self):
        return all([w.is_ready for w in self.widget_list])

class _AutoWidgetGroup:

    def __init__(self, master: ctk.CTkFrame, name: str):
        self._lbl = ctk.CTkLabel(master,text=f"Pump {name.upper()}")
        self.pwm_var = ctk.StringVar(value="")
        self._pwm_entry = ctk.CTkEntry(
            master,
            textvariable=self.pwm_var,
            justify="center",
            validate="key",
            validatecommand=(master.register(pin_validator),"%P")
        )
        self.tacho_var = ctk.StringVar(value="")

        self._tacho_entry = ctk.CTkEntry(
            master,
            textvariable=self.tacho_var,
            justify="center",
            validate="key",
            validatecommand=(master.register(pin_validator),"%P")
        )

    def check_ready(self):
        pwm = pin_validator(self.pwm_var.get(),allow_empty=False)
        pwm_color = ApplicationTheme.BORDER_COLOR if pwm else ApplicationTheme.ERROR_COLOR

        tacho = pin_validator(self.tacho_var.get(),allow_empty=False)
        tacho_color = ApplicationTheme.BORDER_COLOR if tacho else ApplicationTheme.ERROR_COLOR

        self._pwm_entry.configure(border_color=pwm_color)
        self._tacho_entry.configure(border_color=tacho_color)
        
        return pwm and tacho

    @property
    def is_ready(self) -> bool:
        return pin_validator(self.pwm_var.get(),allow_empty=False) and pin_validator(self.tacho_var.get(),allow_empty=False)

    @property
    def pins(self) -> PinDefs:
        if self.check_ready():
            # format is [tacho,pwm]!!!!!!!!!
            # return (int(self.tacho_var.get()),int(self.pwm_var.get()))
            pwm_pin = int(self.pwm_var.get())
            tacho_val = self.tacho_var.get()
            tacho_pin = int(tacho_val) if pin_validator(tacho_val,allow_empty=False) else -1
            return PinDefs(tacho_pin,pwm_pin)
        raise ValueError("PWM and/or tacho entries have invalid inputs")
    
    @pins.setter
    def pins(self,new_value: PinDefs):
        if new_value.tacho_pin<0:
            self.tacho_var.set("")
        else:
            self.tacho_var.set(str(new_value.tacho_pin))
        self.pwm_var.set(str(new_value.pwm_pin))
    
    def grid(self,row):
        self._lbl.grid(row=row,column=0,**ApplicationTheme.GRID_STD)
        self._pwm_entry.grid(row=row,column=_AutoFrame._PWM_COLUMN,**ApplicationTheme.GRID_STD)
        self._tacho_entry.grid(row=row,column=_AutoFrame._TACHO_COLUMN,**ApplicationTheme.GRID_STD)
    
    def grid_forget(self):
        self._lbl.grid_forget()
        self._pwm_entry.grid_forget()
        self._tacho_entry.grid_forget()

_T = TypeVar("_T",bound=ctk.CTkBaseClass)
class _NameWidget(Generic[_T],ABC):
    @abstractmethod
    def show_error(self):
        raise NotImplementedError()
    @abstractmethod
    def clear_error(self):
        raise NotImplementedError()
    
class _NameEntry(ctk.CTkEntry,_NameWidget[ctk.CTkEntry]):
    def clear_error(self):
        self.configure(border_color=ApplicationTheme.BORDER_COLOR)
    def show_error(self):
        self.configure(border_color=ApplicationTheme.ERROR_COLOR)

class _NameLabel(ctk.CTkLabel,_NameWidget[ctk.CTkLabel]):
    def clear_error(self):
        self.configure(text_color=ApplicationTheme.WHITE)
    def show_error(self):
        self.configure(text_color=ApplicationTheme.ERROR_COLOR)
