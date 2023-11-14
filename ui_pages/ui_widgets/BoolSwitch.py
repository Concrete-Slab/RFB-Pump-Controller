import customtkinter as ctk
from enum import Enum
from .themes import ApplicationTheme
from typing import Callable


class SwitchState(Enum):
    OFF = 0
    STARTING = 1
    ON = 2
    CLOSING = 3


class BoolSwitch(ctk.CTkFrame):

    def __init__(self, parent, enum_state: ctk.IntVar, name: str, state_callback: Callable[[SwitchState],None]|None = None):
        super().__init__(parent,fg_color=ApplicationTheme.WHITE)
        self.state_var = enum_state
        self.state_var.trace("w",self.__determine_state)
        self.__name = name
        self.__state_callback = state_callback
        self.button_var = ctk.StringVar(value="")
        self.button = ctk.CTkButton(self, 
                                    textvariable=self.button_var, 
                                    command=self.__iterate_state, 
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
        self.__determine_state()

        self.rowconfigure([0,1],weight=1,uniform="row")
        self.columnconfigure(0,weight=1,uniform="col")
        self.label.grid(row=0,column=0,padx=10,pady=5,sticky="nsew")
        self.button.grid(row=1,column=0,padx=10,pady=5,sticky="nsew")

        

    def __iterate_state(self):
        if self.state_var.get() < 3:
            self.state_var.set(self.state_var.get()+1)
        else:
            self.state_var.set(0)
        if self.__state_callback is not None:
            self.__state_callback(SwitchState(self.state_var.get()))

    def __determine_state(self,*args) -> tuple[str,str]:
        match SwitchState(self.state_var.get()):
            case SwitchState.OFF:
                self.label_var.set(self.__name + " is OFF")
                self.button_var.set("\u23f5")
                self.button.configure(state=ctk.NORMAL)
            case SwitchState.STARTING:
                self.label_var.set(self.__name + " is STARTING...")
                self.button_var.set("\u23f5")
                self.button.configure(state=ctk.DISABLED)
            case SwitchState.ON:
                self.label_var.set(self.__name + " is ON")
                self.button_var.set("\u23f9")
                self.button.configure(state=ctk.NORMAL)
            case SwitchState.CLOSING:
                self.label_var.set(self.__name + " is CLOSING")
                self.button_var.set("\u23f9")
                self.button.configure(state=ctk.DISABLED)
            case _:
                self.label_var.set("Unknown State")
                self.button_var.set("E")
                self.button.configure(state=ctk.DISABLED)
        
        
            

