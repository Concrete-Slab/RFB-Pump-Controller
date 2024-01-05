from App import App
from support_classes.Teardown import TDExecutor
import sys

def main():
    if sys.gettrace():
        # run in debug mode
        app = App(debug=True)
    else:
        app = App()
    app.mainloop()
    TDExecutor.execute()

if __name__ == '__main__':
    main()
