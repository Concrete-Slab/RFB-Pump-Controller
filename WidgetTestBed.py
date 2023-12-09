from ui_pages import *
import customtkinter as ctk
from typing import Callable
from ui_root import UIRoot
from ui_pages.ui_widgets import BoolSwitch


def test_widget(widget_constructor: Callable[[ctk.CTkFrame], ctk.CTkBaseClass]):
    test_app = UIRoot()
    wrapper = ctk.CTkFrame(test_app)
    wrapper.pack()
    test_subject = widget_constructor(wrapper)
    test_subject.pack()
    test_app.title("Testbed for widget: " + test_subject.__class__.__name__)
    test_app.mainloop()

if __name__ == '__main__':
    def widgetfun(parent: ctk.CTkFrame) -> ctk.CTkBaseClass:
        settings_pressed = lambda: print("Settings")
        state_pressed = lambda x: print("State pressed")
        intvar = ctk.IntVar(value=0)
        name = "Test"
        return BoolSwitch(parent,intvar,name,state_pressed,settings_pressed)
    test_widget(widgetfun)
