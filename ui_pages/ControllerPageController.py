from .UIController import UIController
from ui_root import UIRoot
from pump_control import Pump, PumpNames, PumpState, ReadyState, ErrorState, PIDException, LevelException, ReadException
from .CV2Warning import CV2Warning
from .PAGE_EVENTS import CEvents, ProcessName
from typing import Tuple
from serial_interface import InterfaceException
    

class ControllerPageController(UIController):

    DEFAULT_VIDEO_DEVICE = 0

    def __init__(self, root: UIRoot, pump: Pump) -> None:
        super().__init__(root)
        self.pump = pump
        self.__polling_removal_callbacks = []
        self.__pid_removal_callbacks = []
        self.__level_removal_callbacks = []
        self.__other_removal_callbacks = []

        # important event checker - if the pump thread ends then it will need to be joined with main to signal it for garbage colelction
        # pump_join_remover = self._add_event(pump.join_event,pump.stop_event_loop,single_call=True)
        # self.__other_removal_callbacks.append(pump_join_remover)


        # General process events
        self.add_listener(CEvents.START_PROCESS,self.__start_process)
        self.add_listener(CEvents.CLOSE_PROCESS,self.__close_process)
        self.add_listener(CEvents.MANUAL_DUTY_SET,self.pump.manual_set_duty)

        # PID events




        # Datalogging events





        # Level sensing events

        self.add_listener(CEvents.LEVEL_DATA_ACQUIRED,self.__send_level_config)

        # General state poll bindings
        pump_state_remover = self._add_state(pump.state,self.__handle_pump_state)
        self.__other_removal_callbacks.append(pump_state_remover)

        # begin reading the pump speeds
        self.__start_polling()

        

    # GENERAL PROCESS CALLBACKS
    def __start_process(self,process_prefix: str):
        match process_prefix:
            case ProcessName.PID:
                self.__start_pid()
            case ProcessName.LEVEL:
                self.__start_level()
            case ProcessName.DATA:
                self.__start_data()

    def __close_process(self,process_prefix: str):
        match process_prefix:
            case ProcessName.PID:
                self.__close_pid()
            case ProcessName.DATA:
                self.__close_data()
            case ProcessName.LEVEL:
                self.__close_level()

    def __handle_pump_state(self, newstate: PumpState):
        # print("ControllerPageController detected new pumpstate",newstate.__class__.__name__)
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

    # PID CALLBACKS

    def __start_pid(self):
        (state_running,state_duties) = self.pump.start_pid()
        if len(self.__pid_removal_callbacks) == 0:
            self.__pid_removal_callbacks.append(self._add_state(state_running,self.__handlerunning_pid))
            self.__pid_removal_callbacks.append(self._add_state(state_duties,self.__handleduties_pid))

    def __close_pid(self):
        self.pump.stop_pid()

    def __handlerunning_pid(self,newstate: bool):
        if newstate:
            self.notify_event(CEvents.PROCESS_STARTED,ProcessName.PID)
        else:
            self.notify_event(CEvents.PROCESS_CLOSED,ProcessName.PID)

    def __handleduties_pid(self,newduties: Tuple[float,float]):
        dutyA = newduties[0]
        dutyB = newduties[1]
        self.notify_event(CEvents.AUTO_DUTY_SET,PumpNames.A,dutyA)
        self.notify_event(CEvents.AUTO_DUTY_SET,PumpNames.B,dutyB)

    def __unregister_pid(self):
        self.__close_pid()
        for rmcb in self.__pid_removal_callbacks:
            rmcb()

    # DATA LOGGING CALLBACKS
    def __start_data(self):
        pass

    def __close_data(self):
        pass
    
    # LEVEL SENSING CALLBACKS
    def __start_level(self):
        box = self._create_alert(CV2Warning,default_video_device=ControllerPageController.DEFAULT_VIDEO_DEVICE)
        print("after box line")

    def __send_level_config(self,device_number: int, r1: tuple[int,int,int,int], r2: tuple[int,int,int,int], h: tuple[int,int,int,int], ref_vol: float, init_vol: float):
        (state_running,state_levels) = self.pump.start_levels(device_number,r1,r2,h,ref_vol,init_vol)
        
        if len(self.__level_removal_callbacks) == 0:
            self.__level_removal_callbacks.append(self._add_state(state_running,self.__handlerunning_level))
            self.__level_removal_callbacks.append(self._add_state(state_levels,self.__handlelevels_level))
    
    def __handlerunning_level(self,isrunning: bool):
        if isrunning:
            self.notify_event(CEvents.PROCESS_STARTED,ProcessName.LEVEL)
        else:
            self.notify_event(CEvents.PROCESS_CLOSED,ProcessName.LEVEL)
    
    def __handlelevels_level(self,newbuffer):
        pass

    def __close_level(self):
        self.pump.stop_levels()
        
    # SERIAL POLLING CALLBACKS
    def __start_polling(self):
        (state_running,state_speeds) = self.pump.start_polling()
        if len(self.__pid_removal_callbacks) == 0:
            # self.__polling_removal_callbacks.append(self._add_state(state_running,self.__handlerunning_poller))
            self.__polling_removal_callbacks.append(self._add_state(state_speeds,self.__handlespeeds_poller))

    def __close_poller(self):
        self.pump.stop_polling()

    def __handlerunning_poller(self,newstate):
        pass
        # if newstate:
        #     self.notify_event(CEvents.PROCESS_STARTED,ProcessName.PID)
        # else:
        #     self.notify_event(CEvents.PROCESS_CLOSED,ProcessName.PID)

    def __handlespeeds_poller(self,newspeeds: dict[PumpNames,float]):
        new_dict = newspeeds
        for pmp in new_dict.keys():
            self.notify_event(CEvents.AUTO_SPEED_SET,pmp,new_dict[pmp])


        



        


