import serial.tools.list_ports
from serial import Serial
import time
import csv
import serial

class SerialInterface:

    port_list = []

    def __init__(self):
        pass

    @staticmethod
    def get_ports():
        ports = serial.tools.list_ports.comports()
        serialInst = serial.Serial