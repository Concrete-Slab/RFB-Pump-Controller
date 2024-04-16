import copy
import json
from typing import Any, Callable, Generic, Iterable, TypeVar
import numpy as np
from PIL import Image
import csv
import cv2
from contextlib import contextmanager
import os
from pathlib import Path
from cv2_gui.mouse_events import MouseInput, ROISelector, BoxDrawer, Rotator, ChannelFlipper, EscException, BackwardsException
from cv2_gui.cv2_multiprocessing import open_cv2_window
from typing import Generator

_T = TypeVar("_T")
_RT = TypeVar("_RT")

def withwindow(fun):
    def inner(inst: "ImageLabeller",*args,**kwargs):
        with open_cv2_window(inst.wind):
            return fun(inst,*args,**kwargs)
    return inner

@contextmanager
def messenger():
    yield

IMG_DIR = Path(__file__).absolute().parent /"Images"
CSV_PATH = IMG_DIR.parent / "labelled_images.csv"
ESC = 27
ENTER = 13

Rect = tuple[int,int,int,int]

class ImageLabeller:
    def __init__(self,name="Image Labeller",img_dir = IMG_DIR, csv_path = CSV_PATH, extension = ".png") -> None:
        self.wind = name
        self.csvpath = csv_path
        self.imgdir = img_dir
        self.extension = extension
        if csv_path not in os.listdir(csv_path.parent):
            open(csv_path, 'a').close()
    @property
    def display_img(self) -> np.ndarray:
        return self._display_img
    @display_img.setter
    def display_img(self,new_val) -> None:
        self._display_img = new_val
        cv2.imshow(self.wind,new_val)

    def __get_files(self, return_all = False) -> list[str]:
        allfiles = [f for f in os.listdir(self.imgdir) if os.path.isfile(os.path.join(self.imgdir, f))]
        if return_all:
            return allfiles
        with open(self.csvpath,"r",newline="") as f:
            prevlabels = [row[0] for row in csv.reader(f) if len(row)>0]
        remainingfiles = copy.copy(allfiles)
        for filename in allfiles:
            if filename in prevlabels:
                remainingfiles.remove(filename)
        return remainingfiles
    
    def create_labels(self, from_scratch = False, imshape: tuple[int,int]|None = None, rotate_images=False):
        
        if from_scratch:
            # clear existing labels
            with open(self.csvpath,"w") as f:
                f.truncate()

        files = self.__get_files()
        
        with open_cv2_window(self.wind), open(self.csvpath, "a+", newline="") as f:
            writer = csv.writer(f)
            if imshape is None:
                inputs = [
                    ROISelector(auto_progress=True,color=(0,0,255)),
                    ROISelector(auto_progress=True),
                    ROISelector(auto_progress=True,color=(0,0,255)),
                    ROISelector(auto_progress=False),
                ]
            else:
                inputs = [
                    BoxDrawer(imshape[0],imshape[1],auto_progress=True),
                    ROISelector(auto_progress=True),
                    BoxDrawer(imshape[0],imshape[1],auto_progress=True),
                    ROISelector(auto_progress=False),
                ]
            if rotate_images:
                inputs.insert(0,Rotator(auto_progress=True))
            try:
                for i in range(0,len(files)):
                    imgpath = self.imgdir/files[i]
                    curr_img = np.array(Image.open(imgpath))
                    try:
                        outputs = MouseInput.chain_inputs(self.wind,curr_img,inputs)
                        if rotate_images:
                            rotated_img = outputs.pop(0)
                            Image.fromarray(rotated_img).save(imgpath)
                    except BackwardsException:
                        i = i-1
                    
            except EscException:
                pass
            print("Finishing up...")

    @withwindow
    def redo_outer_boxes(self, imshape: tuple[int,int]|None=None):

        with open(self.csvpath, "r", newline="") as f:
            csv_info = [row for row in csv.reader(f)]
        if os.path.isfile(self.csvpath.parent / "labelling.json"):
            labelling_data = json.load(self.csvpath.parent / "labelling.json")
            i = labelling_data["index"] + 1
        else:
            i = 0

        if imshape is None:
            inputs = [
                ROISelector(auto_progress=True,color=(0,0,255)),
                ROISelector(auto_progress=False,color=(0,0,255)),
            ]
        else:
            inputs = [
                BoxDrawer(imshape[0],imshape[1],auto_progress=True),
                BoxDrawer(imshape[0],imshape[1],auto_progress=False),
            ]
        
        def loopfun(_: int, j: int):
            row = csv_info[j]
            filename = row[0]
            # outer_box_1 = tuple(map(int,row[1:5]))
            inner_box_1 = tuple(map(int,row[5:9]))
            # outer_box_2 = tuple(map(int,row[9:13]))
            inner_box_2 = tuple(map(int,row[13:]))

            curr_img = np.array(Image.open(self.imgdir/filename))
            curr_img = cv2.rectangle(curr_img,inner_box_1,(0,255,0),1)
            curr_img = cv2.rectangle(curr_img,inner_box_2,(0,255,0),1)

            outputs = MouseInput.chain_inputs(self.wind,curr_img,inputs)
            outer_box_1 = bbox_to_str(outputs[0])
            outer_box_2 = bbox_to_str(outputs[1])
            csv_info[j][1:5] = outer_box_1
            csv_info[j][9:13] = outer_box_2
        
        self.iterate(loopfun,range(i,len(csv_info)))

        with open(self.csvpath, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerows(csv_info)

    @withwindow
    def flip_channels(self):
        suffix_index = -1*len(self.extension)
        files = [file for file in os.listdir(self.imgdir) if file[suffix_index:] == self.extension]
        mi = ChannelFlipper(auto_progress=True)
        
        def loopfun(i: int, file: str):
            imgpath = self.imgdir/file
            curr_img = np.array(Image.open(imgpath),dtype=np.uint8)
            
            flipped = mi(self.wind,curr_img,ignore_backwards=False)
            Image.fromarray(flipped).save(imgpath)

        self.iterate(loopfun,files)
    
    @staticmethod
    def iterate(fun: Callable[[_T],None],iterable: Iterable[_T]) -> None:
        gen = _bidirectional_generator(iterable)
        for i,item in gen:
            try:
                fun(i,item)
            except BackwardsException:
                gen.send(False)
            except EscException:
                break

def _bidirectional_generator(iterable: Iterable[_T]) -> Generator[tuple[int,_T],bool|None,None]:
    i=0
    while i < len(iterable):
        response = yield i, iterable[i]
        response = True if response is None else response
        if response:
            i+=1
        else:
            i= max(i-1,0)
            _ = yield i, iterable[i]
    return

def bbox_to_str(bbox: tuple[int,int,int,int]) -> tuple[str,str,str,str]:
    return tuple(map(str,bbox))

if __name__ == "__main__":
    x = ImageLabeller()
    x.flip_channels()
