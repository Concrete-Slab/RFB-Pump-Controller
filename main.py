from .App import App
from support_classes import TDExecutor
if __name__ == '__main__':
    app = App()
    app.mainloop()
    TDExecutor.execute()
