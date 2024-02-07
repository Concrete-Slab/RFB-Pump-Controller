import customtkinter as ctk
from .themes import ApplicationTheme
from typing import Callable, Generic, TypeVar
T = TypeVar("T")


class ValueSetterWidget(ctk.CTkFrame):

    def __init__(self,
                 parent,
                 value_var: ctk.DoubleVar,
                 value_callback: Callable[[float],None]|None = None,
                 validation_fun: Callable[[str], bool]|None = None,
                 width = 300,
                 height = 60):
        super().__init__(parent, fg_color=ApplicationTheme.WHITE,width=width,height=height)

        if validation_fun is None:
            validation_fun = ValueSetterWidget.default_validator
        self.value_callback = value_callback

        internal_font = ctk.CTkFont(family=ApplicationTheme.FONT, size=ApplicationTheme.INPUT_FONT_SIZE)
        self.value_var = value_var
        self._entry = ctk.CTkEntry(self,
                                   justify='center',
                                   validate='key',
                                   validatecommand=(self.register(validation_fun), '%P'),
                                   corner_radius=ApplicationTheme.BUTTON_CORNER_RADIUS,
                                   font=internal_font,
                                   )
        self._entry.bind('<Return>', command=lambda event: self.update_value())
        self._entry.bind('<FocusOut>', command=lambda event: self.focus_set(), add="+")
        self._button = ctk.CTkButton(self,
                                     command=self.update_value,
                                     text='Apply',
                                     font=internal_font,
                                     text_color=ApplicationTheme.BLACK,
                                     fg_color=ApplicationTheme.LIGHT_GRAY,
                                     hover_color=ApplicationTheme.GRAY,
                                     corner_radius=ApplicationTheme.BUTTON_CORNER_RADIUS,
                                     )
        self.columnconfigure([0,1],weight=1)
        self.rowconfigure([0],weight=1)

    def update_value(self):
        val = self._entry.get()
        self._entry.delete(0, ctk.END)
        self.focus_set()
        if val != '':
            self.value_var.set(value=int(val))
            if self.value_callback is not None:
                self.value_callback(val)
    
    def grid(self,**kwargs):
        super().grid(**kwargs)
        self._button.grid(row=0, column=1, padx=8, pady=8,sticky="ew")
        self._entry.grid(row=0, column=0, padx=8, pady=8,sticky="ew")

    @staticmethod
    def default_validator(p):
        if str.isdigit(p) or p == "":
            if p == "":
                return True
            elif int(p) < 256:
                return True
            else:
                return False
        else:
            return False
