import serial
import csv
import time

PORT = '/dev/cu.usbmodem101'
BAUD = 115200
OUTPUT_FILE = 'counter_test.csv'

def main():
    try:
        ser = serial.Serial(PORT, BAUD, timeout=1)
    except serial.SerialException:
        print(f"Could not open {PORT}")
        return

    time.sleep(2)  # give the board a moment after opening the port
    ser.reset_input_buffer()  # discard any data sitting in the buffer

    with open(OUTPUT_FILE, 'w', newline='') as csv_file: # creates/overwrites new csv file
        writer = csv.writer(csv_file)
        writer.writerow(['timestamp', 'value']) # header row for CSV

        print(f"Logging to {OUTPUT_FILE}. Press Ctrl+C to stop.")
        try:
            while True:
                line = ser.readline().decode('utf-8').strip() # reads line of text from arduino
                if line:
                    timestamp = time.time()
                    writer.writerow([timestamp, line])
                    csv_file.flush() # prevents data being lost
                    print(timestamp, line)
        except KeyboardInterrupt:
            print("\nStopped logging.")
        finally:
            ser.close()

if __name__ == "__main__":
    main()