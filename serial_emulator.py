import serial
import time
import threading
import atexit



def send_periodically(ser: serial.Serial):
    while True:
        time.sleep(1)
        # Assuming the latest data is stored in a variable `latest_data`
        to_write = ",".join(latest_data)+"\n"
        ser.write(to_write.encode())
        print(to_write)

# Open the serial port
ser = serial.Serial('COM2', 9600)  # Replace 'COMx' with your COM port
atexit.register(ser.close)
ports = "abcdef"
latest_data = ["1"]*6

# Start the periodic sending in a separate thread
threading.Thread(target=send_periodically, args=(ser,),daemon=True).start()

# Main loop to read data
while True:
    if ser.in_waiting > 0:
        new_write = ser.readline().decode().strip("\n").strip("<").strip(">").split(",")
        index = ports.find(latest_data[0])
        if index !=-1:
            latest_data[index]=new_write[1]
        print("Write command received: ",",".join(new_write))  # or log this data
    time.sleep(0.5)