from App import App
from support_classes import TDExecutor
import sys

if __name__ == '__main__':
    gettrace = getattr(sys, 'gettrace', None)
    if sys.gettrace():
        # run in debug mode
        app = App(debug=True)
    else:
        app = App()
    app.mainloop()
    TDExecutor.execute()
