from ui_pages import *
import customtkinter as ctk
from typing import Callable
from ui_pages.ui_widgets import PumpWidget,ValueSetterWidget,BoolSwitch
from ui_root.CTkPollable import CTkPollable
import threading
import atexit


def test_widget(widget_constructor: Callable[[ctk.CTkFrame], ctk.CTkBaseClass]):
    test_app = CTkPollable()
    wrapper = ctk.CTkFrame(test_app)
    wrapper.pack()
    test_subject = widget_constructor(wrapper)
    test_subject.pack()
    test_app.title("Testbed for widget: " + test_subject.__class__.__name__)
    test_app.mainloop()

if __name__ == '__main__':
    def widgetfun(parent: ctk.CTkFrame) -> ctk.CTkBaseClass:
        controller = PortSelectController(debug=True)
        return PortSelectPage(parent,controller)
        # return PumpWidget(parent,"a")
        # return ControllerPage(parent,["a","b","c","d","e","f"])
    test_widget(widgetfun)
