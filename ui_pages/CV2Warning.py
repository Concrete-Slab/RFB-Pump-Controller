from typing import Optional, Tuple, Union
import customtkinter as ctk
from .UIController import UIController
from .PAGE_EVENTS import CEvents, ProcessName
import cv2
from support_classes import open_video_device,open_cv2_window


class CV2Warning(ctk.CTkToplevel):

    ALERT_TITLE = "Level sensing prompt"

    #TODO this code is perhaps rather rushed...

    def __init__(self, master: ctk.CTk, controller: UIController, default_video_device: int = 0,*args, fg_color: str | Tuple[str, str] | None = None, **kwargs):
        super().__init__(master,*args, fg_color=fg_color, **kwargs)
        self.title(self.ALERT_TITLE)
        self.UIcontroller = controller
        self.default_device = default_video_device

        self.__r1: tuple[int,int,int,int]|None = None
        self.__r2: tuple[int,int,int,int]|None = None
        self.__h: tuple[int,int,int,int]|None = None

        self.initial_frame = ctk.CTkFrame(self)

        self.volume_frame = ctk.CTkFrame(self)
        
        # set up initial page

        self.lblvar = ctk.StringVar(value="Select video device (positive int): ")
        lbl = ctk.CTkLabel(self.initial_frame, textvariable = self.lblvar)
        self.current_device = ctk.StringVar(value=str(default_video_device))
        device_selector = ctk.CTkEntry(self.initial_frame, textvariable=self.current_device, validate='key', validatecommand = (self.register(_validate_device),"%P"))
        device_selector.bind('<Return>', command=lambda event: self.__confirm_device())
        device_selector.bind('<FocusOut>', command=lambda event: self.focus_set(), add="+")

        self.confirm_button = ctk.CTkButton(self.initial_frame,text="Confirm",command=self.__confirm_device)
        
        self.UIcontroller.add_listener("valid_regions",self.__destroy_successfully)
        self.UIcontroller.add_listener("invalid_regions",self.__bad_device)
        lbl.grid(row=0,column=0,columnspan=2,padx=10,pady=10,sticky="ns")
        device_selector.grid(row=1,column=0,padx=10,pady=10,sticky="nsew")
        self.confirm_button.grid(row=1,column=1,padx=10,pady=10,sticky="nsew")

        # volume select page

        self.initvar = ctk.StringVar(value="0")
        self.refvar = ctk.StringVar(value="0")
        initlabel = ctk.CTkLabel(self.volume_frame,text="Enter combined initial volume:")
        reflabel = ctk.CTkLabel(self.volume_frame,text="Enter reference volume:")
        initentry = ctk.CTkEntry(self.volume_frame,textvariable=self.initvar,validate="key",validatecommand=(self.register(_validate_volume),"%P"))
        initentry.bind('<Return>', command=lambda event: self.__confirm_volumes())
        initentry.bind('<Tab>', command=lambda event: refentry.focus_set())
        initentry.bind('<FocusOut>', command=lambda event: self.focus_set(), add="+")
        refentry = ctk.CTkEntry(self.volume_frame,textvariable=self.refvar,validate="key",validatecommand=(self.register(_validate_volume),"%P"))
        refentry.bind('<Return>', command=lambda event: self.__confirm_volumes())
        refentry.bind('<Tab>', command=lambda event: initentry.focus_set())
        refentry.bind('<FocusOut>', command=lambda event: self.focus_set(), add="+")
        ml1 = ctk.CTkLabel(self.volume_frame,text="mL")
        ml2 = ctk.CTkLabel(self.volume_frame,text="mL")
        button_frame = ctk.CTkFrame(self.volume_frame)
        volbutton = ctk.CTkButton(button_frame,text="Confirm",command=self.__confirm_volumes)
        redobutton = ctk.CTkButton(button_frame,text="Retake",command=self.__select_device)
        button_frame.columnconfigure([0,1],weight=1,uniform="col")
        volbutton.grid(row=0,column=1,padx=10,pady=10,sticky="ns")
        redobutton.grid(row=0,column=0,padx=10,pady=10,sticky="ns")

        initlabel.grid(row=0,column=0,padx=10,pady=10,sticky="w")
        initentry.grid(row=0,column=1,padx=10,pady=10,sticky="ns")
        ml1.grid(row=0,column=2,padx=10,pady=10,sticky="w")
        reflabel.grid(row=1,column=0,padx=10,pady=10,sticky="w")
        refentry.grid(row=1,column=1,padx=10,pady=10,sticky="ns")
        ml2.grid(row=1,column=2,padx=10,pady=10,sticky="w")
        button_frame.grid(row=3,column=0,columnspan=3,sticky="nsew")

        # Change to initial_frame
        self.__select_device()
        # bring alert box to fromt
        self.attributes('-topmost', 1)
        self.attributes('-topmost', 0)
        


    def __confirm_device(self):
        if self.confirm_button._state == ctk.NORMAL:
            device_num = self.current_device.get()
            if device_num == "":
                self.lblvar.set("Please enter a valid device number")
            else:
                self.confirm_button.configure(state=ctk.DISABLED)
                # self.UIcontroller.notify_event("launch_cv2",int(self.current_device.get()))
                self.__launch_cv2(int(device_num))

    def __bad_device(self):
            self.lblvar.set("Choose a different device")
            self.confirm_button.configure(state=ctk.NORMAL)

    def __select_device(self):
        self.__r1, self.__r2, self.__h = None,None,None
        self.volume_frame.pack_forget()
        self.confirm_button.configure(state=ctk.NORMAL)
        self.initial_frame.pack()

    def __select_volumes(self):
        self.initial_frame.pack_forget()
        self.volume_frame.pack()

    def __bad_regions(self):
        self.lblvar.set("Please select 3 regions")
        self.confirm_button.configure(state=ctk.NORMAL)

    def __confirm_volumes(self):
        init_vol_str = self.initvar.get()
        ref_vol_str = self.refvar.get()
        if init_vol_str != "" and ref_vol_str != "":
            self.UIcontroller.notify_event(CEvents.LEVEL_DATA_ACQUIRED,self.default_device,self.__r1,self.__r2,self.__h,float(ref_vol_str),float(init_vol_str))
            self.__destroy_successfully()

    def __launch_cv2(self,device: int):
        # with open_video_device(device) as cap:
        #     isretrieved, img = cap.read()
        cap = cv2.VideoCapture(device)
        isretrieved,img = cap.read()
        cap.release()
        if isretrieved:
            self.default_device = device
            img = cv2.rotate(img,cv2.ROTATE_90_CLOCKWISE)
            with open_cv2_window("rectfeed") as wind:
                try:
                    self.__r1, self.__r2, self.__h = cv2.selectROIs(wind,img)
                except ValueError:
                    self.__r1, self.__r2, self.__h = None, None, None
            if any((self.__r1 is None, self.__r2 is None, self.__h is None)):
                # TODO change these back to parameterless
                self.__bad_regions()
            else:
                self.__select_volumes()
        else:
            self.__bad_device()
            
    def __destroy_successfully(self):
        super().destroy()

    def destroy(self):
        self.UIcontroller.notify_event(CEvents.PROCESS_CLOSED,ProcessName.LEVEL)
        cv2.destroyAllWindows()
        super().destroy()

def _validate_device(p: str):
    try:
        nump = int(p)
        if nump >= 0:
            return True
        return False
    except ValueError:
        if p == "":
            return True
        return False
    
def _validate_volume(p: str):
    try:
        nump = float(p)
        if nump >= 0:
            return True
        return False
    except ValueError:
        if p == "":
            return True
        return False