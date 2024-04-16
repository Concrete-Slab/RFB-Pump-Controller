import customtkinter as ctk
from typing import Callable
from ui_root import UIRoot
from ui_pages.toplevel_boxes import AlertBox

def test_widget(box_constructor: Callable[..., AlertBox]):
    test_app = UIRoot()
    wrapper = ctk.CTkFrame(test_app)
    wrapper.pack()
    def on_success(*args):
        print("Box returned the following values:")
        for arg in args:
            print(arg)
        test_app.after(100,test_app.destroy)
    def on_failure():
        print("Box closed without returning")
        test_app.after(100,test_app.destroy)

    test_subject = box_constructor(test_app,on_success=on_success,on_failure=on_failure)
    test_app.title("Testbed for widget: " + test_subject.__class__.__name__)
    test_app.mainloop()

if __name__ == '__main__':
    # replace AlertBox with an inherited alert box you wish to test
    test_widget(AlertBox)