#!/usr/bin/env python
# coding: utf-8

# Import required modules

import numpy as np
from simple_pid import PID
import csv
import datetime
from .async_levelsensor import LevelBuffer
from serial_interface import GenericInterface
import asyncio
from support_classes import Generator,SharedState
from .PUMP_CONSTS import PID_DATA_TIMEOUT, PumpNames


Duties = tuple[int,int]

class PIDRunner(Generator[Duties]):
    
    def __init__(self, level_state: SharedState[LevelBuffer], serial_interface: GenericInterface, level_event: asyncio.Event, logging_state: SharedState[bool]=SharedState(False), rel_duty_directory="\\pumps\\flowrates", base_duty=92, **kwargs) -> None:
        super().__init__()
        self.__input_state = level_state
        self.__serial_interface = serial_interface
        self.__logging = logging_state.value
        self.__logging_state = logging_state
        self.__rel_duty_directory = rel_duty_directory
        self.__datafile: str|None = None
        self.__base_duty = base_duty
        self.__level_event = level_event
        self.__pid: PID|None = None

    async def _setup(self):
        # if self.__LOGGING:
        #     timestamp = datetime.datetime.now().strftime("%m-%d-%Y %H-%M-%S")
        #     self.__datafile = ('{}{}.csv').format(self.__rel_duty_directory,timestamp)

        #     with open(self.__datafile, "a", newline='') as f:
        #         writer = csv.writer(f, delimiter=",")
        #         writer.writerow(['Time (seconds since epoch)', 'Flow Rate A','Flow Rate B'])
        #         f.close()
        #TODO verify that changing the min output to 0 will not change bevaviour
        self.__pid = PID(Kp=-100, Ki=-0.005, Kd=0.0, setpoint=0, sample_time=None, 
        output_limits=(-(255-self.__base_duty), 255-self.__base_duty), auto_mode=True, proportional_on_measurement=False, error_map=None)
        #TODO why on earth is this next bit necessary?
        self.__pid.set_auto_mode(False)
        await asyncio.sleep(3)
        self.__pid.set_auto_mode(True, last_output=-.28)

    async def _loop(self) -> Duties|None:
        # The following block continuously checks for either:
        # - The level event to be set, indicating that new level data is available
        #       The event is cleared after the block to allow the process to be repeated again
        # - The generator to be shut down.
        #       The generate() only checks the stop event after _loop returns.
        #       If the level sensor is shut down, this class has no way of knowing until _loop returns, so it will deadlock on the await line
        #       This block with an await timeout therefore allows the code to avoid this scenario and return early
        while self.can_generate():
            try:
                await asyncio.wait_for(self.__level_event.wait(),timeout = PID_DATA_TIMEOUT)
                break
            except TimeoutError:
                pass
        if not self.can_generate():
            return
        self.__level_event.clear()


        # update the state of the datalogger

        new_log_state = self.__logging_state.get_value()
        if new_log_state is not None:
            self.__logging = new_log_state

        try:
            level_buffer = self.__input_state.get_value()
            if level_buffer is not None:
                # There is new data! Read it from the level generator queue
 
                last_readings = level_buffer.read()

                # Calculate the average of the lbuffer readings
                error = 0 - np.mean(last_readings)
                
                # Perform the PID control (rounded as duty is an integer)
                control = round(self.__pid(error))

                # Assign new duties
                if (control > 0): 
                    flowRateA = self.__base_duty + control
                    flowRateB = self.__base_duty
                    
                else:
                    flowRateA = self.__base_duty
                    flowRateB = self.__base_duty - control

                # Write the new flow rates to the serial device
                await self.__serial_interface.write(GenericInterface.format_duty(PumpNames.A,flowRateA))
                await self.__serial_interface.write(GenericInterface.format_duty(PumpNames.B,flowRateB))

                # Optionally, save the new duties in the data file as a new line
                if self.__logging:
                    # print(flowRateA, flowRateB)
                    data = [datetime.datetime.now().strftime("%m-%d-%Y %H:%M:%S"), flowRateA, flowRateB]
                    if self.__datafile is None:
                        timestamp = datetime.datetime.now().strftime("%m-%d-%Y %H-%M-%S")
                        self.__datafile = ('{}{}.csv').format(self.__rel_duty_directory,timestamp)
                        with open(self.__datafile, "a", newline='') as f:
                            writer = csv.writer(f, delimiter=",")
                            writer.writerow(['Time (seconds since epoch)', 'Flow Rate A','Flow Rate B'])
                            writer.writerow(data)
                    else:
                        with open(self.__datafile, "a", newline='') as f:
                            writer = csv.writer(f, delimiter=",")
                            writer.writerow(data)
                
                return (flowRateA,flowRateB)
        except IOError as e:
            print("Error saving flowrates to file")
            print(e)
        return None

    def teardown(self):
        self.__datafile = None



# In[4]:
# def apply_pid(cond: threading.Condition, PIDevent: threading.Event, buffer: Buffer[list[float]],serial_interface: GenericInterface,LOGGING=True,rel_duty_directory="\\pumps\\flowrates",time_window=18*60,level_period=5,**kwargs):

#     N = time_window/level_period
#     buffer.set_N(N)

#     PIDevent.clear()
#     serial_loop = asyncio.new_event_loop()
#     executors = concurrent.futures.ThreadPoolExecutor(max_workers=3)

    # Define function to retrieve the last n lines from a file

    # time_window = 18 # minutes - levelsensor logs data every 5 seconds, using this a priori

    # def get_last_n_lines(file_name, N):
    #     # Create an empty list to keep the track of last N lines
    #     list_of_lines = []
    #     # Open file for reading in binary mode
    #     with open(file_name, 'rb') as read_obj:
    #         # Move the cursor to the end of the file
    #         read_obj.seek(0, os.SEEK_END)
    #         # Create a buffer to keep the last read line
    #         buffer = bytearray()
    #         # Get the current position of pointer i.e eof
    #         pointer_location = read_obj.tell()
    #         # Loop till pointer reaches the top of the file
    #         while pointer_location >= 0:
    #             # Move the file pointer to the location pointed by pointer_location
    #             read_obj.seek(pointer_location)
    #             # Shift pointer location by -1
    #             pointer_location = pointer_location -1
    #             # read that byte / character
    #             new_byte = read_obj.read(1)
    #             # If the read byte is new line character then it means one line is read
    #             if new_byte == b'\n':
    #                 # Save the line in list of lines
    #                 list_of_lines.append(buffer.decode()[::-1])
    #                 # If the size of list reaches N, then return the reversed list
    #                 if len(list_of_lines) == N:
    #                     return list(reversed(list_of_lines))
    #                 # Reinitialize the byte array to save next line
    #                 buffer = bytearray()
    #             else:
    #                 # If last read character is not eol then add it in buffer
    #                 buffer.extend(new_byte)
    #         # As file is read completely, if there is still data in buffer, then its first line.
    #         if len(buffer) > 0:
    #             list_of_lines.append(buffer.decode()[::-1])
    #     # return the reversed list
    #     return list(reversed(list_of_lines))



    # # In[5]:


    # # Define the relative path to the pump data directory from the user's home directory
    # relative_pump_dir = 'Rohit_scripts/rfb-volume-balancing/pumps/levels/*.csv'

    # # Get the absolute path by expanding the user's home directory and adding the relative path
    # pump_dir = os.path.expanduser(os.path.join('~', relative_pump_dir))

    # print(pump_dir)

    # # Initialize level_file to None
    # level_file = None

    # # Iterate through the files that match the pump data pattern and find the most recent file
    # most_recent = 0
    # for f in glob.iglob(pump_dir):
    #     last_updated = os.path.getmtime(f)
    #     if last_updated > most_recent:
    #         most_recent = last_updated
    #         level_file = f

    # # Now you have the most recently modified file stored in level_file
    # print("Most recent file:", level_file)


    # In[6]:

    # if LOGGING:
    #     timestamp = datetime.datetime.now().strftime("%m-%d-%Y %H-%M-%S")
    #     datafile = ('{}{}.csv').format(rel_duty_directory,timestamp)

    #     with open(datafile, "a", newline='') as f:
    #         writer = csv.writer(f, delimiter=",")
    #         writer.writerow(['Time (seconds since epoch)', 'Flow Rate A','Flow Rate B'])
    #         f.close()

    # Initialise flowrate

    # flowRate = 92 # Duty cycle for 20mL/min


    # Set up PID function and settings for it (read on what Kirk's code used)
    # Gains to be (or have been?) determined by trial and error.
    # If controller drives pumps in wrong direction, change sign of all gains (or change sign on level sensor)

    # pid = PID(Kp=-100, Ki=-0.005, Kd=0.0, setpoint=0, sample_time=None, 
    #     output_limits=(-(255-flowRate), 255-flowRate), auto_mode=True, proportional_on_measurement=False, error_map=None)
    # pid.set_auto_mode(False)
    # start = time.time()
    # while time.time() < start + 3:
    #     pass
    # pid.set_auto_mode(True, last_output=-.28)


    # In[7]:


    # Get most recent average imbalance from level_file (could do this calculation in levelsensor code?)

    # updateTimer = time.perf_counter()
    # while not PIDevent.is_set():
        # try:
        #     cond.acquire()
        #     # this thread now holds the right to the buffer

        #     last_readings = buffer.read()
        #     error = 0 - np.mean(last_readings)

        #     control = round(pid(error))

        #     if (control > 0): 
        #         flowRateA = flowRate + control
        #         flowRateB = flowRate
                
        #     else:
        #         flowRateA = flowRate
        #         flowRateB = flowRate - control

        #     serial_loop.run_in_executor(executors,serial_interface.write('<a,{}>'.format(flowRateA)))
        #     serial_loop.run_in_executor(executors,serial_interface.write('<b,{}>'.format(flowRateB)))
            
        #     if LOGGING:
        #             print(flowRateA, flowRateB)
        #             data = [datetime.datetime.now().strftime("%m-%d-%Y %H:%M:%S"), flowRateA, flowRateB]
        #             logTimer = time.perf_counter()
        #             with open(datafile, "a", newline='') as f:
        #                 writer = csv.writer(f, delimiter=",")
        #                 writer.writerow(data)
        #                 f.close()

        #     # Now we release the buffer for the level sensor thread to use
        #     # This will also pause this thread until the level sensor calls notify().
        #     # For safety, we check if the event set happens at intermediate times so we can terminate early if needed
        #     while not PIDevent.is_set():
        #         if cond.wait(timeout=1.0):
        #             break
        #     if PIDevent.is_set():
        #         break


        # except IOError as e:
        #     print("Error saving flowrates")
        #     print(e)
            
        # finally:
        #     # in the case of an unforseen error, make sure the lock is released to avoid deadlocking
        #     cond.release()


 # -------------------- KIRK OLD CODE -------------------------------

        # if(time.perf_counter()-updateTimer > 5):

        #     try:
        #         # # Loads the data from it's format as a text file
        #         # last_readings = np.genfromtxt(get_last_n_lines(level_file,time_window*60/5),delimiter=',')
                
        #         # last_readings = last_readings[~np.isnan(last_readings).any(axis=1), :]
        #         # #print(last_readings)   #use this to check data with excel file, 3 columns wrong but we only need last which is fine
        #         # v = last_readings[:,3]
        #         # #print("Average difference data:", v)
                
        #         # # Calculate average error with setpoint being 0
        #         # error = 0 - np.mean(v)
        #         # #print("Average error:", error)
                
                
        #     except Exception as e:
        #         print("Error:", e)
        #         pass
            
        #         # Compute new output from the PID according to the systems current value
            
        #     control = pid(error)
        #     control = round(control)
        #     #print("Control:", control)
        #     #print("PID Components", pid.components)
            
        #     if (control > 0): 
        #         flowRateA = flowRate + control
        #         flowRateB = flowRate
                
        #     else:
        #         flowRateA = flowRate
        #         flowRateB = flowRate - control
        #     try:
        #         if LOGGING:
        #             print(flowRateA, flowRateB)
        #             data = [timestamp, flowRateA, flowRateB]
        #             logTimer = time.perf_counter()
        #             with open(datafile, "a", newline='') as f:
        #                 writer = csv.writer(f, delimiter=",")
        #                 writer.writerow(data)
        #                 f.close()
        #         # uo("http://localhost:8000/"+"write/"+'<a,{}>'.format(flowRateA))
        #         # uo("http://localhost:8000/"+"write/"+'<b,{}>'.format(flowRateB))
        #     except Exception as e:
        #         print(e.__class__.__name__)
                

        
        #     updateTimer = time.perf_counter()
