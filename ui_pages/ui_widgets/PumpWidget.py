import customtkinter as ctk
from .InfoBox import InfoBox, formatter
from .ValueSetterWidget import ValueSetterWidget
from .themes import ApplicationTheme
from typing import Callable


class PumpWidget(ctk.CTkFrame):

    def __init__(self, parent, identifier: str, duty_callback: Callable[[int],None]|None = None, widget_width = 300, widget_height = 60):
        super().__init__(parent,fg_color=ApplicationTheme.MANUAL_PUMP_COLOR)
        self._pumpName = identifier

        self.columnconfigure([1,2,3],weight=2,uniform="col")
        self.columnconfigure(0,weight=1,uniform="col")
        self.rowconfigure([0],weight=1)

        self.pump_label = ctk.CTkLabel(self,
                                       text="Pump " + identifier.capitalize(), 
                                       text_color=ApplicationTheme.WHITE, 
                                       font=ctk.CTkFont(family=ApplicationTheme.FONT, 
                                                        size=ApplicationTheme.INPUT_FONT_SIZE)
                                        )
        self.pump_label.grid(row=1,column=0,padx=10,pady=10,sticky="")

        self.speedVar = ctk.DoubleVar(value=0)
        self._speedWidget = InfoBox(self, self.speedVar,max_value=12300, width = widget_width, height= widget_height, format_fun=format_speed)
        self._speedWidget.grid(row=1, column=1, sticky="nsew", padx=10, pady=10)

        self.dutyVar = ctk.DoubleVar(value=0)
        self._dutyWidget = InfoBox(self, self.dutyVar, max_value=255, width = widget_width, height=widget_height, max_digits=3)
        self._dutyWidget.grid(row=1, column=2, sticky="nsew", padx=10, pady=10)

        self._dutySetter = ValueSetterWidget(self, self.dutyVar, value_callback = lambda flt: duty_callback(int(flt)))
        self._dutySetter.grid(row=1, column=3, padx=10, pady=10, sticky="nsew")

    def set_bgcolor(self,new_color: str):
        self.configure(fg_color=new_color,require_redraw=True)

    def apply(self):
        self._dutySetter.update_value()

    def destroy(self):
        # TODO end the serial connection
        super().destroy()

@formatter
def format_speed(spd: float) -> str:
    spd_str = "{:.2f}".format(spd)
    return spd_str


