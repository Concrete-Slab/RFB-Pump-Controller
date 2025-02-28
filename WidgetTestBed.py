import customtkinter as ctk
from typing import Callable
from ui_pages.profile_edit_page import ProfileEditPage
from ui_root import UIRoot
from ui_pages.profile_edit_page import ProfileEditPageController

def test_widget(widget_constructor: Callable[[ctk.CTkFrame], ctk.CTkBaseClass]):
    test_app = UIRoot()
    wrapper = ctk.CTkFrame(test_app)
    wrapper.pack()
    test_subject = widget_constructor(wrapper,test_app)
    test_subject.pack()
    test_app.title("Testbed for widget: " + test_subject.__class__.__name__)
    test_app.mainloop()

if __name__ == '__main__':
    def widgetfun(parent: ctk.CTkFrame,root: UIRoot) -> ctk.CTkBaseClass:
        # set up your widget here (with parent as its master widget) and replace the return statement below
        controller = ProfileEditPageController(parent,root)
        return ProfileEditPage(parent,controller)
    test_widget(widgetfun)
