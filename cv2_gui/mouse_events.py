from typing import Generic, TypeVar, Any, Generator, Callable, Iterable
from abc import ABC, abstractmethod
import copy
import numpy as np
import cv2
import multiprocessing as mp

ESC = 27
ENTER = 13
Rect = tuple[int,int,int,int]
T = TypeVar("T")
_T = TypeVar("_T")
MouseEvent = tuple[int,int,int,int,Any]


class MouseInput(Generic[T],ABC):
    """
    Base class for defining mouse interactions with a cv2 window
    Implement your own logic by subclassing and defining the following 3 functions:
    - variable (property): defines what you want to return from the user's input
    - on_input (method): determines how to handle any event from the mouse, such as mouse movement or buttons
    - reset (method): used to reset the state variables of the MouseInput instance

    """
    text = "Default Text"
    WAITKEY_TIME = 50
    def __init__(self, window: str|None = None, img: np.ndarray|None = None, auto_progress = False, lock = mp.Lock(), event = mp.Event()) -> None:
        if window is None:
            window = self.__class__.__name__
        self.__window = window
        img = np.zeros((256,256,3),dtype=np.uint8) if img is None else img
        self.__img = img
        self.__original_img = copy.copy(img)
        self.__back_flag = False
        self.__is_active = False
        self.__auto_progress = auto_progress
        self.__last_event: MouseEvent|None = None
        self.__is_recording = False

        # multiprocessing additional variables
        self._lock = lock
        self.break_event = event

    def __call__(self,window: str,img:np.ndarray,ignore_backwards=True) -> T:
        return self.__mainloop(window,img,ignore_backwards=ignore_backwards)
    
    def terminate(self):
        self.break_event.set()


    @property
    def window(self) -> str:
        return self.__window
    @window.setter
    def window(self,newval: str) -> None:
        # if window doesnt exist, make it
        try:
            if cv2.getWindowProperty(newval, 0) < 0:
                cv2.namedWindow(newval)
        except cv2.error:
            cv2.namedWindow(newval)
        self.__window = newval
    @property
    def cancel_flag(self) -> bool:
        return self.__back_flag
    @cancel_flag.setter
    def cancel_flag(self,newval: bool) -> None:
        self.__back_flag = newval
    @property
    def is_active(self) -> bool:
        return self.__is_active
    @property
    def last_event(self) -> MouseEvent|None:
        return self.__last_event
    @last_event.setter
    def last_event(self,newval: MouseEvent|None):
        self.__is_recording = False
        self.__last_event = newval
    @property
    def auto_progress(self) -> bool:
        return self.__auto_progress
    @auto_progress.setter
    def auto_progress(self,newval: bool) -> None:
        if self.__is_active:
            raise MouseInputException("Cannot change progression mode while loop is active")
        self.__auto_progress = newval
    @property
    def original_image(self) -> np.ndarray:
        return self.__original_img
    @original_image.setter
    def original_image(self,newimg: np.ndarray) -> None:
        self.reset()
        self.__original_img = copy.copy(newimg)
        self.img = newimg
    @property
    def img(self) -> np.ndarray:
        return self.__img
    @img.setter
    def img(self,newimg: np.ndarray) -> None:
        self.__img = newimg
        if self.is_active:
            self.show_with_text()
    @property
    def has_value(self) -> bool:
        try:
            return self.variable is not None
        except MouseInputException:
            return False

    @abstractmethod
    def on_input(self,event,x,y,flags,userdata) -> None:
        pass
    @abstractmethod
    def reset(self) -> None:
        pass
    
    @property
    @abstractmethod
    def variable(self) -> T:
        """
        Quantity that the user is prompted to produce

        returns:
            Value that is related to the user's input. Must be defined clearly by subclasses
        raises:
            MouseInputException if the user has not input enough data yet to determine its value
        """
        raise MouseInputException

    def _wrapped_callback(self,*args):
        if self.__is_recording:
            self.__last_event = args
        self.on_input(*args)

    def __mainloop(self, window: str, img: np.ndarray, init_event: MouseEvent|None = None, ignore_backwards=False) -> T:
        self.window = window
        self.original_image = img
        self.__is_active = True
        if init_event is None:
            self.show_with_text()
        else:
            self.on_input(*init_event)
        # register mouse callback
        cv2.setMouseCallback(self.__window,self._wrapped_callback)
        self.__is_recording = True
        self.break_event.clear()
        loopfun = self._auto_loop if self.auto_progress else self._manual_loop
        try:
            value = loopfun(ignore_backwards=ignore_backwards)
        finally:
            # remove mouse callback
            cv2.setMouseCallback(self.__window,lambda *args: None)
            self.__is_active = False
            self.cancel_flag = False
        return value
    
    def _manual_loop(self, ignore_backwards=False) -> T:
        loopvar = True
        returned_value = None
        while loopvar:
            inp = cv2.waitKey(self.WAITKEY_TIME)
            if self.break_event.is_set() or inp == ESC:
                raise EscException
            if self.__back_flag and not ignore_backwards:
                raise BackwardsException()
            elif inp == ENTER and self.has_value:
                returned_value = self.variable
                loopvar = False
        return returned_value
    
    def _auto_loop(self,ignore_backwards=False) -> T:
        loopvar = True
        returned_value = None
        while loopvar:
            inp = cv2.waitKey(self.WAITKEY_TIME)
            if self.break_event.is_set() or inp == ESC:
                raise EscException()
            elif self.__back_flag and not ignore_backwards:
                raise BackwardsException()
            elif self.has_value:
                loopvar = False
                returned_value = self.variable
        return returned_value

    def show_with_text(self):
        if self.auto_progress:
            text = self.text + " Press <Esc> to quit"
        else:
            text = self.text + " Press <Enter> to confirm or <Esc> to quit"
        display_img = copy.copy(self.img)
        display_img = cv2.putText(display_img, text, (10,20), cv2.FONT_HERSHEY_SIMPLEX, 
                    0.5, (0, 0, 255), 1, cv2.LINE_AA)
        cv2.imshow(self.__window,display_img)
    
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

    @staticmethod
    def chain_inputs(window: str, img: np.ndarray, inputlist: list["MouseInput"],ignore_backwards=False) -> list[Any]:
        i=0
        n_steps = len(inputlist)
        prev_event = None
        while i<n_steps:
            next_obj = inputlist[i]
            if i>0:
                next_image = inputlist[i-1].img
                ib = False
            else:
                next_image = copy.copy(img)
                ib = ignore_backwards
            try:
                _ = next_obj.__mainloop(window,next_image,init_event=prev_event,ignore_backwards=ib)
                prev_event = next_obj.last_event
                i = i + 1
            except BackwardsException as be:
                if i==0 and ignore_backwards == False:
                    raise be
                i = i-1 if i>0 else 0
                if i==0:
                    inputlist[i].reset()
                prev_event = None

        return [mi.variable for mi in inputlist]

class MouseInputException(Exception):
    pass

class ChannelFlipper(MouseInput[np.ndarray]):
    text = "Flip image channels (BGR<->RGB) with mousewheel"
    def __init__(self, window: str|None = None, img: np.ndarray|None = None, auto_progress=False, lock = mp.Lock(), event = mp.Event()) -> None:
        super().__init__(window, img, auto_progress,lock,event)
        self._auto_progress_flag = False
    
    @property
    def variable(self) -> np.ndarray:
        return self.img
    
    @property
    def has_value(self) -> bool:
        val = super().has_value and ((not self.auto_progress) or self._auto_progress_flag)
        self._auto_progress_flag = False
        return val
    
    def on_input(self, event, x, y, flags, userdata) -> None:
        if event == cv2.EVENT_MOUSEWHEEL and self.img.shape[2] in (3,4):
            img = self.img
            temp = copy.copy(img[:,:,2])
            img[:,:,2] = img[:,:,0]
            img[:,:,0] = temp
            self.img = img
        elif event == cv2.EVENT_LBUTTONDOWN:
            self._auto_progress_flag = True
            self.last_event = None
        elif event == cv2.EVENT_RBUTTONDOWN:
            self.cancel_flag = True
            self.last_event = event
        
    def reset(self) -> None:
        self._auto_progress_flag = False
    
class Rotator(MouseInput[np.ndarray]):
    text = "Rotate image with mousewheel. Click to confirm"
    def __init__(self,window: str|None = None, img: np.ndarray|None = None, increment = 10*np.pi/180, auto_progress=False, lock = mp.Lock(), event = mp.Event()):
        super().__init__(window,img,auto_progress=auto_progress,lock=lock,event=event)
        self.__increment = increment
        self.angle = 0
        self._auto_progress_flag = False

    @property
    def has_value(self) -> bool:
        val =  super().has_value and (self._auto_progress_flag or not self.auto_progress)
        self._auto_progress_flag = False
        return val
    
    def on_input(self,event,x,y,flags,userdata):
        if event == cv2.EVENT_MOUSEWHEEL:
            flagsign = flags/abs(flags) if flags !=0 else 0
            self.angle += flagsign*self.__increment
            self.img = rotate_image(copy.copy(self.original_image),self.angle)
        elif event in (cv2.EVENT_LBUTTONDOWN,cv2.EVENT_LBUTTONDBLCLK,cv2.EVENT_MBUTTONDBLCLK,cv2.EVENT_MBUTTONDOWN,cv2.EVENT_RBUTTONDBLCLK,cv2.EVENT_RBUTTONDOWN):
            self._auto_progress_flag = self.auto_progress
            if self.auto_progress:
                self.last_event = None

    def reset(self):
        self.angle = 0
        self._auto_progress_flag = False

    @property
    def variable(self) -> np.ndarray:
        return self.img

class BoxDrawer(MouseInput[tuple[int,int,int,int]]):
    
    def __init__(self, height: int, width: int, window: str|None = None, img: np.ndarray|None = None, boxname: str = "outer box", color: tuple[int,int,int]=(0,0,255),auto_progress=False, lock = mp.Lock(), event = mp.Event()) -> None:
        super().__init__(window,img,auto_progress=auto_progress,lock=lock,event=event)
        self.text = "Click to draw "+boxname+". Right-click to cancel."
        self.boxheight = height
        self.boxwidth = width
        self.topleft: tuple[int,int] = None
        self.color = (color[2],color[1],color[0])
    def reset(self):
        self.topleft = None
    def on_input(self, event, x, y, flags, userdata) -> None:
        if event == cv2.EVENT_LBUTTONDOWN:
            self.topleft = (x,y)
            rect = (x,y,self.boxwidth,self.boxheight)
            self.img = cv2.rectangle(copy.copy(self.original_image),rect,self.color,1)
            self.last_event = None
        elif event == cv2.EVENT_RBUTTONDOWN:
            if self.topleft is None:
                self.cancel_flag = True
            self.topleft = None
            self.img = self.original_image
        elif event == cv2.EVENT_MOUSEMOVE and self.topleft == None:
            rect = (x,y,self.boxwidth,self.boxheight)
            self.img = cv2.rectangle(copy.copy(self.original_image),rect,self.color,1)
    @property
    def variable(self):
        if self.topleft is None:
            raise MouseInputException("No rectangle available")
        return (*self.topleft,self.boxwidth,self.boxheight)
    
class ROISelector(MouseInput[tuple[int,int,int,int]]):
    def __init__(self, window: str|None = None, img: np.ndarray|None = None, boxname: str = "inner box", color: tuple[int,int,int]=(0,255,0),auto_progress=False, lock = mp.Lock(), event = mp.Event()) -> None:
        super().__init__(window, img, auto_progress=auto_progress,lock=lock,event=event)
        self.text = "Click to start drawing "+boxname+". Click again to finish. Right-click to cancel."
        self.initial_point: tuple[int,int]|None = None
        self.final_point: tuple[int,int]|None = None
        self.color = (color[2],color[1],color[0])
    @property
    def is_drawing(self) -> bool:
        return (self.initial_point is not None) and (self.final_point is None)#
    def reset(self):
        self.initial_point = None
        self.final_point = None
    def on_input(self, event, x, y, flags, userdata) -> None:
        if event == cv2.EVENT_LBUTTONDOWN:
            if self.is_drawing:
                self.final_point = (x,y)
                self.img = cv2.rectangle(copy.copy(self.original_image),self.initial_point,self.final_point,self.color,1)
                self.last_event = None
            else:
                self.initial_point = (x,y)
        elif event == cv2.EVENT_RBUTTONDOWN:
            if self.initial_point is None:
                self.cancel_flag = True
            self.initial_point = None
            self.final_point = None
            self.img = self.original_image
        elif event == cv2.EVENT_MOUSEMOVE and self.is_drawing:
            intermediate_pt = (x,y)
            self.img = cv2.rectangle(copy.copy(self.original_image),self.initial_point,intermediate_pt,self.color,1)

    @property
    def variable(self) -> tuple[int,int,int,int]:
        if self.initial_point is None or self.final_point is None:
            raise MouseInputException("No rectangle available")
        width = abs(self.initial_point[0]-self.final_point[0])
        height = abs(self.initial_point[1]-self.final_point[1])
        x_min = min(self.initial_point[0],self.final_point[0])
        y_min = min(self.initial_point[1],self.final_point[1])
        return (x_min,y_min,width,height)

class ImageScroller(MouseInput[None]):
    text="Next image: left-click. Prev image: right-click"
    def __init__(self, window: str | None = None, img: np.ndarray | None = None, auto_progress=False, lock = mp.Lock(), event = mp.Event()) -> None:
        super().__init__(window, img, auto_progress,lock=lock,event=event)
        self._auto_progress_flag = False
    def variable(self):
        return None
    def reset(self):
        self._auto_progress_flag = False
    def on_input(self, event, x, y, flags, userdata) -> None:
        if event == cv2.EVENT_LBUTTONDOWN:
            self._auto_progress_flag = True
            self.last_event = None
        elif event == cv2.EVENT_RBUTTONDOWN:
            self.cancel_flag = True
            self.last_event = event
    @property
    def has_value(self):
        val = super().has_value and (not self.auto_progress or self._auto_progress_flag)
        self._auto_progress_flag = False
        return val
    
class HeightSelector(MouseInput[int]):
    def __init__(self, window: str | None = None, img: np.ndarray | None = None, auto_progress=False, lock=mp.Lock(), event=mp.Event(), line_color = (0,255,0)) -> None:
        super().__init__(window, img, auto_progress, lock, event)
        self.initial_height = None
        self.final_height = None
        self.color = line_color
        self.is_drawing = False
        self.__intermediate_img = None
    
    @property
    def variable(self) -> int:
        if self.initial_height is not None and self.final_height is not None:
            return abs(self.initial_height-self.final_height)
        raise MouseInputException()
    def reset(self):
        self.initial_height = None
        self.final_height = None
    def on_input(self, event, x, y, flags, userdata) -> None:
        if event == cv2.EVENT_MOUSEMOVE:
            if self.is_drawing and self.__intermediate_img is not None:
                imgwidth = self.img.shape[1]
                nextimg = cv2.line(copy.copy(self.__intermediate_img),(0,y),(imgwidth,y),self.color,thickness=1)
                self.img = cv2.line(nextimg,(x,y),(x,self.initial_height),self.color,thickness=1)
            elif self.__intermediate_img is None and not self.is_drawing:
                imgwidth = self.img.shape[1]
                self.img = cv2.line(copy.copy(self.original_image),(0,y),(imgwidth,y),self.color,thickness=1)
        elif event == cv2.EVENT_LBUTTONDOWN:
            if self.is_drawing:
                self.final_height = y
                self.is_drawing = False
            else:
                imgwidth = self.img.shape[1]
                self.initial_height = y
                self.is_drawing = True
                self.__intermediate_img = cv2.line(copy.copy(self.img),(0,y),(imgwidth,y),self.color,thickness=1)
                self.img = self.__intermediate_img
        elif event == cv2.EVENT_RBUTTONDOWN:
            if self.final_height:
                self.final_height = None
                self.is_drawing = True
                self.img = self.__intermediate_img
            elif self.initial_height:
                self.initial_height = None
                self.is_drawing = False
                self.__intermediate_img = None
                self.img = self.original_image
            else:
                self.cancel_flag = True
                self.last_event = None


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

def rotate_image(image: np.ndarray, angle: float):
  image_center = tuple(np.array(image.shape[1::-1]) / 2)
  rot_mat = cv2.getRotationMatrix2D(image_center, angle, 1.0)
  result = cv2.warpAffine(image, rot_mat, image.shape[1::-1], flags=cv2.INTER_LINEAR)
  return result

class BackwardsException(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)

class EscException(BaseException):
    pass
