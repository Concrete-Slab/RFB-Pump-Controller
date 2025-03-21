from typing import Iterable
from support_classes.settings_interface import CAMERA_SETTINGS
from ui_root import UIRoot, UIController
from pump_control import Pump, PumpState, ReadyState, ErrorState, PIDException, LevelException, ReadException
from .CONTROLLER_EVENTS import CEvents, ProcessName
from serial_interface import InterfaceException, WriteCommand
from support_classes import GeneratorException, PumpNames, PumpConfig
from .processes import PIDProcess, LevelProcess, DataProcess, BaseProcess

class ControllerPageController(UIController):

    DEFAULT_VIDEO_DEVICE = 0

    def __init__(self, root: UIRoot, pump: Pump) -> None:
        super().__init__(root)
        self.pump = pump
        self.__polling_removal_callbacks = []
        # important event checker - if the pump thread ends then it will need to be joined with main to signal it for garbage colelction
        # pump_join_remover = self._add_event(pump.join_event,pump.stop_event_loop,single_call=True)
        # self.__other_removal_callbacks.append(pump_join_remover)

        self.__level_process = LevelProcess(self,pump)

        self.PROCESS_MAP: dict[ProcessName,BaseProcess] = {
            ProcessName.PID: PIDProcess(self,pump),
            ProcessName.LEVEL: self.__level_process,
            ProcessName.DATA: DataProcess(self,pump)
        }

        # General process events
        def start_process(event: CEvents.StartProcess):
            self.PROCESS_MAP[event.process_name].start()
        self.add_listener(CEvents.StartProcess,start_process)
        def close_process(event: CEvents.CloseProcess):
            self.PROCESS_MAP[event.process_name].close()
        self.add_listener(CEvents.CloseProcess,close_process)
        def open_settings(event: CEvents.OpenSettings):
            self.PROCESS_MAP[event.process_name].open_settings()
        self.add_listener(CEvents.OpenSettings, open_settings)

        self.add_listener(CEvents.ManualDutySet,lambda event: self.pump.manual_set_duty(event.pump_id, event.new_duty))

        self.add_listener(CEvents.SettingsModified,self.__handle_settings_changed)

        self.add_listener(CEvents.OpenROISelection,lambda event: self.__level_process.request_ROIs())

        self.add_listener(CEvents.StopAll,lambda event: self.pump.run_sync(self.pump.emergency_stop,args=([pmp for pmp in PumpConfig().pumps],)))        
        
        # General state poll bindings
        self._add_queue(pump.queue,self.__handle_pump_state)
        self._add_queue(pump.serial_writes,self.__handle_serial_write)

        # begin reading the pump speeds
        self.__start_polling()

    
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

    def __handle_serial_write(self, new_write: WriteCommand):
        self.notify_event(CEvents.AutoDutySet(PumpConfig().pumps(new_write.pump), new_write.duty))

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
            self.__level_process.level_data = None
        self.pump.change_settings(modifications)
        