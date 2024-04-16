## Code adapted from Mano's answer on stackexchange:
## https://stackoverflow.com/questions/42158694/how-to-run-tensorboard-from-python-scipt-in-virtualenv
from multiprocessing import Process
import sys
import os
from contextlib import contextmanager
from lightning.pytorch.loggers import TensorBoardLogger
from pathlib import Path
import shutil

class TensorboardSupervisor:
    def __init__(self, log_dp):
            self.server = TensorboardServer(log_dp)
            self.server.start()
            print("Started Tensorboard Server")
            self.chrome = BrowserProcess()
            print("Started Browser")
            self.chrome.start()

    def finalize(self):
        if self.server.is_alive():
            print('Killing Tensorboard Server')
            self.server.terminate()
            self.server.join()
            self.chrome.terminate()
            self.chrome.join()


class TensorboardServer(Process):
    def __init__(self, log_dp):
        super().__init__()
        self.os_name = os.name
        self.log_dp = str(log_dp)
        # self.daemon = True

    def run(self):
        if self.os_name == 'nt':  # Windows
            os.system(f'{sys.executable} -m tensorboard.main --logdir "{self.log_dp}" 2> NUL')
        elif self.os_name == 'posix':  # Linux
            os.system(f'{sys.executable} -m tensorboard.main --logdir "{self.log_dp}" '
                      f'--host `hostname -I` >/dev/null 2>&1')
        else:
            raise NotImplementedError(f'No support for OS : {self.os_name}')
    
    
class BrowserProcess(Process):
    def __init__(self):
        super().__init__()
        self.os_name = os.name
        self.daemon = True

    def run(self):
        if self.os_name == 'nt':  # Windows
            os.system(f'start http://localhost:6006/')
        elif self.os_name == 'posix':  # Linux
            os.system(f'google-chrome http://localhost:6006/')
        else:
            raise NotImplementedError(f'No support for OS : {self.os_name}')
        
@contextmanager
def tblogger(log_path: Path, name: str|None="lightning_logs",copy_path:list[Path]|Path|None=None):
    try:
        logger = TensorBoardLogger(log_path,name=name)
        print(logger.root_dir)
        print(logger.save_dir)
        print(logger.log_dir)
        supervisor = TensorboardSupervisor(log_path)
        yield logger
    finally:
        supervisor.finalize()
        try:
            _copy_to_log_dir(copy_path,logger)
        except:
            pass

def _copy_to_log_dir(copy_path:list[Path]|Path|None,logger: TensorBoardLogger):

    def save_one(pth: Path):
        fname = pth.parts[-1]
        shutil.copy2(pth,Path(logger.log_dir)/fname)

    if isinstance(copy_path,list) and len(copy_path)>0 and isinstance(copy_path[0],Path):
        for path in copy_path:
            save_one(path)
    elif isinstance(copy_path,Path):
        save_one(copy_path)