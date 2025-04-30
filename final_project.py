import subprocess
import time
import keyboard
import sys
import os # Import os module for checking process status

# Define the names of the files to run
FILE_1 = "main.py"
FILE_2 = "facial_recognition2.py"

# Variable to keep track of the currently selected file
current_file = FILE_1

# Variable to hold the currently running subprocess object
current_process = None

# Flag to signal when to exit the loop
exit_script = False

def terminate_current_process():
    """Terminates the currently running subprocess if one exists."""
    global current_process
    if current_process and current_process.poll() is None: # Check if process is running
        print(f"Terminating process for {current_file}...")
        try:
            current_process.terminate() # Request graceful termination
            # Give the process a moment to terminate
            time.sleep(0.1)
            if current_process.poll() is None:
                print("Process did not terminate, killing...")
                current_process.kill() # Force termination if needed
        except Exception as e:
            print(f"Error terminating process: {e}")
        current_process = None # Clear the process reference

def start_file(filename):
    """Starts a new subprocess for the given file."""
    global current_process
    try:
        print(f"Starting process for {filename}...")
        # Use Popen to run the file without waiting
        # We don't capture output here as the application might be interactive
        process = subprocess.Popen([sys.executable, filename])
        current_process = process
        print(f"Process started with PID: {process.pid}")
    except FileNotFoundError:
        print(f"Error: The file '{filename}' was not found.")
        current_process = None
    except Exception as e:
        print(f"An error occurred while starting '{filename}': {e}")
        current_process = None


def switch_to_file1():
    """Switches the current file to FILE_1 and starts it."""
    global current_file
    if current_file != FILE_1:
        terminate_current_process()
        current_file = FILE_1
        start_file(current_file)
    else:
        print(f"{FILE_1} is already the current file.")


def switch_to_file2():
    """Switches the current file to FILE_2 and starts it."""
    global current_file
    if current_file != FILE_2:
        terminate_current_process()
        current_file = FILE_2
        start_file(current_file)
    else:
        print(f"{FILE_2} is already the current file.")

def quit_script():
    """Sets the flag to exit the main loop and terminates the current process."""
    global exit_script
    print("\nQuitting script...")
    terminate_current_process()
    exit_script = True

# Set up keyboard hooks
# The `suppress=False` means the key press will also be sent to the active application
# Set to `suppress=True` if you want the main script to consume the key press
# and prevent it from reaching the child application.
# Given your requirement, we'll start with suppress=False, but you might need to
# experiment based on how your child applications handle input.
keyboard.add_hotkey('t', switch_to_file1, suppress=False)
keyboard.add_hotkey('f', switch_to_file2, suppress=False)
keyboard.add_hotkey('q', quit_script, suppress=False)

print(f"Starting script. Initial file: {current_file}.")
print("Press 't' to switch to file1.py")
print("Press 'f' to switch to file2.py")
print("Press 'q' to quit")

# Start the initial file
start_file(current_file)

try:
    # Main loop - just waits for the exit_script flag to be set by hotkeys
    while not exit_script:
        # Check if the current process has terminated on its own
        if current_process and current_process.poll() is not None:
            print(f"Process for {current_file} finished unexpectedly.")
            current_process = None # Clear the reference
            # You might want to restart the file here, or just wait for user input
            # For now, we'll just let it wait for user input to switch/quit

        time.sleep(0.1) # Small sleep to prevent high CPU usage

except Exception as e:
    print(f"An error occurred in the main loop: {e}")
finally:
    # Ensure the current process is terminated on exit
    terminate_current_process()
    # Clean up keyboard hooks when exiting
    keyboard.unhook_all()
    print("Script finished.")

