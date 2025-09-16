from App import App
from support_classes.Teardown import with_teardown
import sys
from multiprocessing import freeze_support

@with_teardown
def run_application():
    if sys.gettrace():
        # run in debug mode
        app = App(debug=True)
    else:
        app = App()
    app.mainloop()

if __name__ == '__main__':
    freeze_support()
    run_application()
