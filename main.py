import serial
import time
import io
from PIL import Image
import pytesseract  # Import the Tesseract OCR library
import pyttsx3  # Import the pyttsx3 library for text-to-speech
import re # Regular Expression Library
import platform # To check OS

# --- Configuration ---
SERIAL_PORT = 'COM5'  # Or '/dev/ttyUSB0' on Linux/Mac, etc. - Check your Arduino IDE/Device Manager
BAUD_RATE = 921600

# --- !! IMPORTANT !! ---
# Set the correct path to the Tesseract executable on your system.
# Common paths:
# Windows: r'C:\Program Files\Tesseract-OCR\tesseract.exe' (use 'r' prefix for raw string)
# Linux: '/usr/bin/tesseract'
# macOS: '/usr/local/bin/tesseract' (if installed via Homebrew)
# --- VERIFY THIS PATH ---
if platform.system() == "Windows":
    TESSERACT_PATH = r'D:\Program Files\Tesseract-OCR\tesseract.exe'
else:
    # Default for Linux/Mac - adjust if needed
    TESSERACT_PATH = '/usr/bin/tesseract'


def get_serial_connection(port, baudrate, timeout=2):
    """
    Establishes and returns a serial connection. Handles errors and waits.
    """
    try:
        # Ensure port is a string
        port_str = str(port)
        ser = serial.Serial(port_str, baudrate, timeout=timeout)
        print(f"Connected to {port_str} at {baudrate} bps")
        # Add a longer delay to ensure ESP32 is ready after potential reset
        time.sleep(3)
        # Clear any potential leftover data in the input buffer
        ser.reset_input_buffer()
        print("Input buffer cleared.")
        return ser
    except serial.SerialException as e:
        print(f"Error opening serial port {port}: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred during connection: {e}")
        return None

def receive_image_from_serial(ser, timeout=10):
    """
    Receives an image from the serial port, reads size from header.
    Handles start/end markers and timeouts robustly.
    Returns the raw image bytes or None on error.
    """
    if not ser or not ser.is_open:
        print("Serial port not available or not open.")
        return None

    # Set read timeout specifically for this operation
    ser.timeout = timeout

    image_data = None
    image_size = 0

    try:
        # 1. Find the start marker and read the size
        print("Waiting for IMAGE_START header...")
        while True:
            line_bytes = ser.readline()
            if not line_bytes: # Timeout occurred
                print("Timeout waiting for IMAGE_START header.")
                return None
            try:
                line = line_bytes.decode('utf-8').strip()
                print(f"Received line: {line}") # Debug print
                if line.startswith("IMAGE_START:"):
                    try:
                        image_size = int(line.split(':')[1])
                        print(f"Expecting image of size: {image_size} bytes")
                        if image_size <= 0:
                            print("Error: Invalid image size received.")
                            return None
                        break # Found header, exit loop
                    except (IndexError, ValueError):
                        print("Error: Could not parse image size from header.")
                        # Continue reading lines until a valid header or timeout
                elif "Capturing image..." in line or "Image sent" in line:
                    # Ignore common status messages from ESP32 while waiting for header
                    print("Ignoring status message from ESP32.")
                    continue
                elif not line:
                    # Ignore empty lines
                    continue
                else:
                    # Unexpected line before header
                    print(f"Unexpected line while waiting for header: {line}")
                    # Decide if you want to return None or keep waiting
                    # return None # Option: Fail if unexpected data received

            except UnicodeDecodeError:
                print(f"Warning: Could not decode bytes: {line_bytes}")
                continue # Ignore undecodable lines

        # 2. Read the image data
        print(f"Reading {image_size} bytes of image data...")
        image_data = ser.read(image_size)

        if len(image_data) != image_size:
            print(f"Error: Received {len(image_data)} bytes, expected {image_size}")
            # Attempt to clear buffer to help resync
            ser.reset_input_buffer()
            return None
        print(f"Successfully read {len(image_data)} bytes.")

        # 3. Robustly read until IMAGE_END or timeout
        print("Waiting for IMAGE_END marker...")
        end_marker_found = False
        # Use a shorter timeout for finding the end marker
        original_timeout = ser.timeout
        ser.timeout = 2 # Shorter timeout (e.g., 2 seconds)
        while True:
            line_bytes = ser.readline()
            if not line_bytes: # Timeout occurred
                print("Warning: Timeout waiting for IMAGE_END marker.")
                break
            try:
                line = line_bytes.decode('utf-8').strip()
                print(f"Received line after image data: {line}") # Debug print
                if line == "IMAGE_END":
                    print("Received IMAGE_END marker.")
                    end_marker_found = True
                    break
                elif not line:
                    # Ignore empty lines after image data
                    continue
                else:
                    # Ignore other potential lines sent by ESP32 after image
                    print(f"Ignoring line after image data: {line}")

            except UnicodeDecodeError:
                 print(f"Warning: Could not decode bytes after image data: {line_bytes}")
                 continue # Ignore undecodable lines

        ser.timeout = original_timeout # Restore original timeout

        if not end_marker_found:
             print("Warning: Did not receive IMAGE_END marker before timeout.")

        return image_data # Return the raw JPEG bytes even if end marker wasn't found cleanly

    except serial.SerialException as e:
        print(f"Serial error during communication: {e}")
        return None
    except Exception as e:
        print(f"An error occurred receiving image data: {e}")
        return None
    finally:
        # Reset timeout for general reading outside this function if needed
        if ser and ser.is_open:
            ser.timeout = 2 # Reset to a default reasonable timeout


def extract_text_from_image(image_bytes, tesseract_cmd=TESSERACT_PATH):
    """
    Extracts text from an image using Tesseract OCR.
    Flips the image horizontally if text appears mirrored.
    Displays the (flipped) image before OCR.

    Args:
        image_bytes: Raw bytes of the image (e.g., JPEG).
        tesseract_cmd: Path to the Tesseract OCR executable.

    Returns:
        The extracted text as a string, or None on error.
    """
    if not image_bytes:
        print("Error: No image data provided for OCR.")
        return None
    try:
        # 1. Set tesseract cmd
        print(f"Using Tesseract executable at: {tesseract_cmd}")
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

        # 2. Open the image using PIL
        image = Image.open(io.BytesIO(image_bytes))
        print(f"Image opened successfully for OCR ({image.format}, {image.size}, {image.mode})")

        # 3. Flip the image horizontally (if needed for mirroring)
        print("Flipping image horizontally...")
        image = image.transpose(Image.FLIP_LEFT_RIGHT)

        # --- ADDED: Display the image ---
        try:
            print("Displaying the captured (and flipped) image...")
            image.show() # Opens in default system image viewer
        except Exception as display_e:
            print(f"Warning: Could not display image automatically: {display_e}")
        # --------------------------------

        # 4. Perform OCR using pytesseract
        print("Performing OCR on flipped image...")
        text = pytesseract.image_to_string(image)
        print("OCR completed.")
        return text.strip()  # Remove leading/trailing whitespace

    except FileNotFoundError:
        print(f"FATAL ERROR: Tesseract executable not found at '{tesseract_cmd}'.")
        print("Please ensure Tesseract OCR is installed correctly and the TESSERACT_PATH variable in the script is set to the correct location of 'tesseract.exe' (Windows) or 'tesseract' (Linux/Mac).")
        return None
    except pytesseract.TesseractNotFoundError: # More specific error
        print(f"FATAL ERROR: Tesseract not found or not accessible at '{tesseract_cmd}'.")
        print("Please ensure Tesseract OCR is installed correctly and the TESSERACT_PATH variable is correct.")
        return None
    except Exception as e:
        print(f"Error during OCR processing: {e}")
        # Optionally save the image that caused the error for debugging
        # try:
        #     with open("ocr_error_image.jpg", "wb") as f:
        #         f.write(image_bytes)
        #     print("Image causing OCR error saved as ocr_error_image.jpg")
        # except Exception as save_e:
        #     print(f"Could not save error image: {save_e}")
        return None


def speak_text(text, rate=150):
    """
    Speaks the given text using a text-to-speech engine (pyttsx3).

    Args:
        text: The text to speak.
        rate: The speaking rate (words per minute).
    """
    if not text:
        print("No text provided to speak.")
        return
    try:
        # 1. Initialize the TTS engine
        engine = pyttsx3.init()
        if not engine:
            print("Error: Could not initialize TTS engine.")
            # Attempt to find the driver manually if needed (less common)
            # try:
            #     engine = pyttsx3.init(driverName='sapi5') # For Windows
            #     # engine = pyttsx3.init(driverName='nsss') # For Mac
            #     # engine = pyttsx3.init(driverName='espeak') # For Linux
            # except Exception as init_e:
            #      print(f"Could not initialize specific TTS driver: {init_e}")
            #      return
            return

        # 2. Set the speaking rate
        engine.setProperty('rate', rate)  # Adjust as needed

        # 3. Get available voices and potentially set one (optional)
        # voices = engine.getProperty('voices')
        # for voice in voices:
        #    print(f"Voice: {voice.name}, ID: {voice.id}")
        # engine.setProperty('voice', voices[0].id) # Example: Set the first voice

        # 4. Speak the text
        print(f"Speaking: {text}")
        engine.say(text)
        engine.runAndWait()  # Block until speaking is done
        print("Speaking finished.")
        # Clean up engine resources if issues persist
        # engine.stop()
        # del engine

    except Exception as e:
        print(f"Error during text-to-speech: {e}")


def clean_text(text):
    """
    Cleans the extracted text, removing unwanted characters and normalizing spacing.
    Args:
        text: A string
    Returns:
        A cleaned string
    """
    if not text:
        return ""
    # Remove non-alphanumeric characters except spaces, newlines, and some punctuation
    # Keep common punctuation like .,?!'-
    text = re.sub(r"[^a-zA-Z0-9\s\n.,?!'-]", '', text)
    # Normalize spaces (replace multiple spaces/newlines with single spaces)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def main():
    """
    Main function to coordinate the image capture, OCR, and TTS processes.
    """
    # 1. Establish Serial Connection
    ser = get_serial_connection(SERIAL_PORT, BAUD_RATE)
    if not ser:
        print("Failed to establish serial connection. Exiting.")
        return

    # 2. Main Loop
    try:
        while True:
            cmd = input("Press Enter to capture image and speak, or 'q' to quit: ")
            if cmd.lower() == 'q':
                break

            # 3. Send capture command
            print("\n--- Requesting New Image ---")
            try:
                # Ensure serial port is open before writing
                if not ser.is_open:
                    print("Serial port is not open. Attempting to reconnect...")
                    ser.close() # Close just in case
                    ser = get_serial_connection(SERIAL_PORT, BAUD_RATE)
                    if not ser:
                        print("Reconnection failed. Exiting.")
                        break # Exit loop if reconnection fails
                    # Continue to next iteration after successful reconnect
                    # continue

                # Clear input buffer before sending command to discard old data
                ser.reset_input_buffer()
                print("Sending 'capture' command to ESP32...")
                ser.write(b'capture\n')
                ser.flush() # Ensure command is sent
                print("Command sent.")

            except serial.SerialException as e:
                 print(f"Serial error sending command: {e}. Attempting to continue...")
                 # Optionally try to reconnect here or just continue
                 continue
            except Exception as e:
                 print(f"Error sending command: {e}")
                 continue # Skip to next iteration

            # 4. Receive image
            image_data = receive_image_from_serial(ser)
            if image_data is None:
                print("Failed to receive image data properly. Please check ESP32 status and connection.")
                # Optional: Add a delay before next attempt
                # time.sleep(1)
                continue  # Go back to the beginning of the loop

            # 5. Extract text from the image (this function now also displays the image)
            text = extract_text_from_image(image_data)
            if text is None:
                print("Failed to extract text from image. Image might be blurry, empty, or Tesseract configuration is wrong.")
                continue  # Go back to the beginning of the loop

            # 6. Clean the extracted text
            cleaned_text = clean_text(text)
            if not cleaned_text:
                 print("No text found in the image after cleaning.")
            else:
                 print("--- Extracted Text ---")
                 print(cleaned_text)
                 print("----------------------")

                 # 7. Speak the text
                 speak_text(cleaned_text)

    except KeyboardInterrupt:
        print("\nProgram interrupted by user.")
    except Exception as e:
        print(f"An unexpected error occurred in the main loop: {e}")
    finally:
        if ser and ser.is_open:
            ser.close()
            print("Serial port closed.")


if __name__ == "__main__":
    main()