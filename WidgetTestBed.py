import customtkinter as ctk
from typing import Callable
from ui_root import UIRoot

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
        # set up your widget here (with parent as its master widget) and replace the return statement below
        return ctk.CTkLabel(parent,text = "Hello World")
    test_widget(widgetfun)
