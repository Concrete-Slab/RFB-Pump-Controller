from typing import Any, Iterable
from support_classes.settings_interface import CAMERA_SETTINGS, Settings, CaptureBackend
from ui_root import UIRoot, UIController
from pump_control import Pump, PumpState, ReadyState, ActiveState, ErrorState, PIDException, LevelException, ReadException
from .CONTROLLER_EVENTS import CEvents, ProcessName
from serial_interface import InterfaceException
from support_classes import GeneratorException, PumpNames, PumpConfig, SharedState, PygameCapture, CV2Capture
from .process_controllers import BaseProcess, LevelProcess
import threading
    

class ControllerPageController(UIController):

    DEFAULT_VIDEO_DEVICE = 0

    def __init__(self, root: UIRoot, pump: Pump) -> None:
        super().__init__(root)
        self.pump = pump
        self.__polling_removal_callbacks = []
        self.__other_removal_callbacks = []

        # important event checker - if the pump thread ends then it will need to be joined with main to signal it for garbage colelction
        # pump_join_remover = self._add_event(pump.join_event,pump.stop_event_loop,single_call=True)
        # self.__other_removal_callbacks.append(pump_join_remover)

        # dependency injection
        for process in ProcessName:
            BaseProcess.instanceof(process).set_context(self,self.pump)

        # General process events
        def start_process(event: CEvents.StartProcess):
            BaseProcess.instanceof(event.process_name).start()
        self.add_listener(CEvents.StartProcess,start_process)
        def close_process(event: CEvents.CloseProcess):
            BaseProcess.instanceof(event.process_name).close()
        self.add_listener(CEvents.CloseProcess,close_process)
        def open_settings(event: CEvents.OpenSettings):
            BaseProcess.instanceof(event.process_name).open_settings()
        self.add_listener(CEvents.OpenSettings, open_settings)

        self.add_listener(CEvents.ManualDutySet,lambda event: self.pump.manual_set_duty(event.pump_id, event.new_duty))

        self.add_listener(CEvents.SettingsModified,self.__handle_settings_changed)

        self.add_listener(CEvents.OpenROISelection,lambda event: LevelProcess.get_instance().request_ROIs())

        self.add_listener(CEvents.StopAll,lambda event: self.pump.run_sync(self.pump.emergency_stop,args=([pmp for pmp in PumpConfig().pumps],)))

        self.add_listener(CEvents.UpdateVideoDevices,self.__get_new_video_devices)
        
        
        # General state poll bindings
        pump_state_remover = self._add_queue(pump.queue,self.__handle_pump_state)
        self.__other_removal_callbacks.append(pump_state_remover)

        # begin reading the pump speeds
        self.__start_polling()

    def __get_new_video_devices(self, event: CEvents.UpdateVideoDevices):

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
            self.notify_event(CEvents.NotifyNewVideoDevices(event.module,event.backend,new_list))
            vd_thread.join()
        
        self._add_state(vd_state,_on_complete,single_call=True)
        vd_thread.start()

    def __handle_pump_state(self, newstate: PumpState):
        if isinstance(newstate,ErrorState):
            error = newstate.error
            if isinstance(error,InterfaceException):
                msg = str(error)
                if msg == "" or msg[0] == "<":
                    msg = "Serial port disconnected"
                # self._nextpage("port_select_page",starting_prompt=msg)
                # TODO implement back_custom without import clashes
                self._back()
            if isinstance(error,LevelException) or isinstance(error,PIDException) or isinstance(error,ReadException):
                self.notify_event(CEvents.Error(error))
        elif isinstance(newstate,ReadyState):
            self.notify_event(CEvents.Ready())
        elif isinstance(newstate, ActiveState):
            for pmp in newstate.auto_duties.keys():
                self.notify_event(CEvents.AutoDutySet(pmp,newstate.auto_duties[pmp]))

    # SERIAL POLLING CALLBACKS
    def __start_polling(self):
        (state_running,state_speeds) = self.pump.start_polling()
        if len(self.__polling_removal_callbacks) == 0:
            self.__polling_removal_callbacks.append(self._add_state(state_running,self.__handlerunning_poller))
            self.__polling_removal_callbacks.append(self._add_state(state_speeds,self.__handlespeeds_poller))

    def __close_poller(self):
        self.pump.stop_polling()

    def __handlerunning_poller(self,newstate: bool):
        if not newstate:
            self.notify_event(CEvents.Error(GeneratorException("Speed readings have stopped unexpectedly")))

    def __handlespeeds_poller(self,newspeeds: dict[PumpNames,float]):
        new_dict = newspeeds
        for pmp in new_dict.keys():
            self.notify_event(CEvents.AutoSpeedSet(pmp,new_dict[pmp]))

    # SETTINGS MODIFICATION LOGIC
    def __handle_settings_changed(self, event: CEvents.SettingsModified):
        modifications = event.modifications
        def _contains_any(lst1: Iterable, lst2: Iterable):
            for item in lst1:
                if item in lst2:
                    return True
            return False
        if _contains_any(modifications,CAMERA_SETTINGS):
            # if camera settings are modified, image scaling/size/position may have changed, so need to reselect data
            LevelProcess.get_instance().level_data = None
        self.pump.change_settings(modifications)
        