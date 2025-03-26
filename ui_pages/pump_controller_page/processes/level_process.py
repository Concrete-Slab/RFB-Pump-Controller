from dataclasses import dataclass
import threading
import time
from pump_control.async_levelsensor import LevelOutput, LevelReading
from support_classes.settings_interface import read_setting
from ui_pages.pump_controller_page.processes.base_process import BaseProcess
from ui_pages.pump_controller_page.CONTROLLER_EVENTS import CEvents, ProcessName
from support_classes import Settings, read_settings, modify_settings, CAMERA_SETTINGS, SharedState, CV2Capture, PygameCapture, CaptureBackend, DEFAULT_SETTINGS, LEVEL_SETTINGS, Capture, ImageFilterType
from pump_control import Pump
from typing import Any, Callable
from typing_extensions import override
from ui_root import AlertBoxBase, AlertBox, UIController, UIRoot, event_group
import customtkinter as ctk
from ui_pages.ui_layout import WidgetGroup, make_and_group, make_and_grid, make_entry, make_menu, make_segmented_button, make_fileselect, validator_function, ApplicationTheme
from cv2_gui.cv2_multiprocessing import InputProcess
import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import cv2
from PIL import Image
import os
from pathlib import Path

class LevelProcess(BaseProcess):

    def __init__(self, controller_context: UIController, pump_context: Pump):
        super().__init__(controller_context, pump_context)
        self.level_data: _LevelData|None = None
        self.display_box: AlertBoxBase | None = None
        self.display_state: SharedState|None = None

    @property
    def name(self) -> str:
        return "Level Sensor"
    
    def start(self):
        if self.level_data is None:
            ## need to first get the regions for the detector, and then start sensing
            self.request_ROIs(after_success=self.__send_level_config,after_failure= lambda: self._controller_context.notify_event(CEvents.ProcessClosed(ProcessName.LEVEL)))
        else:
            ## already have the regions, so start sensing
            self.__send_level_config()

    def request_ROIs(self,after_success: Callable[[None],None]|None = None,after_failure: Callable[[None],None] = None):
        ## promps the user to assign the detector regions and reference volume. Public method, so that it may be called either on its own or before starting level sensing
        def on_failure():
            self._controller_context.notify_event(CEvents.CloseROISelection())
            if after_failure:
                after_failure()
        def on_success(r1: Rect, r2: Rect, h: Rect, ref_vol: float):
            self.level_data = _LevelData(r1,r2,h,ref_vol)
            self._controller_context.notify_event(CEvents.CloseROISelection())
            if after_success:
                after_success()
        box = self._controller_context._create_alert(LevelSelect(on_success=on_success,on_failure=on_failure))

    def __send_level_config(self):
        if self.level_data:
            (state_running,state_levels) = self._pump_context.start_levels(*self.level_data.as_tuple())
            self.display_state = state_levels.duplicate()
            self._monitor_running(state_running)
    
    @override
    def _handle_running(self,isrunning: bool):
        if isrunning and self.display_state:
            self._controller_context.notify_event(CEvents.ProcessStarted(ProcessName.LEVEL))

            on_close = self._pump_context.stop_levels
            
            self.display_box = self._controller_context._create_alert(LevelDisplay(self.display_state,on_failure=on_close,on_success=on_close))
        else:
            self._controller_context.notify_event(CEvents.ProcessClosed(ProcessName.LEVEL))
            if self.display_box:
                self.display_box.destroy()
                self.display_box = None

    def close(self):
        self._pump_context.stop_levels()
    
    @classmethod
    def process_name(cls):
        return ProcessName.LEVEL
    @property
    def settings_constructor(self):
        return LevelSettingsBox.default


Rect = tuple[int,int,int,int]

class _LevelData:
    def __init__(self,r1: Rect, r2: Rect, h: float, ref_vol: float):
        self.r1 = r1
        self.r2 = r2
        self.h = h
        self.ref_vol = ref_vol
    def as_tuple(self) -> tuple[Rect,Rect,float,float]:
        return (self.r1,self.r2,self.h,self.ref_vol)

class _LevelSelectFrame(AlertBoxBase[Rect,Rect,Rect,float]):

    ALERT_TITLE = "Level sensing prompt"

    #TODO this code is perhaps rather rushed...

    def __init__(self, master: ctk.CTk,*args, on_success: Callable[[int,Rect,Rect,Rect,float],None] | None = None, on_failure: Callable[[None],None] | None, fg_color: str | tuple[str, str] | None = None, **kwargs):
        super().__init__(master,*args, on_success=on_success, on_failure=on_failure, fg_color=fg_color, **kwargs)
        self.title(self.ALERT_TITLE)
        self.__video_params = read_settings(*CAMERA_SETTINGS)

        self.__filter_type = read_setting(Settings.IMAGE_FILTER)
        
        # multiprocessing variables
        self.__unregister_exit_condition: Callable[[None],None]|None = None
        self.__cv2_process = InputProcess(self.__filter_type,self.__video_params,window_name="Set up level visualisation")

        self.__r1: tuple[int,int,int,int]|None = None
        self.__r2: tuple[int,int,int,int]|None = None
        self.__h: tuple[int,int,int,int]|None = None

        self.initial_frame = ctk.CTkFrame(self)

        self.volume_frame = ctk.CTkFrame(self)
        
        # set up initial page
        instructions_label = ctk.CTkLabel(self.initial_frame,
                                          text = """Follow the prompts in the text on the image!\nPress ESC to cancel at any time\n""")
        self.lblvar = ctk.StringVar(value="Select the anolyte tank, catholyte tank, and finally a reference height")
        self.msg_lbl = ctk.CTkLabel(self.initial_frame, textvariable = self.lblvar)

        self.confirm_button = ctk.CTkButton(self.initial_frame,text="Confirm",command=self.__confirm_initial)
        
        instructions_label.grid(row=0,column=0,columnspan=2,padx=10,pady=5,sticky="nsew")
        self.msg_lbl.grid(row=1,column=0,columnspan=2,padx=10,pady=10,sticky="ns")
        self.confirm_button.grid(row=2,column=1,padx=10,pady=10,sticky="nsw")

        # volume select page
        self.refvar = ctk.StringVar(value="0")
        reflabel = ctk.CTkLabel(self.volume_frame,text="Enter reference volume:")
        self.__refentry = ctk.CTkEntry(self.volume_frame,textvariable=self.refvar,validate="key",validatecommand=(self.register(_validate_volume),"%P"))
        self.__refentry.bind('<Return>', command=lambda event: self.__confirm_volumes())
        self.__refentry.bind('<FocusOut>', command=lambda event: self.focus_set(), add="+")
        ml2 = ctk.CTkLabel(self.volume_frame,text="mL")
        button_frame = ctk.CTkFrame(self.volume_frame)
        volbutton = ctk.CTkButton(button_frame,text="Confirm",command=self.__confirm_volumes)
        redobutton = ctk.CTkButton(button_frame,text="Retake",command=self.__initial_screen)
        button_frame.columnconfigure([0,1],weight=1,uniform="col")
        volbutton.grid(row=0,column=1,padx=10,pady=10,sticky="ns")
        redobutton.grid(row=0,column=0,padx=10,pady=10,sticky="ns")

        reflabel.grid(row=1,column=0,padx=10,pady=10,sticky="w")
        self.__refentry.grid(row=1,column=1,padx=10,pady=10,sticky="ns")
        ml2.grid(row=1,column=2,padx=10,pady=10,sticky="w")
        button_frame.grid(row=3,column=0,columnspan=3,sticky="nsew")

        # Change to initial_frame
        self.__initial_screen()

    def __confirm_initial(self):
        if self.confirm_button._state == ctk.NORMAL:
            self.confirm_button.configure(state=ctk.DISABLED)
            self.__cv2_process.start()
            self.__unregister_exit_condition = self._add_event(self.__cv2_process.exit_flag,self.__check_regions)

    def __bad_regions(self,error: BaseException | None):
            match InputProcess.ErrorCode(error):
                case InputProcess.ErrorCode.INCORRECT_SELECTION:
                    errormsg = "Please select exactly 3 regions"
                case InputProcess.ErrorCode.CAPTURE_ERROR:
                    errormsg = "Camera failed to take picture"
                case InputProcess.ErrorCode.OVER_EDGE_SELECTION:
                    errormsg = "Selections cross over edge of image"
                case _:
                    errormsg = "Unknown Error"
            self.lblvar.set(errormsg)
            self.msg_lbl.configure(text_color=ApplicationTheme.ERROR_COLOR)
            self.confirm_button.configure(state=ctk.NORMAL)

    def __initial_screen(self):
        self.__r1, self.__r2, self.__h = None,None,None
        self.volume_frame.pack_forget()
        self.confirm_button.configure(state=ctk.NORMAL)
        self.msg_lbl.configure(text_color=ApplicationTheme.WHITE)
        self.initial_frame.pack()

    def __check_regions(self):
        with self.__cv2_process.output_data.get_lock():
            rects = [int(val) for val in self.__cv2_process.output_data]
        with self.__cv2_process.error_data.get_lock():
            error = int(self.__cv2_process.error_data.value)
        self.__teardown_thread()
        if all(val>0 for val in rects) and len(rects) == 9 and error==0:
            self.__r1 = tuple(rects[0:4])
            self.__r2 = tuple(rects[4:8])
            self.__h = rects[8]
            self.__select_volumes()
        else:
            self.__bad_regions(error)

    def __select_volumes(self):
        self.initial_frame.pack_forget()
        self.volume_frame.pack()
        self.__refentry.configure(border_color = ApplicationTheme.MANUAL_PUMP_COLOR)
        self.__refentry.focus_set()

    def __teardown_thread(self):
        if self.__unregister_exit_condition:
            self.__unregister_exit_condition()
            self.__unregister_exit_condition = None
        if self.__cv2_process.is_alive():
            self.__cv2_process.terminate()
            self.__cv2_process.join()
            self.__cv2_process.exit_flag.clear()
        self.__cv2_process = InputProcess(self.__filter_type,self.__video_params,window_name="Set up level visualisation")

    def __confirm_volumes(self):
        ref_vol_str = self.refvar.get()
        if _validate_volume(ref_vol_str,allow_empty=False):
            self.__teardown_thread()
            self.destroy_successfully(self.__r1,self.__r2,self.__h,float(ref_vol_str))
        else:
            self.__refentry.configure(border_color=ApplicationTheme.ERROR_COLOR)
            
    def destroy(self):
        super().destroy()
        self.__teardown_thread()

class LevelSelect(AlertBox[Rect,Rect,Rect,float]):
    def __init__(self, on_success = None, on_failure = None, auto_resize=True):
        super().__init__(on_success, on_failure, auto_resize)
    def create(self, root):
        return _LevelSelectFrame(root,on_success=self.on_success,on_failure=self.on_failure)


@event_group
class LSEvent:
    @dataclass
    class UpdateVideoDevices:
        module: str
        backend: CaptureBackend
        force_newlist: bool

    @dataclass
    class NotifyNewVideoDevices:
        module: str
        backend: CaptureBackend
        devices: list[str]|list[int]

class LevelSettingsController(UIController):

    def __init__(self, root, debug=False):
        super().__init__(root, debug)
        self.add_listener(LSEvent.UpdateVideoDevices,self.__get_new_video_devices)

    def __get_new_video_devices(self, event: LSEvent.UpdateVideoDevices):
        vd_state = SharedState[list[str]|list[int]]()

        def _vd_thread(module: str, backend: CaptureBackend, force_new: bool, shared_state = SharedState[list[str]|list[int]]):
            try:
                new_list = None
                if module == "Pygame":
                    new_list = PygameCapture.get_cameras(force_newlist=force_new,backend=backend)
                elif module == "OpenCV":
                    new_list = CV2Capture.get_cameras()
                if new_list:
                    shared_state.set_value(new_list)
            except RuntimeError:
                shared_state.set_value([])

        vd_thread = threading.Thread(target=_vd_thread,args=(event.module,event.backend,event.force_newlist,vd_state))

        def _on_complete(new_list: list[str]|list[int]):
            self.notify_event(LSEvent.NotifyNewVideoDevices(event.module,event.backend,new_list))
            vd_thread.join()
        
        self._add_state(vd_state,_on_complete,single_call=True)
        vd_thread.start()

class _LevelSettingsFrame(AlertBoxBase[dict[Settings,Any]]):


    __NUM_CAMERA_SETTINGS = 3
    ALERT_TITLE = "Level Sensing Settings"

    VD_LOADING = "Loading..."
    NO_VD_FOUND = "No video devices detected"

    OTSU_DISPLAY = "Non-parametric thresholding"
    LINKNET_DISPLAY = "LinkNet FCN"
    NONE_DISPLAY = "None (no fluid detection)"

    def __init__(self, master: ctk.CTk, controller: UIController, *args, on_success: Callable[[dict[Settings,Any]], None] | None = None, on_failure: Callable[[None], None] | None = None, fg_color: str | tuple[str, str] | None = None, **kwargs):
        super().__init__(master, *args, on_success=on_success, on_failure=on_failure, fg_color=fg_color, **kwargs)
        self.title(self.ALERT_TITLE)
        self.controller = controller
        all_settings = read_settings(*LEVEL_SETTINGS)
        self.__prev_filecapture_directory = all_settings[Settings.FILECAPTURE_DIRECTORY]
        prev_interface: str = all_settings[Settings.CAMERA_INTERFACE_MODULE]
        prev_vd: int = all_settings[Settings.VIDEO_DEVICE]
        prev_auto_exposure: bool = all_settings[Settings.AUTO_EXPOSURE]
        prev_exposure_time: int = all_settings[Settings.EXPOSURE_TIME]
        prev_sensing_period: float = all_settings[Settings.SENSING_PERIOD]
        prev_average_period: float = all_settings[Settings.AVERAGE_WINDOW_WIDTH]
        prev_stabilisation_period: float = all_settings[Settings.LEVEL_STABILISATION_PERIOD]
        prev_backend: CaptureBackend = all_settings[Settings.CAMERA_BACKEND]
        prev_rescale_factor: float = all_settings[Settings.IMAGE_RESCALE_FACTOR]
        prev_filter: ImageFilterType = all_settings[Settings.IMAGE_FILTER]
        # prev_period: float = all_settings[Settings.IMAGE_SAVE_PERIOD]

        def display_name_from_filter(filter: ImageFilterType) -> str:
            match filter:
                case ImageFilterType.OTSU:
                    return self.OTSU_DISPLAY
                case ImageFilterType.LINKNET:
                    return self.LINKNET_DISPLAY
                case ImageFilterType.NONE:
                    return self.NONE_DISPLAY
                case _:
                    return self.NONE_DISPLAY
        def filter_from_display_name(display_name: str) -> ImageFilterType:
            match display_name:
                case self.OTSU_DISPLAY:
                    return ImageFilterType.OTSU
                case self.LINKNET_DISPLAY:
                    return ImageFilterType.LINKNET
                case self.NONE_DISPLAY:
                    return ImageFilterType.NONE
                case _:
                    return ImageFilterType.NONE
                
        prev_filter_displayname = display_name_from_filter(prev_filter)
        filter_displaynames = [display_name_from_filter(f) for f in ImageFilterType]

        segment_frames, self.confirm_button, _ = self.generate_layout("Camera Settings","Computer Vision Settings",confirm_command=self.__confirm_selections)
        camera_frame = segment_frames[0]
        cv_frame = segment_frames[1]
        
        self.rescale_var = make_and_grid(make_entry,camera_frame,"Image Rescaling Factor",Settings.IMAGE_RESCALE_FACTOR,prev_rescale_factor,0,map_fun=float,entry_validator = _validate_scale_factor, on_return = self.__confirm_selections)
        # self.save_period_var = make_and_grid(make_entry, camera_frame, "Period Between Image Saves", Settings.IMAGE_SAVE_PERIOD, prev_period, 2, map_fun=float, entry_validator = _validate_time_float, on_return = self.__confirm_selections, units="s")
        self.filter_var = make_and_grid(make_menu,camera_frame,"Detector Type",Settings.IMAGE_FILTER,prev_filter_displayname,1,values=filter_displaynames,map_fun=lambda ift_str: filter_from_display_name(ift_str))
        self.interface_var = make_and_grid(make_menu,camera_frame,"Camera Module Interface",Settings.CAMERA_INTERFACE_MODULE,prev_interface,2,values=Capture.supported_interfaces(debug=controller.debug))
        self.interface_var.trace_add(self.__interface_changed)

        self.sense_period_var = make_and_grid(make_entry,cv_frame,"Image Capture Period",Settings.SENSING_PERIOD,str(prev_sensing_period),1,entry_validator = _validate_time_float,units="s",map_fun=float,on_return=self.__confirm_selections)
        self.average_var = make_and_grid(make_entry,cv_frame,"Moving Average Period",Settings.AVERAGE_WINDOW_WIDTH, str(prev_average_period),2,entry_validator = _validate_time_float,units = "s",map_fun=float,on_return=self.__confirm_selections)
        self.stabilisation_var = make_and_grid(make_entry,cv_frame,"Stabilisation Period",Settings.LEVEL_STABILISATION_PERIOD, str(prev_stabilisation_period),3,entry_validator = _validate_time_float,units="s",map_fun=float,on_return=self.__confirm_selections)

        # add self.save_period_var back
        self.permanent_vars = [self.rescale_var,self.filter_var,self.interface_var,self.sense_period_var,self.average_var,self.stabilisation_var]
        
        #----------CV2 Settings-------------
        self.cv2_widget_group = WidgetGroup(initial_row=self.__NUM_CAMERA_SETTINGS)

        cv2_available_backends = [be.value for be in CV2Capture.get_backends()]
        cv2_display_backend = prev_backend.value if prev_backend.value in cv2_available_backends else cv2_available_backends[0]
        self.cv2_backend_var = make_and_group(make_menu,
                                               camera_frame,
                                               "Camera Backend Provider",
                                               Settings.CAMERA_BACKEND,
                                               cv2_display_backend,
                                               self.cv2_widget_group,
                                               map_fun=lambda be: CaptureBackend(be),
                                               values=cv2_available_backends)

        self.cv2_vd_var = make_and_group(make_entry,
                                          camera_frame,
                                          "Camera Device Number",
                                          Settings.VIDEO_DEVICE,
                                          prev_vd,
                                          self.cv2_widget_group,
                                          map_fun=int,
                                          entry_validator=_validate_device,
                                          on_return = self.__confirm_selections
                                          )
        
        self.cv2_exposure_method_var = make_and_group(make_segmented_button,
                                                       camera_frame,
                                                       "Camera Exposure Determination",
                                                       Settings.AUTO_EXPOSURE,
                                                       "Auto" if prev_auto_exposure else "Manual",
                                                       self.cv2_widget_group,
                                                       map_fun= lambda str_in: str_in == "Auto",
                                                       values=["Auto","Manual"],
                                                       command=self.__exposure_method_changed
                                                       )
        current_row = self.cv2_widget_group.current_row
        self.cv2_manual_exposure_group = WidgetGroup(initial_row=current_row+1,parent=self.cv2_widget_group)
        self.exposure_time_var = make_and_group(make_entry,
                                                 camera_frame,
                                                 "Manual Exposure Time",
                                                 Settings.EXPOSURE_TIME,
                                                 str(prev_exposure_time),
                                                 self.cv2_manual_exposure_group,
                                                 map_fun=int,
                                                 entry_validator=_validate_exposure,
                                                 on_return=self.__confirm_selections)
        
        #-----------Pygame Settings--------------
        self.pygame_widget_group = WidgetGroup(initial_row=self.__NUM_CAMERA_SETTINGS)
        # backend selection dropdown menu
        pygame_available_backends = [be.value for be in PygameCapture.get_backends()]
        pygame_display_backend = prev_backend.value if prev_backend.value in pygame_available_backends else CaptureBackend.ANY.value
        self.pygame_backend_var = make_and_group(make_menu,   
                                                  camera_frame,
                                                  "Camera Backend Provider",
                                                  Settings.CAMERA_BACKEND,
                                                  pygame_display_backend,
                                                  self.pygame_widget_group,
                                                  map_fun=lambda str_in: CaptureBackend(str_in),
                                                  values=pygame_available_backends)
        self.pygame_backend_var.trace_add(self.__maybe_refresh_pygame_cameras)

        # camera selection dropdown menu
        if prev_interface == "Pygame":
            device_list = PygameCapture.get_cameras(backend=prev_backend)
            if prev_vd < len(device_list):
                selected_device = device_list[prev_vd]
            else:
                selected_device = device_list[0]
        else:
            selected_device = "Loading..."
            device_list = ["Loading..."]
        self.pygame_vd_var = make_and_group(make_menu,
                                             camera_frame,
                                             "Camera Device",
                                             Settings.VIDEO_DEVICE,
                                             selected_device,
                                             self.pygame_widget_group,
                                             map_fun = self.__cast_pygame_camera,
                                             values=device_list,
                                             refresh_function=lambda: self.__maybe_refresh_pygame_cameras(force_new=True))
        # ----------------------- FILE CAPTURE ------------------------------

        self.file_widget_group = WidgetGroup(self.__NUM_CAMERA_SETTINGS)
        self.file_capture_directory = make_and_group(make_fileselect,
                                                      camera_frame,
                                                      "Directory",
                                                      Settings.FILECAPTURE_DIRECTORY,
                                                      str(self.__prev_filecapture_directory) if self.__prev_filecapture_directory else "",
                                                      self.file_widget_group,
                                                      file_command=self.__request_filecapture_directory,
                                                      on_return=self.__confirm_selections
                                                      )

        self.widget_dict: dict[str,WidgetGroup] = {"OpenCV": self.cv2_widget_group,"Pygame":self.pygame_widget_group,"File":self.file_widget_group}
        
        self.controller.add_listener(LSEvent.NotifyNewVideoDevices,self.__handle_new_cameras)
        
        self.__interface_changed()

    def __validate_pygame_camera(self,selected_camera):
        selected_backend = CaptureBackend(self.pygame_backend_var.get())
        return selected_camera in PygameCapture.get_cameras(backend=selected_backend)
    def __cast_pygame_camera(self,selected_camera):
        selected_backend = CaptureBackend(self.pygame_backend_var.get())
        current_device_list = PygameCapture.get_cameras(backend=selected_backend)
        if selected_camera in current_device_list:
            return current_device_list.index(selected_camera)
        return DEFAULT_SETTINGS[Settings.VIDEO_DEVICE]

    def __maybe_refresh_pygame_cameras(self,*args, force_new = False):
        selected_backend = CaptureBackend(self.pygame_backend_var.get())
        # selected_camera = self.pygame_vd_var.get()
        if self.pygame_vd_var.widget is not None:
            self.pygame_vd_var.widget.configure(values=[self.VD_LOADING])
            self.pygame_vd_var.set(self.VD_LOADING)
            self.pygame_vd_var.disable()
            self.pygame_backend_var.disable()
            self.interface_var.disable()
            self.confirm_button.configure(state=ctk.DISABLED)
        self.controller.notify_event(LSEvent.UpdateVideoDevices("Pygame",selected_backend,force_new))

    def __handle_new_cameras(self, event: LSEvent.NotifyNewVideoDevices):
        if event.module != "Pygame":
            return
        if len(event.devices) == 0:
            # no video devices available on this backend
            if event.backend == CaptureBackend.ANY:
                # nothing else to do, just state there are no video devices
                self.pygame_vd_var.widget.configure(values=["No Video Devices Found"])
                self.pygame_vd_var.set("No Video Devices Found")
                self.pygame_backend_var.enable()
                self.interface_var.enable()
            else:
                # there may just be no cameras for the selected backend in particular, so revert to default backend
                self.pygame_backend_var.set(CaptureBackend.ANY.value)
                self.pygame_backend_var.widget.configure(fg_color = ApplicationTheme.ERROR_COLOR)
                self.after(1000,lambda: self.pygame_backend_var.widget.configure(fg_color = ctk.ThemeManager.theme["CTkOptionMenu"]["fg_color"]))
                self.__maybe_refresh_pygame_cameras()
            return
        prev_camera = self.pygame_vd_var.get()
        if prev_camera not in event.devices:
            self.pygame_vd_var.set(event.devices[0])
        self.pygame_vd_var.enable()
        self.pygame_vd_var.widget.configure(values=event.devices)
        self.pygame_backend_var.enable()
        self.interface_var.enable()
        self.confirm_button.configure(state=ctk.NORMAL)

    def __request_filecapture_directory(self):
        if self.__prev_filecapture_directory is None or not os.path.isdir(self.__prev_filecapture_directory):
            self.__prev_filecapture_directory = Path().parent
        dir_out = ctk.filedialog.askdirectory(initialdir=self.__prev_filecapture_directory,mustexist=True)
        self.bring_forward()
        if dir_out != "":
            self.__prev_filecapture_directory = dir_out
        return dir_out

    def __interface_changed(self,*args):
        new_interface = self.interface_var.get()
        group_of_interest = self.widget_dict[new_interface]
        for interface_group in self.widget_dict.values():
            if interface_group != group_of_interest:
                interface_group.hide()
        group_of_interest.show()
        self.visible_group = group_of_interest
        if new_interface == "OpenCV":
            self.__exposure_method_changed()
        elif new_interface == "Pygame":
            self.__maybe_refresh_pygame_cameras()

    def __exposure_method_changed(self,*args):
        new_method = self.cv2_exposure_method_var.get()
        if new_method == "Auto":
            self.cv2_manual_exposure_group.hide()
            self.exposure_time_var.widget.configure(border_color=ApplicationTheme.MANUAL_PUMP_COLOR)
        else:
            self.cv2_manual_exposure_group.show()

    def __confirm_selections(self):
        #TODO grab the state in a better way - using "_" variables is vulnerable to deprecation in future ctk patches
        if self.confirm_button._state == ctk.DISABLED:
            return
        all_valid = True
        temp_vars = self.visible_group.get_vars()
        all_vars = [*self.permanent_vars,*temp_vars]
        for var in all_vars:
            if not var.is_valid():
                all_valid = False
                break
        if all_valid:
            all_settings = {var.setting:var.get_mapped() for var in all_vars}
            modifications = modify_settings(all_settings)
            self.destroy_successfully(modifications)
            return

        for var in all_vars:
            if isinstance(var.widget,ctk.CTkEntry):
                entry_fgcolor = ApplicationTheme.MANUAL_PUMP_COLOR if var.is_valid() else ApplicationTheme.ERROR_COLOR
                var.widget.configure(border_color=entry_fgcolor)

class LevelSettingsBox(AlertBox[dict[Settings,Any]]):
    def __init__(self, on_success = None, on_failure = None, auto_resize=True):
        super().__init__(on_success, on_failure, auto_resize)
    def create(self, root):
        controller = LevelSettingsController(root,root.debug)
        return _LevelSettingsFrame(root,controller,on_success=self.on_success,on_failure = self.on_failure)

_TimedReading = tuple[float,float,float,float,float]
def _mean_data(data: list[_TimedReading]) -> _TimedReading:
    n = len(data)
    if n<1:
        return
    out = [0.0,0.0,0.0,0.0,0.0]
    for j in range(0,5):
        meanval = 0
        for k in range(0,n):
            meanval += data[k][j]
        meanval = meanval/n
        out[j] = meanval
    return tuple(out)

class _LevelDisplayFrame(AlertBoxBase[None]):

    MIN_DISPLAY_DATA = 500
    MAX_DISPLAY_DATA = 1000
    BUFFER_SIZE = 10
    ALERT_TITLE = "Level Visualiser"

    def __init__(self, master: UIRoot, level_state: SharedState[tuple[LevelReading|None,np.ndarray]], *args, on_success: Callable[[None], None] | None = None, on_failure: Callable[[None], None] | None = None, fg_color: str | tuple[str, str] | None = None, **kwargs):
        super().__init__(master, *args, on_success=on_success, on_failure=on_failure, fg_color=fg_color, **kwargs)
        self.teardown_window = master.register_state(level_state,self.__update_display)
        self.title(self.ALERT_TITLE)
        
        self.initial_time = time.time()

        self.info_frame = ctk.CTkFrame(self)

        self._initial_image_array = np.zeros((720,720,3),dtype=np.uint8)
        initial_image = ctk.CTkImage(Image.fromarray(self._initial_image_array),size=self._initial_image_array.shape[:-1][::-1])
        self.img_box = ctk.CTkLabel(self.info_frame,image=initial_image,text="")

        self.input_buffer: list[_TimedReading] = []
        self.prev_values: list[_TimedReading] = []
        self.update_graph = True


        self.mode_var = ctk.StringVar(self,value="Image")
        self.mode_switcher = ctk.CTkSegmentedButton(self,values=["Image","Graph"],variable=self.mode_var,corner_radius=ApplicationTheme.BUTTON_CORNER_RADIUS,)
        self.mode_var.trace_add("write",self.__mode_change)
        self.mode_switcher.grid(row=1,column=0,padx=10,pady=10,sticky="ns")
        self.info_frame.grid(row=0,column=0,padx=10,pady=10,sticky="nsew")
        self._prev_state = None

        # graph objs
        self.fig = Figure(figsize=(5,4),dpi=200)
        self.ax = self.fig.add_subplot()
        self.ax.set_xlabel("Elapsed Time (s)")
        self.ax.set_ylabel("Level (mL)")
        self.canvas = FigureCanvasTkAgg(figure=self.fig,master=self.info_frame)
        self.graph_box = self.canvas.get_tk_widget()
        self.__mode_change()

    @staticmethod
    def __aggregate_data(vals_in: list[_TimedReading]) -> list[_TimedReading]:
        # aggregate data by windowing until minimum size is reached
        # do this in place so that no memory is wasted
        step = LevelDisplay.MAX_DISPLAY_DATA//LevelDisplay.MIN_DISPLAY_DATA
        for i in range(0,LevelDisplay.MIN_DISPLAY_DATA):
            lower_index = i*step
            upper_index = lower_index + step
            try:
                curr_data = vals_in[lower_index:upper_index]
                mean = _mean_data(curr_data)
                vals_in[i] = mean
            except IndexError:
                break
        return vals_in[:i]
    
    def __update_display(self,new_state: LevelOutput|None):
        if new_state is None:
            return
    
        mode = self.mode_var.get()
        if new_state is not None and new_state.levels is not None:

            # add value to buffer
            timed_reading = (time.time()-self.initial_time,*new_state.levels)
            self.input_buffer.append(timed_reading)

            # add buffer to main data
            if len(self.input_buffer)>=self.BUFFER_SIZE or len(self.prev_values)<self.BUFFER_SIZE:
                self.prev_values = [*self.prev_values,*self.input_buffer]
                self.input_buffer.clear()
                self.update_graph = True

            # aggregate main data if it gets too long
            if len(self.prev_values)>self.MAX_DISPLAY_DATA:
                self.prev_values = self.__aggregate_data(self.prev_values)

            if mode == "Image":
                self.__place_image(new_state.levels, new_state.filtered_image)
            elif mode == "Graph" and self.update_graph:
                self.__place_graph()
                self.update_graph = False
        else:
            if mode == "Image":
                self.__place_image([0,0,0,0],self._initial_image_array)
        self._prev_state = new_state

    def __place_image(self, new_levels: LevelReading, new_image: np.ndarray):
        # write information text
        cv2.putText(new_image, f'Electrolyte Loss: {0-new_levels[3]} mL', (10,50), cv2.FONT_HERSHEY_SIMPLEX, 
                    0.75, (255, 0, 0), 2, cv2.LINE_AA)
        cv2.putText(new_image, f'Anolyte: {new_levels[0]} mL', (10,80), cv2.FONT_HERSHEY_SIMPLEX, 
                    0.75, (255, 0, 0), 2, cv2.LINE_AA)
        cv2.putText(new_image, f'Catholyte: {new_levels[1]}mL', (10,110), cv2.FONT_HERSHEY_SIMPLEX, 
                    0.75, (255, 0, 0), 2, cv2.LINE_AA)
        cv2.putText(new_image, f'Diff: {new_levels[2]} mL', (10,140), cv2.FONT_HERSHEY_SIMPLEX, 
                    0.75, (255, 0, 0), 2, cv2.LINE_AA)
        ctkimg = ctk.CTkImage(Image.fromarray(new_image),size=new_image.shape[:-1][::-1])
        self.img_box.configure(image=ctkimg)

    def __place_graph(self):
        self.ax.clear()
        data = np.array(self.prev_values)
        times = data[:,0]
        anolyte = data[:,1]
        catholyte = data[:,2]
        diff = data[:,3]
        total = data[:,4]
        self.ax.plot(times,anolyte,label="Anolyte")
        self.ax.plot(times,catholyte,label="Catholyte")
        self.ax.plot(times,diff,label="Difference")
        self.ax.plot(times,total,label="Total")
        self.ax.legend()
        self.canvas.draw()

    def __mode_change(self,*args):
        new_mode = self.mode_var.get()
        grid_args = {
            "row":0,
            "column":0,
            "padx":0,
            "pady":0,
            "sticky":"nsew"
        }
        if new_mode == "Image":
            self.graph_box.grid_forget()
            self.img_box.grid(**grid_args)
        else:
            self.img_box.grid_forget()
            self.graph_box.grid(**grid_args)
        self.__update_display(self._prev_state)

    def _destroy_quietly(self):
        self.teardown_window()
        return super()._destroy_quietly()

class LevelDisplay(AlertBox):
    def __init__(self, level_state: SharedState[tuple[LevelReading|None,np.ndarray]], on_success = None, on_failure = None, auto_resize=True):
        super().__init__(on_success, on_failure, auto_resize)
        self.level_state = level_state
    def create(self, root):
        return _LevelDisplayFrame(root,self.level_state,on_success=self.on_success,on_failure=self.on_failure)

@validator_function
def _validate_volume(p: str,allow_empty = True):
    try:
        nump = float(p)
        if nump > 0:
            return True
        if nump == 0 and allow_empty:
            return True
        return False
    except ValueError:
        if p == "" and allow_empty:
            return True
        return False
@validator_function
def _validate_time_float(timestr: str, allow_empty = True):
    if timestr == "":
        return allow_empty
    try:
        t = float(timestr)
        if t>0 or (t==0 and allow_empty):
            return True
        return False
    except:
        return False
@validator_function
def _validate_exposure(exp: str, allow_empty: bool = True) -> bool:
    if exp in ("","-",".") and allow_empty:
        return True
    try:
        int(exp)
        return True
    except:
        return False
@validator_function
def _validate_scale_factor(sf: str, allow_empty = True):
    MAX_FACTOR = 10
    if sf == "":
        return allow_empty
    try:
        f = float(sf)
        if f>(1/MAX_FACTOR) and f<MAX_FACTOR or (f>=0 and allow_empty):
            return True
        return False
    except:
        return False
@validator_function
def _validate_device(p: str, allow_empty = True):
    try:
        nump = int(p)
        if nump >= 0:
            return True
        return False
    except ValueError:
        if p == "" and allow_empty:
            return True
        return False


