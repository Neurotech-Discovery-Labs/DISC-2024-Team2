import os
import subprocess
import pytrigno
import numpy as np
import tkinter as tk
from collections import deque
import time
import csv
from datetime import datetime
from tkinter import messagebox
import random

# Configuration for the Trigno EMG device
host = 'localhost'  # Replace with your host IP
dev = pytrigno.TrignoEMG(channel_range=(0, 15), data_port=50043, samples_per_read=850, host=host, units='normalized')

# Start the device
dev.start()

# Print the current working directory
print("Current Working Directory:", os.getcwd())

# Create a basic Tkinter window
root = tk.Tk()
root.title("EMG-based BMI Interface")

# Increase the canvas size to fit the screen
canvas_width = 1920  # Set width to screen resolution
canvas_height = 1000 #1080  # Subtract 20 pixels if needed
canvas = tk.Canvas(root, width=canvas_width, height=canvas_height, bg='white')
canvas.pack()

# Moving average filter settings
window_size = 5
signal_buffer = deque(maxlen=window_size)

# New initial position (centered)
initial_x = canvas_width // 2
initial_y = canvas_height // 2

# Store positions (fix for NameError)
x_position = [initial_x]
y_position = [initial_y]

# Create a circle to represent the controlled object (blue circle)
moving_circle_radius = 10
moving_circle = canvas.create_oval(
    initial_x - moving_circle_radius, initial_y - moving_circle_radius, 
    initial_x + moving_circle_radius, initial_y + moving_circle_radius, 
    fill='blue'
)

# Update barrier positions dynamically
barrier_distance = 0.38 * min(canvas_width, canvas_height)  # Adjusted for scaling
small_distance = barrier_distance / 2

# Initialize min/max trackers
num_channels = 4

# Flag to track if the circle is active
circle_active = True

# Adjust barriers to fit the new canvas, making them the same size as the blue moving circle
barriers = {
    "top": canvas.create_oval(initial_x - moving_circle_radius, initial_y - moving_circle_radius - 400, 
                               initial_x + moving_circle_radius, initial_y + moving_circle_radius - 400, fill='orange'),

    "right": canvas.create_oval(initial_x - moving_circle_radius + 550, initial_y - moving_circle_radius, 
                                 initial_x + moving_circle_radius + 550, initial_y + moving_circle_radius, fill='orange'),

    "bottom": canvas.create_oval(initial_x - moving_circle_radius, initial_y - moving_circle_radius + 400, 
                                  initial_x + moving_circle_radius, initial_y + moving_circle_radius + 400, fill='orange'),

    "left": canvas.create_oval(initial_x - moving_circle_radius - 550, initial_y - moving_circle_radius, 
                                initial_x + moving_circle_radius - 550, initial_y + moving_circle_radius, fill='orange'),

    "top_right": canvas.create_oval(initial_x - moving_circle_radius + 275, initial_y - moving_circle_radius - 200, 
                                     initial_x + moving_circle_radius + 275, initial_y + moving_circle_radius - 200, fill='orange'),

    "bottom_right": canvas.create_oval(initial_x - moving_circle_radius + 275, initial_y - moving_circle_radius + 200, 
                                       initial_x + moving_circle_radius + 275, initial_y + moving_circle_radius + 200, fill='orange'),

    "bottom_left": canvas.create_oval(initial_x - moving_circle_radius - 275, initial_y - moving_circle_radius + 200, 
                                      initial_x + moving_circle_radius - 275, initial_y + moving_circle_radius + 200, fill='orange'),

    "top_left": canvas.create_oval(initial_x - moving_circle_radius - 275, initial_y - moving_circle_radius - 200, 
                                   initial_x + moving_circle_radius - 275, initial_y + moving_circle_radius - 200, fill='orange')
}

# Initialize trial order (4 trials per color, shuffled)
trial_order = ["top", "right", "bottom", "left", "top_right", "bottom_right", "bottom_left", "top_left"] * 3
random.shuffle(trial_order)
current_trial_index = 0

# Initially, hide all barriers except the first one
for color, barrier in barriers.items():
    canvas.itemconfig(barrier, state='hidden')
canvas.itemconfig(barriers[trial_order[current_trial_index]], state='normal')

# Points and trial settings

successful_hits = 0  # Counter for successful hits
max_hits = 24  # Set the maximum number of hits to 24 for 24 trials
points_display = canvas.create_text(
    canvas_width // 2, 50, 
    text=f"Successful Points: 0", 
    font=("Calibri", 20)
)

# List to store EMG data (trial number, timestamp, signal strength)
emg_data = []  

# Calibration settings
rest_calibration_time = 5  # Calibration time at rest in seconds
mvc_calibration_time = 2    # Calibration time during MVC in seconds
pause_time = 2               # Pause time in seconds
noise_levels = None  # To be set after calibration
max_contraction_value = None   # Max contraction value for thresholds
calibration_complete = False

def show_message(message):
    root = tk.Tk()
    root.withdraw()  # Hide the main window
    messagebox.showinfo("Calibration Instruction", message)
    root.destroy()
    
def show_calibration_message():
    root = tk.Tk()
    root.withdraw()
    messagebox.showinfo("Calibration Instruction", "Calibration started. Please relax your arm for 5 seconds...")
    root.destroy()
    
def calibrate():
    global noise_levels, scaling_factors, max_contractions, calibration_complete 

    # Predefined fallback sensor noise thresholds
    default_noise_threshold = 0.05  # Fallback if rest calibration is insufficient
    # Show pop-up message for relaxation phase
    show_calibration_message()
    
    # Phase 1: Collect samples at rest
    print("Calibration started. Please relax your arm for 5 seconds...")
    rest_samples = [[] for _ in range(4)]

    start_time = time.time()
    while time.time() - start_time < rest_calibration_time:
        data = dev.read() * 1e6  # Convert volts to microvolts
        data[2] = data[4]  # HARD CODED BS: swapping to emg 5 because emg 3 doesnt seem to work well
        for i in range(4):
            rest_samples[i].append(np.mean(np.abs(data[i])))

    rest_means = [np.mean(samples) for samples in rest_samples]
    print(f"Rest calibration complete. Resting means: {rest_means}")

    # Set noise thresholds dynamically based on resting means (e.g., 2x the noise level)  NOT DYNAMIC since you only do this once. THIS VALUES SHOULD REP CENTER OF SCREEN 
    noise_levels = [max(mean * 1.1, default_noise_threshold) for mean in rest_means]
    print(f"Dynamic noise thresholds set: {noise_levels}")
    
    # Calibration for MVC
    scaling_factors = [] 
    max_contractions = []
    
    for i in range(4):
        if i == 0:
            show_message("Right arm up..")
        elif i == 1:
            show_message("Right arm down")
        elif i == 2:
            show_message("Left arm left...")
        elif i == 3:
            show_message("Left arm to right...")

        print("Pause calibration, prepare for next") 
        time.sleep(pause_time)  # Pause for 2 seconds to allow for max contraction
        print("Recording now!")

        mvc_samples = [] # INITIALIZING MAX VOLUNTARY CONTRACTION (MVC) VARIABLE.... REALTIME 
        start_time = time.time() 
        while (time.time() - start_time) < mvc_calibration_time:   #WHILE THE CLOCKTIME-THE STARTTIME IS LESS THAN CALIBRATION TIME... THEN READ THE DATA AND UPDATED 
            data = dev.read() * 1e6  #read in data & change into micro volts (from volts) 
            data[2] = data[4]  #swapping to emg 5 because emg 3 doesnt seem to work well
            if data.shape[0] > 0:  
                mvc_samples.append(np.mean(np.abs(data[i])))  #WHILE IN THIS LOOP FOR CALIBRATION TIME, THEN ADD TO THE MVC_SAMPLES VARIABLE THE CURRENT READ VALUE

        mvc_mean = np.mean(mvc_samples) #NOW THAT WE ARE OUT OF THE LOOP, CALCULATE THE MEAN OF OUR APPDENDED SAMPLES DURING THE CALIBRATION
        #scaling_factor = (mvc_mean - 0.5 * mvc_mean) / mvc_mean 
        max_contractions.append(mvc_mean)

    calibration_complete = True 
    global initial_time
    initial_time = time.time()  # Record when calibration ended
    
def stop_circle():
    global circle_active
    circle_active = False
    print("Circle stopped!")
    root.after(3000, reset_circle)  # Wait for 3 seconds before resetting

def reset_circle():
    global current_trial_index, successful_hits, circle_active

    # Reset circle position
    canvas.coords(moving_circle, initial_x - 10, initial_y - 10, initial_x + 10, initial_y + 10)
    x_position.append(initial_x)
    y_position.append(initial_y)
    circle_active = True  # Re-enable movement

    # Proceed to the next barrier
    if current_trial_index < max_hits - 1:
        # Hide the current barrier
        current_color = trial_order[current_trial_index]
        canvas.itemconfig(barriers[current_color], state='hidden')

        # Move to the next trial and show the corresponding barrier
        current_trial_index += 1
        next_color = trial_order[current_trial_index]
        canvas.itemconfig(barriers[next_color], state='normal')
    else:
        end_game()  # End the game if all trials are completed

def check_collision():
    global successful_hits

    moving_coords = canvas.coords(moving_circle)
    current_barrier = trial_order[current_trial_index]
    barrier_coords = canvas.coords(barriers[current_barrier])

    # Check for collision (bounding box overlap)
    if (moving_coords[2] > barrier_coords[0] and moving_coords[0] < barrier_coords[2] and
            moving_coords[3] > barrier_coords[1] and moving_coords[1] < barrier_coords[3]):
        print(f"Collision with {current_barrier.capitalize()} Barrier!")

        # Update successful hit count
        successful_hits += 1
        update_points_display()
        stop_circle()

def update_points_display():
    canvas.itemconfig(
        points_display, 
        text=f"Successful Hits: {successful_hits}/{max_hits}"
    )

def end_game():
    """Handle game termination."""
    print("Maximum number of hits reached. Stopping the program.")
    save_data_to_csv()  # Save the EMG data to CSV
    open_csv_file()  # Open the CSV file after saving
    dev.stop()  # Stop the EMG device
    root.quit()  # Exit the Tkinter loop
    
def update_position(sensor0, sensor1, sensor2, sensor3):
    """Update the position of the circle based on normalized sensor inputs."""
    global circle_active, x_position, y_position

    amount_movement = 150
    
    if not circle_active or not calibration_complete:
        return

    new_x_position = x_position[-1]
    new_y_position = y_position[-1]

    # Normalize and scale signals if they exceed their minimum threshold
    def normalize_and_scale(sensor_value, min_threshold, max_contraction):
        if sensor_value < min_threshold: 
            return 0  # Ignore signals below the threshold
        normalized = (sensor_value - min_threshold) / (max_contraction - min_threshold)
        return normalized
        
    if sensor0 >= noise_levels[0] or sensor1 >= noise_levels[1]:  # Move up
        
        movement1 = normalize_and_scale(sensor0, noise_levels[0], max_contractions[0])
        movement2 = normalize_and_scale(sensor1, noise_levels[1], max_contractions[1])
        if movement1< movement2:
            movement1 = 0
        else:
            movement2 = 0
            
        print(f"Sensor 0 Signal: {movement1:.4f}")
        print(f"Sensor 1 Signal: {movement2:.4f}")
        new_y_position += (amount_movement * movement2)
        new_y_position -= (amount_movement * movement1)

    if sensor2 >= noise_levels[2] or sensor3 >= noise_levels[3]:  # Move left
        
        movement3 = normalize_and_scale(sensor2, noise_levels[2], max_contractions[2])
        movement4 = normalize_and_scale(sensor3, noise_levels[3], max_contractions[3])
        if movement3 < movement4:
            movement3 = 0
        else:
            movement4 = 0

        print(f"Sensor 2 Signal: {movement3:.4f}")
        print(f"Sensor 3 Signal: {movement4:.4f}")
        new_x_position -= amount_movement * movement3
        new_x_position += amount_movement * movement4
     
    # Ensure the blue circle stays within the new full-screen canvas
    # Ensure the blue circle stays within the full-screen canvas
    new_x_position = max(moving_circle_radius, min(canvas_width - moving_circle_radius, new_x_position))
    new_y_position = max(moving_circle_radius, min(canvas_height - moving_circle_radius * 2, new_y_position))

    # Update circle position
    x_position.append(new_x_position)
    y_position.append(new_y_position)
    canvas.coords(
        moving_circle,
        new_x_position - 10, new_y_position - 10,
        new_x_position + 10, new_y_position + 10
    )
    print(f"Moving Circle Position: ({new_x_position}, {new_y_position})")
    
    # Append EMG data with current x and y positions, only if successful hits are less than max hits
    if successful_hits < max_hits:
        current_time = time.time() - initial_time
        emg_data.append((current_trial_index, current_time, (sensor0 + sensor1) / 2, new_x_position, new_y_position))

    check_collision()

def save_data_to_csv():
    """Save the EMG data to a CSV file with a timestamp in the filename."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f'emg_data_{timestamp}.csv'

    try:
        with open(filename, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['Trial', 'Timestamp', 'Signal Strength', 'X Position', 'Y Position'])  # Correct header
            
            # Simply write the data without adding duplicate columns
            writer.writerows(emg_data)  
        
        print(f"EMG data saved to '{filename}'.")
    except Exception as e:
        print(f"Error saving data to CSV: {e}")

def open_csv_file():
    """Open the CSV file after saving."""
    file_path = f'emg_data_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    if os.path.exists(file_path):
        if os.name == 'posix':  # macOS or Linux
            subprocess.run(['open', file_path]) if os.uname().sysname == 'Darwin' else subprocess.run(['xdg-open', file_path])
        else:  # Windows
            os.startfile(file_path)
    else:
        print("CSV file not found.")

def read_emg():
    """Read EMG data and update the position of the circle."""

    data = dev.read() * 1e6  # Read in latest data and Convert raw data from V to µV  
    data[2] = data[4]; # swapping to emg 5 because emg 3 doesnt seem to work well
    if data.shape[1] > 0:  # Check if we have any data
        print(data.shape)  # Ensure at least four sensors are available
        # Read and normalize data for both sensors
        sensor0 = np.mean(np.abs(data[0])) # avg sample taken 
        sensor1 = np.mean(np.abs(data[1]))
        sensor2 = np.mean(np.abs(data[2]))
        sensor3 = np.mean(np.abs(data[3]))
        
        # Pass the original signal strengths as well for updating the plot
        update_position(sensor0, sensor1, sensor2, sensor3)
        
    else:
        print("No data received.")
    
    root.after(1, read_emg)      # Call this function again after 4 ms

# Start the calibration
calibrate()

# Start reading EMG data  THIS IS THE MAIN EXPERIMENT LOOP
read_emg()

# Start the Tkinter event loop
root.mainloop()

