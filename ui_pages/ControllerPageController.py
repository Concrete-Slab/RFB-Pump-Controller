from typing import Any
from .UIController import UIController
from ui_root import UIRoot
from pump_control import Pump, PumpState, ReadyState, ActiveState, ErrorState, PIDException, LevelException, ReadException
from .PAGE_EVENTS import CEvents
from serial_interface import InterfaceException
from support_classes import GeneratorException, PumpNames
from .process_controllers import ProcessName
    

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
            process.value.get_instance().set_context(self,self.pump)

        # General process events
        def start_process(process: ProcessName):
            process.value.get_instance().start()
        self.add_listener(CEvents.START_PROCESS,start_process)
        def close_process(process: ProcessName):
            process.value.get_instance().close()
        self.add_listener(CEvents.CLOSE_PROCESS,close_process)
        def open_settings(process: ProcessName):
            process.value.get_instance().open_settings()
        self.add_listener(CEvents.OPEN_SETTINGS, open_settings)

        self.add_listener(CEvents.MANUAL_DUTY_SET,self.pump.manual_set_duty)

        self.add_listener(CEvents.SETTINGS_MODIFIED,self.__handle_settings_changed)

        # General state poll bindings
        pump_state_remover = self._add_state(pump.state,self.__handle_pump_state)
        self.__other_removal_callbacks.append(pump_state_remover)

        # begin reading the pump speeds
        self.__start_polling()

    def __handle_pump_state(self, newstate: PumpState):
        if isinstance(newstate,ErrorState):
            error = newstate.error
            if isinstance(error,InterfaceException):
                msg = str(error)
                if msg == "" or msg[0] == "<":
                    msg = "Serial port disconnected"
                self._nextpage("port_select_page",starting_prompt=msg)
            if isinstance(error,LevelException) or isinstance(error,PIDException) or isinstance(error,ReadException):
                self.notify_event(CEvents.ERROR,error)
        elif isinstance(newstate,ReadyState):
            self.notify_event(CEvents.READY)
        elif isinstance(newstate, ActiveState):
            for pmp in newstate.auto_duties.keys():
                self.notify_event(CEvents.AUTO_DUTY_SET,pmp,newstate.auto_duties[pmp])

    # SERIAL POLLING CALLBACKS
    def __start_polling(self):
        (state_running,state_speeds) = self.pump.start_polling()
        if len(self.__polling_removal_callbacks) == 0:
            self.__polling_removal_callbacks.append(self._add_state(state_running,self.__handlerunning_poller))
            self.__polling_removal_callbacks.append(self._add_state(state_speeds,self.__handlespeeds_poller))

    def __close_poller(self):
        self.pump.stop_polling()

    def __handlerunning_poller(self,newstate):
        if not newstate:
            self.notify_event(CEvents.ERROR,GeneratorException("Speed readings have stopped unexpectedly"))

    def __handlespeeds_poller(self,newspeeds: dict[PumpNames,float]):
        new_dict = newspeeds
        for pmp in new_dict.keys():
            self.notify_event(CEvents.AUTO_SPEED_SET,pmp,new_dict[pmp])

    # SETTINGS MODIFICATION LOGIC
    def __handle_settings_changed(self, modifications: dict[str, Any]):
        self.pump.change_settings(modifications)
        