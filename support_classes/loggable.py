from pathlib import Path
import os
import csv
import datetime

class Loggable:

    def __init__(self,directory: Path = Path(__file__).absolute().parent,default_headers: list[str] = []):
        self.__directory: Path = directory
        self.__headers: list[str] = default_headers
        self.__filename: str|None = None
        
    def log(self,newline: list):
        if self.__filename is None:
            self.__filename = datetime.datetime.now().strftime("%m-%d-%Y %H-%M-%S")
        total_path = f"{self.__directory.as_posix()}/{self.__filename}.csv"
        if os.path.isfile(total_path):
            with open(total_path,mode="a") as f:
                writer = csv.writer(f,delimiter=",")
                writer.writerow(newline)
        else:
            if not os.path.isdir(self.__directory):
                os.makedirs(self.__directory)
            with open(total_path,mode="a+") as f:
                writer = csv.writer(f,delimiter = ",")
                writer.writerow(self.__headers)
                writer.writerow(newline)

    def set_dir(self,newdir: Path):
        self.__directory = newdir
        self.__filename = None

    def new_file(self):
        self.__filename = None

    def get_dir(self) -> Path:
        return self.__directory


