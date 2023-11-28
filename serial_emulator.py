import serial
import time
import threading
import atexit



def send_periodically(ser: serial.Serial):
    while True:
        time.sleep(1)
        # Assuming the latest data is stored in a variable `latest_data`
        with lock:
            to_write = ",".join(latest_data)+"\n"
            ser.write(to_write.encode())
            print(to_write)

# Open the serial port
ser = serial.Serial('COM2', 9600)  # Replace 'COMx' with your COM port
atexit.register(ser.close)
ports = "abcdef"
lock = threading.Lock()
latest_data = ["1"]*6

# Start the periodic sending in a separate thread
threading.Thread(target=send_periodically, args=(ser,),daemon=True).start()

# Main loop to read data
while True:
    currentbytes = bytearray()
    store_bytes = False
    while ser.in_waiting:
        nextbyte = ser.read()
        if len(nextbyte) == 0:
            break
        elif nextbyte == b"<":
            store_bytes = True
        elif nextbyte == b">":
            store_bytes = False
            ## PERFORM THE COMMAND
            with lock:
                command = currentbytes.decode().split(",")
                index = ports.find(command[0])
                if index != -1 : 
                    latest_data[index] = command[1]
                    print(f"Writing: {command[0]},{command[1]}")
            currentbytes=bytearray()
        elif store_bytes:
            currentbytes += nextbyte
    time.sleep(0.5)