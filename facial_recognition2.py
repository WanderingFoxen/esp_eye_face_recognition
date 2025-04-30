import face_recognition
import cv2
import numpy as np
import time
import pickle
import serial
import io
import pyttsx3    # Import pyttsx3

# --- Configuration ---
SERIAL_PORT = 'COM5'       # Change this to your ESP-EYE's serial port
BAUD_RATE = 921600         # Matches the BAUD_RATE in your ESP32 code
# --- Markers expected from your ESP32 code ---
START_STRING = b'IMAGE_START:'
END_STRING = b'IMAGE_END\r\n' # Assuming Serial.println sends CR+LF (\r\n)
CV_SCALER = 4              # Scaling factor for face detection to improve performance

# --- Speaking Configuration ---
SPEAK_REST_PERIOD_SECONDS = 5 # Time in seconds to wait before speaking the same name again
last_spoken_time = {} # Dictionary to track when each name was last spoken {name: timestamp}
tts_engine = None # Variable to hold the pyttsx3 engine instance

# --- Load pre-trained face encodings ---
print("[INFO] loading encodings...")
try:
    with open("encodings.pickle", "rb") as f:
        data = pickle.loads(f.read())
    known_face_encodings = data["encodings"]
    known_face_names = data["names"]
    print(f"[INFO] loaded {len(known_face_names)} known faces.")
except FileNotFoundError:
    print("[ERROR] encodings.pickle not found. Please run encode_faces.py first.")
    exit()
except Exception as e:
    print(f"[ERROR] failed to load encodings: {e}")
    exit()

# --- Initialize Serial Communication ---
print(f"[INFO] Opening serial port {SERIAL_PORT} at {BAUD_RATE}...")
try:
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.5) # Timeout is important
    print("[INFO] Serial port opened successfully.")
except serial.SerialException as e:
    print(f"[ERROR] Could not open serial port {SERIAL_PORT}: {e}")
    print("Please check port name, baud rate, and if the device is connected.")
    print("Also ensure no other program (like Serial Monitor) is using the port.")
    exit()

# --- Initialize TTS Engine ---
print("[INFO] Initializing TTS engine...")
try:
    tts_engine = pyttsx3.init()
    # Optional: Configure voice, speed, etc.
    # Example: Get available voices and set one (voice IDs are system-dependent)
    # voices = tts_engine.getVoices()
    # for voice in voices:
    #     print(f"Voice: {voice.name}, ID: {voice.id}")
    # tts_engine.setProperty('voice', voices[0].id) # Set the first voice found
    tts_engine.setProperty('rate', 180) # Adjust speaking rate (words per minute)
    # tts_engine.setProperty('volume', 1.0) # Adjust volume (0.0 to 1.0)

    print("[INFO] TTS engine initialized.")
except Exception as e:
    print(f"[ERROR] Failed to initialize TTS engine: {e}")
    print("[ERROR] Text-to-Speech will be disabled.")
    tts_engine = None # Ensure tts_engine is None if initialization fails


# --- Variables for processing and display ---
face_locations = []
face_encodings = []
face_names = [] # Will hold names detected in the *current* frame
frame_count = 0
start_time = time.time()
fps = 0
byte_buffer = b'' # Buffer to store incoming serial bytes

# --- Functions (operate on OpenCV frames) ---

def process_frame(frame):
    """Processes a single frame to find faces and their encodings."""
    global face_locations, face_encodings, face_names # face_names is updated here

    if frame is None:
        face_locations = [] # Clear data if frame is None
        face_encodings = []
        face_names = []
        return None # Cannot process a None frame

    try:
        # Calculate new dimensions. Need to be integers.
        # Ensure dimensions are positive before resizing
        new_width = int(frame.shape[1] / CV_SCALER)
        new_height = int(frame.shape[0] / CV_SCALER)

        if new_width <= 0 or new_height <= 0:
             # print(f"[WARNING] Calculated scaled dimensions are non-positive: {new_width}x{new_height}. Skipping face detection for this frame.")
             # Clear previous face data as we didn't process this frame
             face_locations = []
             face_encodings = []
             face_names = []
             return frame # Return original frame

        # Resize the frame for faster face detection
        resized_frame = cv2.resize(frame, (new_width, new_height))

        # Convert BGR (OpenCV default) to RGB (face_recognition library)
        rgb_resized_frame = cv2.cvtColor(resized_frame, cv2.COLOR_BGR2RGB)

        face_locations = face_recognition.face_locations(rgb_resized_frame)
        face_encodings = face_recognition.face_encodings(rgb_resized_frame, face_locations, model='large')

        face_names = [] # Clear names from previous frame
        for face_encoding in face_encodings:
            matches = face_recognition.compare_faces(known_face_encodings, face_encoding)
            name = "Unknown"

            # Use the known face with the smallest distance
            face_distances = face_recognition.face_distance(known_face_encodings, face_encoding)

            best_match_index = -1
            min_distance = float('inf')

            for i, match in enumerate(matches):
                if match and face_distances[i] < min_distance:
                     min_distance = face_distances[i]
                     best_match_index = i

            if best_match_index != -1:
                 name = known_face_names[best_match_index]

            face_names.append(name) # Add name for the current face

        return frame # Return the original frame for drawing

    except Exception as e:
        print(f"[ERROR] Error during frame processing: {e}")
        # Clear face data on error
        face_locations = []
        face_encodings = []
        face_names = []
        return frame # Attempt to return original frame


def draw_results(frame):
    """Draws rectangles and names on the frame."""
    if frame is None:
        return None

    # Display the results
    for (top, right, bottom, left), name in zip(face_locations, face_names):
        # Scale back up face locations since detection was done on a scaled frame
        # Ensure scaling results in integers
        top = int(top * CV_SCALER)
        right = int(right * CV_SCALER)
        bottom = int(bottom * CV_SCALER)
        left = int(left * CV_SCALER)

        # Draw a box around the face
        color = (0, 255, 0) if name != "Unknown" else (244, 42, 3) # Green for known, Red/Orange for unknown
        cv2.rectangle(frame, (left, top), (right, bottom), color, 3)

        # Draw a label with a name
        text_y_offset = 35
        cv2.rectangle(frame, (left - 3, top - text_y_offset), (right + 3, top), color, cv2.FILLED)
        font = cv2.FONT_HERSHEY_DUPLEX
        cv2.putText(frame, name, (left + 6, top - 6), font, 1.0, (255, 255, 255), 1) # White color

    return frame

def calculate_fps():
    """Calculates and returns the current frames per second."""
    global frame_count, start_time, fps
    frame_count += 1
    elapsed_time = time.time() - start_time
    if elapsed_time >= 1: # Calculate FPS roughly every second
        fps = frame_count / elapsed_time
        frame_count = 0
        start_time = time.time()
    return fps

# --- Function to speak a name ---
def speak_name(name):
    """Speaks the given name using pyttsx3."""
    global last_spoken_time, tts_engine

    if tts_engine is None:
        # TTS engine failed to initialize, cannot speak
        return

    current_time = time.time()

    # Check if this name is known and if the rest period has passed
    if name != "Unknown" and (name not in last_spoken_time or current_time - last_spoken_time[name] >= SPEAK_REST_PERIOD_SECONDS):
        print(f"[SPEAKING] {name}")
        try:
            # Queue the name to be spoken. pyttsx3.say() is usually non-blocking.
            # The actual speaking happens in the engine's own event loop.
            tts_engine.say(name)
            # Process the queued speech events. This can sometimes block briefly.
            # For short phrases, this might be acceptable. For longer speech,
            # consider running the engine in a separate thread if it blocks too much.
            tts_engine.runAndWait() # Added runAndWait() to ensure speech is processed

            last_spoken_time[name] = current_time # Update the last spoken time

        except Exception as e:
            print(f"[ERROR] Error queuing or running speech with pyttsx3: {e}")


# --- Main Loop ---
print("[INFO] Starting video stream processing...")

while True:
    try:
        # Read bytes from the serial port into the buffer
        if ser.in_waiting > 0:
            byte_buffer += ser.read(ser.in_waiting)

        # --- Search and decode a single frame from buffer ---
        frame = None # Initialize frame variable for the current iteration

        # Look for the start marker "IMAGE_START:"
        start_index = byte_buffer.find(START_STRING)

        if start_index != -1:
            # Found start, now look for the newline immediately after the length
            newline_index = byte_buffer.find(b'\n', start_index + len(START_STRING))

            if newline_index != -1:
                # Found the newline after the length string
                length_string_bytes = byte_buffer[start_index + len(START_STRING) : newline_index]

                try:
                    # Convert the length string bytes to an integer
                    jpeg_length = int(length_string_bytes.decode('ascii'))

                    # Calculate the expected start and end positions of the raw JPEG data
                    jpeg_data_start_index = newline_index + 1
                    jpeg_data_end_index = jpeg_data_start_index + jpeg_length

                    # Check if the buffer contains enough data for the JPEG image
                    if len(byte_buffer) >= jpeg_data_end_index:

                         # Now check for the END_STRING marker *immediately* after the expected end of JPEG data
                         actual_end_string_start_index = byte_buffer.find(END_STRING, jpeg_data_end_index)

                         if actual_end_string_start_index != -1 and actual_end_string_start_index == jpeg_data_end_index:
                             # Found a complete frame block (START, Length, JPEG data, END)

                             # Extract the raw JPEG data
                             jpeg_data = byte_buffer[jpeg_data_start_index : jpeg_data_end_index]

                             # --- Remove the processed block from the buffer ---
                             buffer_clear_index = actual_end_string_start_index + len(END_STRING)
                             byte_buffer = byte_buffer[buffer_clear_index:]

                             # --- Decode the JPEG data ---
                             try:
                                 nparr = np.frombuffer(jpeg_data, np.uint8)
                                 frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                                 if frame is None:
                                     print("[WARNING] cv2.imdecode returned None - potentially corrupted JPEG data.")

                             except Exception as e:
                                 print(f"[ERROR] Error decoding JPEG data: {e}")


                             # --- Process the frame if successfully decoded ---
                             if frame is not None:
                                 # Call your existing processing function
                                 # This updates the global face_names list
                                 processed_frame = process_frame(frame)

                                 if processed_frame is not None:

                                     # --- Speak detected names (after processing) ---
                                     # Create a set of unique recognized names in this frame
                                     current_recognized_names = set(name for name in face_names if name != "Unknown")

                                     # Iterate through unique names and potentially speak them
                                     for name in current_recognized_names:
                                         speak_name(name) # Call the new speak function

                                     # --- Draw results and display ---
                                     display_frame = draw_results(processed_frame)

                                     if display_frame is not None:
                                         # Calculate and update FPS
                                         current_fps = calculate_fps()

                                         # Attach FPS counter
                                         cv2.putText(display_frame, f"FPS: {current_fps:.1f}", (display_frame.shape[1] - 150, 30),
                                                     cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2) # Green color

                                         # Display the frame
                                         cv2.imshow('ESP-EYE Video Feed (COM5)', display_frame)

                                 # else: print warning handled in process_frame check
                             # else: print warning handled in frame decode check


                         # else: If start and length found, but not the full jpeg_data+END_STRING,
                         # we just wait for more data in the next loop iteration.

                    # else: If start, length string, and newline found, but buffer doesn't have
                    # enough bytes for the full jpeg_length, wait for more data.

                except ValueError:
                    # This happens if the bytes between START_STRING and \n are not a valid integer string
                    print(f"[WARNING] Could not parse JPEG length from buffer: {length_string_bytes}. Clearing buffer to resync.")
                    byte_buffer = b'' # Clear buffer to try and resync

            # If start found but no newline yet, wait for more data.

        # --- Handle buffer potentially growing too large ---
        if len(byte_buffer) > 1024 * 1024 * 10: # e.g., 10MB limit
             print("[WARNING] Byte buffer growing too large without finding a frame, clearing buffer.")
             byte_buffer = b'' # Clear buffer to try and resync

    except serial.SerialException as e:
        print(f"[ERROR] Serial communication error: {e}")
        break # Exit loop on serial error
    except Exception as e:
        print(f"[ERROR] An unexpected error occurred: {e}")
        break # Exit loop on other errors

    # Break the loop if 'q' is pressed
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

# --- Cleanup ---
print("[INFO] Stopping video stream and cleaning up...")
cv2.destroyAllWindows()
if 'ser' in locals() and ser.isOpen():
    ser.close()
    print("[INFO] Serial port closed.")
if tts_engine:
     try:
         # It's good practice to stop the engine explicitly on exit
         # This might help clean up resources depending on the backend
         tts_engine.stop()
         print("[INFO] TTS engine stopped.")
     except Exception as e:
          print(f"[ERROR] Error stopping TTS engine: {e}")


