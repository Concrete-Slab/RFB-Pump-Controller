import customtkinter as ctk
from .themes import ApplicationTheme
from typing import Callable

Formatter = Callable[[float|int],str]
def formatter(f: Formatter) -> Formatter:
    return f


class InfoBox(ctk.CTkFrame):

    def __init__(self,
                 parent,
                 value_var: ctk.DoubleVar,
                 max_value=None,
                 fg_color=ApplicationTheme.WHITE,
                 max_digits: int = 0,
                 format_fun: Formatter = lambda x: str(x)):
        super().__init__(master=parent, fg_color=fg_color)
        self.max_value = max_value
        self.format_fun = format_fun
        self.columnconfigure([0,1],weight=1)
        self.rowconfigure([0],weight=1)

        self.progress_bar = ctk.CTkProgressBar(self,
                                               progress_color=ApplicationTheme.GREEN,
                                               fg_color=ApplicationTheme.LIGHT_GRAY,
                                               )
        self.value_var = value_var
        self.text_var = ctk.StringVar(value=format_fun(self.value_var.get()))
        value_var.trace_add("write", self._update_progress_value)

        
        self.output_text = ctk.CTkLabel(self,
                                        textvariable=self.text_var, text_color=ApplicationTheme.BLACK,
                                        font=ctk.CTkFont(family=ApplicationTheme.FONT,
                                                         size=ApplicationTheme.INPUT_FONT_SIZE),
                                        )
        
        self._update_progress_value()
        self.progress_bar.grid(row=0, column=0, sticky="ew", pady=10, padx=10)
        self.output_text.grid(row=0,column=1,pady=20, padx=20,sticky="nsew")

    def _update_progress_value(self, *args):
        new_val = self.value_var.get()
        self.text_var.set(self.format_fun(new_val))
        if self.max_value is None:
            self.progress_bar.set(new_val)
        else:
            self.progress_bar.set(new_val/self.max_value)


