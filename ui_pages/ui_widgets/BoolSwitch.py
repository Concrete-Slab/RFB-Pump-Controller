import customtkinter as ctk
from enum import Enum
from ..ui_layout.themes import ApplicationTheme
from typing import Callable
from PIL import Image
from pathlib import Path


class SwitchState(Enum):
    OFF = 0
    STARTING = 1
    ON = 2
    CLOSING = 3


class BoolSwitch(ctk.CTkFrame):

    def __init__(self, parent, enum_state: ctk.IntVar, name: str, state_callback: Callable[[SwitchState],None]|None = None, settings_callback: Callable[[None],None]|None = None):
        super().__init__(parent,fg_color=ApplicationTheme.WHITE,width=100)
        self.state_var = enum_state
        self.state_var.trace_add("write",self._determine_state)
        self._name = name
        self._state_callback = state_callback
        self._settings_callback = settings_callback
        self.button_var = ctk.StringVar(value="")
        self.button = ctk.CTkButton(self, 
                                    textvariable=self.button_var, 
                                    command=self._iterate_state, 
                                    font = ctk.CTkFont(family=ApplicationTheme.FONT, 
                                                        size=ApplicationTheme.INPUT_FONT_SIZE), 
                                    corner_radius=ApplicationTheme.BUTTON_CORNER_RADIUS,
                                    hover_color = ApplicationTheme.GRAY,
                                    fg_color=ApplicationTheme.LIGHT_GRAY, 
                                    text_color=ApplicationTheme.BLACK
                                )
        self.label_var = ctk.StringVar(value="")
        self.label = ctk.CTkLabel(self, 
                                  textvariable=self.label_var, 
                                  text_color=ApplicationTheme.BLACK, 
                                  font = ctk.CTkFont(family=ApplicationTheme.FONT, 
                                                        size=ApplicationTheme.INPUT_FONT_SIZE), 
                                )
        
        self._determine_state()

        self.rowconfigure([0,1],weight=1,uniform="row")
        
        self.settings_button = None
        if settings_callback is not None:
            fullpath = Path().absolute() / "ui_pages/ui_widgets/assets/settings_label.png"
            pilimg = Image.open(fullpath.as_posix())
            settings_image = ctk.CTkImage(light_image=pilimg,size=(20,20))
            self.settings_button = ctk.CTkButton(self,
                                                 command=lambda: self.set_settings_button_active(False),
                                                 image=settings_image,
                                                 text=None,
                                                 corner_radius=ApplicationTheme.BUTTON_CORNER_RADIUS,
                                                 hover_color = ApplicationTheme.GRAY,
                                                 fg_color=ApplicationTheme.LIGHT_GRAY,
                                                )
            self.columnconfigure([0,1],weight=1,uniform="col")
            self.settings_button.grid(row=1,column=1,padx=10,pady=5,sticky="nsew")
        else:
            self.columnconfigure(0,weight=1,uniform="col")
        self.label.grid(row=0,column=0,columnspan=2,padx=10,pady=5,sticky="nsew")
        self.button.grid(row=1,column=0,padx=10,pady=5,sticky="nsew")

    def _iterate_state(self):
        if self.state_var.get() < 3:
            self.state_var.set(self.state_var.get()+1)
        else:
            self.state_var.set(0)
        if self._state_callback is not None:
            self._state_callback(SwitchState(self.state_var.get()))

    def set_settings_button_active(self,isactive: bool):
        if self.settings_button is not None and self._settings_callback is not None:
            if isactive:
                self.settings_button.configure(state=ctk.NORMAL,require_redraw=True)
            else:
                self.settings_button.configure(state=ctk.DISABLED,require_redraw=True)
                self._settings_callback()

    def _determine_state(self,*args) -> tuple[str,str]:
        match SwitchState(self.state_var.get()):
            case SwitchState.OFF:
                self.label_var.set(self._name + " is OFF")
                self.button_var.set("\u23f5")
                self.button.configure(state=ctk.NORMAL)
            case SwitchState.STARTING:
                self.label_var.set(self._name + " is STARTING...")
                self.button_var.set("\u23f5")
                self.button.configure(state=ctk.DISABLED)
            case SwitchState.ON:
                self.label_var.set(self._name + " is ON")
                self.button_var.set("\u23f9")
                self.button.configure(state=ctk.NORMAL)
            case SwitchState.CLOSING:
                self.label_var.set(self._name + " is CLOSING")
                self.button_var.set("\u23f9")
                self.button.configure(state=ctk.DISABLED)
            case _:
                self.label_var.set("Unknown State")
                self.button_var.set("E")
                self.button.configure(state=ctk.DISABLED)
        
class LevelBoolSwitch(BoolSwitch):

    def __init__(self, parent, enum_state: ctk.IntVar, name: str, state_callback: Callable[[SwitchState],None]|None = None, settings_callback: Callable[[None],None]|None = None, ROI_callback: Callable[[None],None]|None = None):
        super().__init__(parent, enum_state,name,state_callback=state_callback,settings_callback=settings_callback)
        self.label.grid_forget()
        self.button.grid_forget()
            
        
        self._ROI_callback = ROI_callback
        self.ROI_button = ctk.CTkButton(self,
                                        command = lambda: self.set_ROI_button_active(False),
                                        text = "\u2316",
                                        font = ctk.CTkFont(family=ApplicationTheme.FONT, 
                                                        size=ApplicationTheme.INPUT_FONT_SIZE),
                                        corner_radius=ApplicationTheme.BUTTON_CORNER_RADIUS,
                                        hover_color=ApplicationTheme.GRAY,
                                        fg_color = ApplicationTheme.LIGHT_GRAY,
                                        text_color=ApplicationTheme.BLACK
                                        )
        self.grid_propagate(False)
        self.rowconfigure([0,1],weight=1,uniform="row")
        if settings_callback:
            self.settings_button.grid_forget()
            self.columnconfigure([0,1,2],weight=1,uniform="col")
            self.settings_button.grid(row=1,column=2,padx=10,pady=5,sticky="nsew")
            self.label.grid(row=0,column=0,columnspan=3,padx=10,pady=5,sticky="nsew")
        else:
            self.columnconfigure([0,1],weight=1,uniform="col")
            self.columnconfigure(0,weight=1,uniform="col")
            self.label.grid(row=0,column=0,columnspan=2,padx=10,pady=5,sticky="nsew")
        self.button.grid(row=1,column=0,padx=10,pady=5,sticky="nsew")
        self.ROI_button.grid(row=1,column=1,padx=10,pady=5,sticky="nsew")
        self.grid_propagate(True)

    def set_ROI_button_active(self,isactive: bool,with_callback: bool = True):
        if isactive:
            self._determine_state()
            self.ROI_button.configure(state=ctk.NORMAL)
            self.settings_button.configure(state=ctk.NORMAL)
            pass
        else:
            self.button.configure(state=ctk.DISABLED)
            self.ROI_button.configure(state=ctk.DISABLED)
            self.settings_button.configure(state=ctk.DISABLED)
            if with_callback:
                self._ROI_callback()
    
    def set_settings_button_active(self,isactive: bool):
        if self.settings_button is not None and self._settings_callback is not None:
            if isactive:
                self.settings_button.configure(state=ctk.NORMAL,require_redraw=True)
                self.ROI_button.configure(state=ctk.NORMAL)
            else:
                self.settings_button.configure(state=ctk.DISABLED,require_redraw=True)
                self.ROI_button.configure(state=ctk.DISABLED)
                self._settings_callback()
            

