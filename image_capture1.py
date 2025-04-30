import cv2
import os
from datetime import datetime
import serial
import time
import numpy as np

# Configuration
PERSON_NAME = "test"
SERIAL_PORT = "COM5"
BAUD_RATE = 921600
IMAGE_START_MARKER = b"IMAGE_START:"
IMAGE_END_MARKER = b"IMAGE_END"


def create_folder(name):
    dataset_folder = "dataset"
    if not os.path.exists(dataset_folder):
        os.makedirs(dataset_folder)

    person_folder = os.path.join(dataset_folder, name)
    if not os.path.exists(person_folder):
        os.makedirs(person_folder)
    return person_folder


def read_image_from_serial(ser):
    """Reads a complete image from the serial stream"""
    # Wait for the start marker
    while True:
        line = ser.readline()
        if IMAGE_START_MARKER in line:
            try:
                # Extract image size from the start marker
                size_str = line.decode('utf-8').split(':')[1].strip()
                image_size = int(size_str)
                break
            except (IndexError, ValueError):
                continue

    # Read the image data
    image_data = ser.read(image_size)

    # Read until we find the end marker (discarding any extra bytes)
    while True:
        line = ser.readline()
        if IMAGE_END_MARKER in line:
            break

    return image_data


def capture_photos(name):
    folder = create_folder(name)

    # Initialize serial connection
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        print(f"Connected to {SERIAL_PORT} at {BAUD_RATE} baud")
    except serial.SerialException as e:
        print(f"Failed to connect to {SERIAL_PORT}: {e}")
        return

    # Allow some time for camera initialization
    time.sleep(2)

    photo_count = 0
    print(f"Taking photos for {name}. Press SPACE to capture, 'q' to quit.")

    cv2.namedWindow('Live Preview - Press SPACE to Capture', cv2.WINDOW_NORMAL)

    try:
        while True:
            # Get image from serial
            image_data = read_image_from_serial(ser)

            # Convert to OpenCV format
            nparr = np.frombuffer(image_data, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if frame is not None:
                # Display the live preview
                cv2.imshow('Live Preview - Press SPACE to Capture', frame)

                key = cv2.waitKey(1) & 0xFF

                if key == ord(' '):  # Space key to capture
                    photo_count += 1
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"{name}_{timestamp}.jpg"
                    filepath = os.path.join(folder, filename)
                    cv2.imwrite(filepath, frame)
                    print(f"Photo {photo_count} saved: {filepath}")

                    # Show confirmation on the preview window
                    confirmation_frame = frame.copy()
                    cv2.putText(confirmation_frame, f"SAVED: {filename}", (10, 30),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                    cv2.imshow('Live Preview - Press SPACE to Capture', confirmation_frame)
                    cv2.waitKey(500)  # Show confirmation for 500ms

                elif key == ord('q'):  # Q key to quit
                    break
    except Exception as e:
        print(f"Error during capture: {e}")
    finally:
        # Clean up
        cv2.destroyAllWindows()
        ser.close()
        print(f"Photo capture completed. {photo_count} photos saved for {name}.")


if __name__ == "__main__":
    capture_photos(PERSON_NAME)