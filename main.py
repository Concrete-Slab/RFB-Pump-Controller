from App import App
from support_classes.Teardown import with_teardown
import sys

@with_teardown
def run_application():
    if sys.gettrace():
        # run in debug mode
        app = App(debug=True)
    else:
        app = App()
    app.mainloop()

if __name__ == '__main__':
    run_application()
