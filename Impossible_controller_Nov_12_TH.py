# JMR Sept 1 2024 Web control of ESP32-S3 Seeed Studio originaly for drone control
# Added ultrasound distance to the stream
# ESP32 2 MP Camera
# Connect to 10west3319
# Sept 12 2024, added commands for the drone to move in different directions, integrated control and IMU in one thread.
# Sept 13the hangup was the ultrasound! causing main loop to hang
# Sept 30 added OLED display
# Nov 9 2024, added analog input and rewrote to control vines :) with auto mode
# Nov 11 2024, added automatic calibration for wet and dry values and redid ADC A2/GPIO3 to A8/GPIO7 AND USED GPIO44 FOR PUMP 3
# Nov 12 2024, added temperature and humidity sensor - really tricky to get working so save these settings
import network
import socket
import camera
import time
import gc
from machine import Pin, I2C, PWM, ADC
import _thread

import utime
import socket
import _thread
import ssd1306

# Clear memory before starting
gc.collect()

First_network = "10 West"
First_network_password = "10west3319"
Second_network = "Starlink"
Second_network_password = "Rothberg"
Third_network = "genechaser"
Third_network_password = "12345678"
Fourth_network = "genemachine"
Fourth_network_password = "12345678"

# Deinitialize pins
for pin_num in range(45):  # ESP32-CAM has pins 0-44
    try:
        pin = Pin(pin_num)
        pin.init(Pin.IN)  # Reset to input mode
    except:
        pass  # Skip pins that can't be accessed

# Initialize a single I2C object for both Temperature and Humidity and OLED 
i2c = I2C(1, scl=Pin(6), sda=Pin(5), freq=100000)

SENSOR_ADDR = 0x38

# Initialize OLED display
oled = ssd1306.SSD1306_I2C(128, 64, i2c)
print("OLED initialized", oled)
oled.fill(0)
oled.text("OLED initialized", 0, 0)
oled.show() 

# Scan for I2C devices (optional, for debugging)
print("Scanning I2C bus...")
devices = i2c.scan()
if devices:
    for i, device in enumerate(devices):
        print(f"I2C device found at address: 0x{device:02X}")
        oled.text(f"I2C device found at address: 0x{device:02X}", 0, 10 + i*10)
        oled.show()
else:
    print("No I2C devices found")
    oled.text("No I2C devices found", 0, 10)
    oled.show()

# Individual GPIO definitions for pumps
GPIO3 = Pin(3, Pin.OUT)   # Pump 0 Have to use 3 because need 7 for ADC since 3 ADC does not work in carrier board
GPIO8 = Pin(8, Pin.OUT)   # Pump 1
GPIO9 = Pin(9, Pin.OUT)   # Pump 2
GPIO44 = Pin(44, Pin.OUT) # Pump 3

# Then use a dictionary to reference them
pump_pins = {
    0: GPIO3,
    1: GPIO8,
    2: GPIO9,
    3: GPIO44,
}

#print out the pump pins
print("Pump pins initialized")
oled.fill(0)
oled.text("Pump pins initialized", 0, 0)
oled.show()
for i, pin in enumerate(pump_pins):
    print(f"Pump pin {i} value:", pin)
    oled.text(f"Pump pin {i} value:", pin, 0, 10 + i*10)
    oled.show()

# Initialize analog pins
analog_pins = [
    ADC(Pin(1)),  # A0  Sensor 0
    ADC(Pin(2)),  # A1  Sensor 1
    ADC(Pin(7)),  # A7  Sensor 2 Had to use 7 because 3 ADC does not work in carrier board
    ADC(Pin(4)),  # A3  Sensor 3
]

# Configure ADC for 12-bit range (0-4095)
print("Configuring analog pins")
oled.fill(0)
oled.text("Configuring analog pins", 0, 0)
oled.show()
for i, pin in enumerate(analog_pins):
    print(f"Configuring pin {pin}")
    oled.text(f"Configuring pin {pin}", 0, 10 + i*10)
    oled.show()
    pin.atten(ADC.ATTN_11DB)  # Full range: 0-3.3V

print("Analog pins initialized")
oled.fill(0)
oled.text("Analog pins initialized", 0, 0)
oled.show()
for i, pin in enumerate(analog_pins):
    print(f"Analog pin {i} value:", pin.read_u16() >> 4)  # Convert 16-bit to 12-bit
    oled.text(f"Analog pin {i} value:", pin.read_u16() >> 4, 0, 10 + i*10)
    oled.show()

#PIN IS GPIO NOT pysical yeah, so it works. These pins are on the camera module!
trigger = Pin(41, Pin.OUT)
echo = Pin(42, Pin.IN)

# Initial delay to allow hardware to be ready
time.sleep(1)  # Delay for 1 seconds

# Global settings for automation
auto_settings = {
    'enabled': False,
    'max_duration': 30,        # Could be 'daily_limit'
    'auto_duration': 5,        # Could be 'water_time'
    'pause_duration': 60,      # Could be 'soak_time'
    'thresholds': {
        0: {'wet': 1300, 'dry': 2000},  # Instead of 'low' and 'high'
        1: {'wet': 1300, 'dry': 2000}, 
        2: {'wet': 1300, 'dry': 2000},
        3: {'wet': 1300, 'dry': 2000}
    },
    'timeouts': {
        0: {'locked_until': 0},
        1: {'locked_until': 0},
        2: {'locked_until': 0}, 
        3: {'locked_until': 0},
    },
    'cycle_totals': {         # Could be 'daily_totals'
        0: {'total': 0, 'last_water': 0},
        1: {'total': 0, 'last_water': 0},
        2: {'total': 0, 'last_water': 0},
        3: {'total': 0, 'last_water': 0},
    }
}


"""
- is_pump_locked()      # Timeout checking
- set_pump_timeout()    # Setting 24h timeouts
- reset_timeouts()      # Reset all timeouts
- check_and_water()     # Auto mode functionality
"""

# Add lock definition near pump_status dictionary
status_lock = _thread.allocate_lock()

pump_status = {
    'active_pump': None,      # 0 means no pump running
    'message': '',         # Current status message
    'duration': 0,         # Duration of current pump cycle
    'display_update': False # Flag for when OLED needs update
}

def pump_worker(source='manual'):
    """Background thread that manages ALL pump timing and auto watering
    This is where pumps get turned ON and OFF after their duration
    Also handles automatic watering checks
    Runs independently so main loop stays responsive"""
    global pump_status
    while True:
        # Handle active pump timing
        if pump_status['active_pump'] is not None:
            pump_num = pump_status['active_pump']
            duration = pump_status['duration']
            
            # Check if pump is locked before starting
            locked, lock_message = is_pump_locked(pump_num)
            if locked:
                with status_lock:
                    pump_status['active_pump'] = None
                    pump_status['message'] = lock_message
                    pump_status['display_update'] = True
                continue
            
            # Check if this cycle would exceed max_duration
            cycle_total = auto_settings['cycle_totals'][pump_num]['total'] + duration
            if cycle_total > auto_settings['max_duration']:
                with status_lock:
                    pump_status['active_pump'] = None
                    pump_status['message'] = f"Pump {pump_num} cycle limit reached"
                    pump_status['display_update'] = True
                set_pump_timeout(pump_num)
                continue
            
            # Update status and start pump
            with status_lock:
                pump_status['message'] = f"{source}: Pump {pump_num} ON for {duration}s"
                pump_status['display_update'] = True

            # Turn pump ON
            pump_pins[pump_num].value(1)
            # Wait for duration
            # Wait for duration while updating message
            start_time = time.time()
            while time.time() - start_time < duration:
                remaining = duration - (time.time() - start_time)
                with status_lock:
                    pump_status['message'] = f"{source}: Pump {pump_num} ON - {remaining:.1f}s remaining"
                    print(pump_status['message'])
                    pump_status['display_update'] = True
                time.sleep(0.5)  # Small delay to prevent tight loop
            # Turn pump OFF
            pump_pins[pump_num].value(0)
            print(f"Pump {pump_num} OFF")
            # Update status with lock
            with status_lock:
                pump_status['active_pump'] = None
                pump_status['message'] = f"{source}: Pump {pump_num} OFF"
                pump_status['display_update'] = True
            
            # After pump completes, update cycle total
            auto_settings['cycle_totals'][pump_num]['total'] += duration
            auto_settings['cycle_totals'][pump_num]['last_water'] = time.time()
        
        # Handle automatic watering checks
        elif auto_settings['enabled']:
            for i, pin in enumerate(analog_pins):
                value = pin.read_u16() >> 4
                thresholds = auto_settings['thresholds'][i]
                
                if value > thresholds['dry']:
                    # Check if pump is locked
                    locked, lock_message = is_pump_locked(i)
                    if locked:
                        continue
                    
                    # Check if adding auto_duration would exceed max_duration
                    cycle_total = auto_settings['cycle_totals'][i]['total'] + auto_settings['auto_duration']
                    if cycle_total > auto_settings['max_duration']:
                        set_pump_timeout(i)
                        continue
                    
                    # Turn pump ON
                    pump_pins[i].value(1)
                    
                    # Update status
                    with status_lock:
                        pump_status['active_pump'] = i
                        pump_status['duration'] = auto_settings['auto_duration']
                        pump_status['message'] = f"Auto: Pump {i} ON for {auto_settings['auto_duration']}s"
                        pump_status['display_update'] = True
                    
                                                # Wait for duration while updating message
                    start_time = time.time()
                    while time.time() - start_time < auto_settings['auto_duration']:
                        remaining = auto_settings['auto_duration'] - (time.time() - start_time)
                        with status_lock:
                            pump_status['message'] = f"Auto: Pump {i} ON - {remaining:.1f}s remaining"
                            pump_status['display_update'] = True
                        time.sleep(0.5)
                    
                    # Turn pump OFF
                    pump_pins[i].value(0)
                    
                    # Update status
                    with status_lock:
                        pump_status['active_pump'] = None
                        pump_status['message'] = f"Auto: Pump {i} OFF"
                        pump_status['display_update'] = True
                    
                    #update the message for time of pause need  a while loop
                    start_time = time.time()
                    while time.time() - start_time < auto_settings['pause_duration']:
                        remaining = auto_settings['pause_duration'] - (time.time() - start_time)
                        with status_lock:
                            pump_status['message'] = f"Auto: Pump {i} OFF - Pause {remaining:.1f}s remaining"
                            pump_status['display_update'] = True
                        time.sleep(0.5)
                    # After auto watering completes, update cycle total
                    auto_settings['cycle_totals'][i]['total'] += auto_settings['auto_duration']
                    auto_settings['cycle_totals'][i]['last_water'] = time.time()
                    
                    # Check if we need to set a timeout
                    value = pin.read_u16() >> 4
                    if value > thresholds['dry']:
                        set_pump_timeout(i)
        
        # Short sleep to prevent tight loop
        time.sleep(0.1)


def is_pump_locked(pump_num):
    """Check if pump is in timeout"""
    locked_until = auto_settings['timeouts'][pump_num]['locked_until']
    if locked_until > time.time():
        # Calculate remaining hours
        hours_left = (locked_until - time.time()) / 3600
        print(f"Pump {pump_num} locked for {hours_left:.1f} more hours")
        oled.fill(0)
        oled.text(f"Pump {pump_num} locked for {hours_left:.1f} more hours", 0, 0)
        oled.show()
        return True, f"Pump {pump_num} locked for {hours_left:.1f} more hours"
    # Reset cycle total when timeout expires
    auto_settings['cycle_totals'][pump_num]['total'] = 0
    return False, ""

def set_pump_timeout(pump_num):
    """Set 24-hour timeout for a pump"""
    auto_settings['timeouts'][pump_num]['locked_until'] = time.time() + (24 * 3600)
    print(f"Pump {pump_num} locked for 24 hours due to timeout")
    oled.fill(0)
    oled.text(f"Pump {pump_num} locked for 24 hours due to timeout", 0, 0)
    oled.show()
    return f"Pump {pump_num} locked for 24 hours due to timeout"

def reset_timeouts():
    """Reset all timeouts"""
    for pump_num in range(4):
        print(f"Resetting pump {pump_num} timeout")
        oled.fill(0)
        oled.text(f"Resetting pump {pump_num} timeout", 0,10+pump_num*10)
        oled.show()
        auto_settings['timeouts'][pump_num]['locked_until'] = 0
    print("All timeouts reset")
    return "All timeouts reset"


"""
Web Browser Commands:
    water 1 30     - Turn on pump 1 for 30 seconds
    setdry 1 1300   - Set dry threshold for sensor 1 to 1300
    setwet 1 2000   - Set wet threshold for sensor 1 to 2000
    auto on        - Enable automatic mode
    auto off       - Disable automatic mode
    status         - Get current settings and sensor values
    reset          - Reset all timeouts
    calibrate [0-3] - Start calibration for specific sensor default is all
"""


def main_page():
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Gabby's Impossible Vines Hydroponics</title>
    <style>
        body, html {
            margin: 0;
            padding: 0;
            height: 100%;
            display: flex;
            flex-direction: column;
        }
        .stream-container {
            flex: 1;
            display: flex;
            justify-content: center;
            align-items: center;
            background-color: #000;
        }
        .distance-container {
            height: 50px;
            background-color: #f0f0f0;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        img {
            max-width: 100%;
            max-height: 100%;
            object-fit: contain;
        }
    </style>
</head>
<body>
    <div class="stream-container">
        <h1 style="color: white; position: absolute; top: 5px; left: 50%; transform: translateX(-50%);">Gabby's Impossible Vines Hydroponic</h1>
        <img id="stream" src="/capture" alt="Live Stream">
    </div>
    <div class="distance-container">
        <h2>Hydroponic Status: <span id="distance">Measuring...</span></h2>
    </div>
    <div class="command-container">
        <input type="text" id="commandInput" placeholder="Enter command">
        <button onclick="sendCommand()">Send</button>
        <p id="commandStatus"></p>
        <p style="color: #666;">
Commands: water 1 30 | auto on/off | status | setwet 1 500 | setdry 1 1000 | reset | setdaily 30 | calibrate [0-3]
</p>
    </div>
    <script>
        // Function to update the image
        function updateImage() {
            document.getElementById('stream').src = '/capture?' + new Date().getTime();
        }
        
        // Function to update the distance
        function updateDistance() {
            fetch('/distance')
                .then(response => response.text())
                .then(distance => {
                    document.getElementById('distance').textContent = distance ;
                })
                .catch(error => console.error('Error fetching distance:', error));
        }
        
        // Update image more frequently (every 500ms)
        setInterval(updateImage, 500);  // Adjust this value to change image update frequency
        
        // Update distance less frequently (every 5 seconds)
        setInterval(updateDistance,1100);  // Adjust this value to change distance update frequency

        function sendCommand() {
            var command = document.getElementById('commandInput').value;
            fetch('/command?cmd=' + encodeURIComponent(command))
                .then(response => response.text())
                .then(result => {
                    document.getElementById('commandStatus').textContent = result;
                    console.log(result);
                })
                .catch(error => {
                    console.error('Error:', error);
                    document.getElementById('commandStatus').textContent = 'Error: ' + error;
                });
        }
    </script>
</body>
</html>
"""

# Camera setup with retry mechanism
def init_camera():
    for attempt in range(5):  # Retry up to 5 times
        try:
            camera.deinit()
            time.sleep(2)
            cam = camera.init()
            if cam:
                camera.framesize(10)     # frame size 800x600 (1.33 aspect ratio)
                camera.contrast(3)       # increase contrast
                camera.speffect(0)       # normal color mode (was 2 for grayscale)
                camera.quality(10)       # quality (0-63, lower is higher quality)
                camera.saturation(3)     # increase color saturation
                camera.brightness(-1)     # slightly increase brightness
                camera.whitebalance(1)   # enable auto white balance
                
                return True
            print(f"Camera initialization failed, attempt {attempt + 1}/5")
        except Exception as e:
            print(f"Error initializing camera: {e}")
    print("All camera initialization attempts failed")
    return False


def connect_wifi(ssid, password):
    wifi.connect(ssid, password)
    max_wait = 10
    while max_wait > 0:
        if wifi.isconnected():
            return True
        max_wait -= 1
        print('Waiting for connection...')
        time.sleep(1)
    print('Wi-Fi connection failed')
    return False


def get_distance(trigger, echo, timeout_us=60000):
    # PIN IS GPIO NOT physical yeah, so it works.
    trigger.value(0)
    utime.sleep_us(2)
    trigger.value(1)
    utime.sleep_us(5)  
    trigger.value(0)
    
    pulse_start = utime.ticks_us()
    deadline = utime.ticks_add(pulse_start, timeout_us)
    
    # Wait for echo to go high
    while echo.value() == 0:
        if utime.ticks_diff(deadline, utime.ticks_us()) <= 0:
            print(f"Timeout waiting for echo start on {trigger}")
            return 0
        pulse_start = utime.ticks_us()
    
    # Wait for echo to go low
    while echo.value() == 1:
        if utime.ticks_diff(deadline, utime.ticks_us()) <= 0:
            print(f"Timeout waiting for echo end on {trigger}")
            return 0
        pulse_end = utime.ticks_us()
    
    pulse_duration = utime.ticks_diff(pulse_end, pulse_start)
    distance = (pulse_duration * 0.0343) / 2
    return distance


def process_command(cmd):
    global auto_settings
    # URL decode and clean the command
    response_msg = ""
    cmd = cmd.replace('%20', ' ')
    print(f"Command: {cmd}")
    parts = cmd.strip().lower().split()  # Split into parts and then handle each command based on first word
    print(f"Command parts: {parts}")
    print(f"Command parts[0]: {parts[0]}")
    print(f"Command parts length: {len(parts)}")
    if len(parts) > 1:  
        print(f"Command parts[1]: {parts[1]}")
    if len(parts) > 2:
        print(f"Command parts[2]: {parts[2]}")

    if parts[0] == "status":
        response_msg = f"Auto mode: {auto_settings['enabled']} | "
        response_msg += f"Active Pump: {pump_status['active_pump']} | "
        response_msg += f"Max Daily: {auto_settings['max_duration']}s | "
        response_msg += f"Water Time: {auto_settings['auto_duration']}s | "
        
        for sensor in range(4):
            # Get current sensor value and settings
            value = analog_pins[sensor].read_u16() >> 4
            thresholds = auto_settings['thresholds'][sensor]
            cycle_data = auto_settings['cycle_totals'][sensor]
            locked_until = auto_settings['timeouts'][sensor]['locked_until']
            
            # Check lock status directly
            lock_status = f"Locked {((locked_until - time.time()) / 3600):.1f}h" if locked_until > time.time() else "Available"
            
            pump_state = "ON" if pump_status['active_pump'] == sensor else "OFF"
            
            response_msg += f"Sensor {sensor}: Value={value}, Wet={thresholds['wet']}, Dry={thresholds['dry']} | "
            response_msg += f"Status: {lock_status}, Pump: {pump_state} | "
            response_msg += f"Cycle Total: {cycle_data['total']}s | "
        
        print(f"Response message: {response_msg}")
        display_message(response_msg)
        return response_msg
    
    elif parts[0] == "auto" and len(parts) > 1:
        if parts[1] == "on":
            auto_settings['enabled'] = True
            print(f"Automatic mode enabled")
            display_message("Automatic mode enabled")
            return "Automatic mode enabled"
        elif parts[1] == "off":
            auto_settings['enabled'] = False
            print(f"Automatic mode disabled")
            display_message("Automatic mode disabled")
            return "Automatic mode disabled"
    
    elif parts[0] == "water" and len(parts) == 3:
        pump_num = int(parts[1])
        duration = int(parts[2])
        if 0 <= pump_num <= 3:
            print(f"Activating pump {pump_num} for {duration} seconds")
            #activate the pump by changing the message my just setting the active pump and duration
            with status_lock:
                pump_status['active_pump'] = pump_num
                pump_status['duration'] = duration
                pump_status['message'] = f"Manual: Pump {pump_num} ON for {duration}s"
                pump_status['display_update'] = True
            display_message(f"Manual: Pump {pump_num} ON for {duration}s")
            return f"Manual: Pump {pump_num} ON for {duration}s"
        else:
            return "Invalid pump number"
    
    elif parts[0] == "setwet" and len(parts) == 3:
        sensor = int(parts[1])
        value = int(parts[2])
        if 0 <= sensor <= 3:
            auto_settings['thresholds'][sensor]['wet'] = value
            print(f"Set wet threshold for sensor {sensor} to {value}")
            display_message(f"Set wet threshold for sensor {sensor} to {value}")
            return f"Set wet threshold for sensor {sensor} to {value}"
    
    elif parts[0] == "setdry" and len(parts) == 3:
        sensor = int(parts[1])
        value = int(parts[2])
        if 0 <= sensor <= 3:
            auto_settings['thresholds'][sensor]['dry'] = value
            print(f"Set dry threshold for sensor {sensor} to {value}")
            display_message(f"Set dry threshold for sensor {sensor} to {value}")
            return f"Set dry threshold for sensor {sensor} to {value}"
    
    elif parts[0] == "setmax" and len(parts) == 2:
        try:
            new_max = int(parts[1])
            if 1 <= new_max <= 300:  # Allowing up to 5 minutes as absolute maximum
                auto_settings['max_duration'] = new_max
                display_message(f"Maximum watering duration set to {new_max} seconds")
                return f"Maximum watering duration set to {new_max} seconds"
            else:
                display_message("Invalid duration. Please choose between 1 and 300 seconds")
                return "Invalid duration. Please choose between 1 and 300 seconds"
        except ValueError:
            display_message("Invalid number format")
            return "Invalid number format"
    
    #reset the timeouts
    elif parts[0] == "reset":
        reset_timeouts()
        display_message("Reset all timeouts")
        return "Reset all timeouts"
    
    elif parts[0] == "calibrate":
        if len(parts) == 1:
            return start_calibration()  # Calibrate all sensors
        elif len(parts) == 2:
            try:
                sensor_num = int(parts[1])
                return start_calibration(sensor_num)  # Calibrate specific sensor
            except ValueError:
                return "Invalid sensor number. Must be 0-3."
    
    return f"Unknown command: '{cmd}'"


def start_calibration(sensor_num=None):
    """Run the calibration process for all sensors or a specific sensor
    Args:
        sensor_num (int, optional): Specific sensor to calibrate (0-3). If None, calibrates all sensors.
    """
    sensors_to_calibrate = range(4) if sensor_num is None else [sensor_num]
    
    for sensor in sensors_to_calibrate:
        if not 0 <= sensor <= 3:
            return f"Invalid sensor number: {sensor}. Must be 0-3."
            
        # Dry calibration
        print(f"Starting dry calibration for sensor {sensor}")
        display_message(f"Place sensor {sensor} in DRY condition. Starting in 20s...")
        time.sleep(20)
        print(f"Starting dry calibration now")
        display_message(f"Starting dry calibration now")
        
        # Take multiple readings and average them for stability
        dry_readings = []
        for _ in range(6):
            value = analog_pins[sensor].read_u16() >> 4
            print(f"Sensor {sensor} dry value: {value}")
            oled.text(f"Sensor {sensor} dry value: {value}", 0, 10 + sensor*10)
            oled.show()
            dry_readings.append(value)
            time.sleep(0.3)
        
        dry_value = sum(dry_readings) // len(dry_readings)
        print(f"Sensor {sensor} average dry value: {dry_value}")
        display_message(f"Sensor {sensor} average dry value: {dry_value}")
        time.sleep(2)
        
        # Wet calibration
        display_message(f"Place sensor {sensor} in WET condition. Starting in 20s...")
        time.sleep(20)
        print(f"Starting wet calibration now")
        display_message(f"Starting wet calibration now")
        
        # Take multiple readings and average them
        wet_readings = []
        for _ in range(6):
            value = analog_pins[sensor].read_u16() >> 4
            print(f"Sensor {sensor} wet value: {value}")
            oled.text(f"Sensor {sensor} wet value: {value}", 0, 10 + sensor*10)
            oled.show()
            wet_readings.append(value)
            time.sleep(0.3)
        
        wet_value = sum(wet_readings) // len(wet_readings)
        print(f"Sensor {sensor} average wet value: {wet_value}")
        display_message(f"Sensor {sensor} average wet value: {wet_value}")
        time.sleep(2)
        
        # Set thresholds with some margin
        margin = (dry_value - wet_value) * 0.1  # 10% margin
        auto_settings['thresholds'][sensor]['dry'] = int(dry_value - margin)
        auto_settings['thresholds'][sensor]['wet'] = int(wet_value + margin)
        
        display_message(f"S{sensor} calibrated: Dry: {auto_settings['thresholds'][sensor]['dry']} Wet: {auto_settings['thresholds'][sensor]['wet']}")
        time.sleep(3)
    
    return "Calibration complete for " + ("all sensors" if sensor_num is None else f"sensor {sensor_num}")


def display_message(message):
    oled.fill(0)
    # Split message into chunks of 16 chars (96 pixels wide, 6 pixels per char)
    lines = []
    
    while message:
        if len(message) > 16:
            split_point = message[:16].rfind(' ')
            if split_point == -1:  # No space found
                split_point = 16
            lines.append(message[:split_point])
            message = message[split_point:].strip()
        else:
            lines.append(message)
            message = ''
    
    # Calculate number of pages needed (5 lines per page when showing page numbers, 6 without)
    num_pages = (len(lines) + 4) // 5  # Round up division for multi-page
    
    # Display each page
    for page in range(num_pages):
        oled.fill(0)
        # Get lines for this page
        if num_pages > 1:
            # Get 5 lines per page when showing page numbers
            page_lines = lines[page*5:(page+1)*5]
            # Show page number on first line
            oled.text(f"Page {page+1}/{num_pages}", 0, 0)
            # Display lines starting from second row
            for i, line in enumerate(page_lines):
                oled.text(line, 0, (i+1)*10)
        else:
            # Get 6 lines for single page (no page numbers needed)
            page_lines = lines[page*6:(page+1)*6]
            # Display lines using full height
            for i, line in enumerate(page_lines):
                oled.text(line, 0, i*10)
        oled.show()
        time.sleep(2.0)  # Pause between pages

def display_status():
    """Update OLED display with current status using display_message"""
    # Build status message string
    status_msg = f"Auto: {auto_settings['enabled']} | "
    
    # Add temperature and humidity
    temp, humidity = read_temp_humidity()
    if temp is not None:
        status_msg += f"T:{temp:.1f}C H:{humidity:.1f}% | "
    
    # Add sensor values and thresholds
    for i, pin in enumerate(analog_pins):
        value = pin.read_u16() >> 4
        thresholds = auto_settings['thresholds'][i]
        status_msg += f"S{i}: {value} | "
        status_msg += f"L:{thresholds['dry']} H:{thresholds['wet']} | "
    
    # Display the message using existing function
    display_message(status_msg)

def read_and_display_analog():
    # Initialize analog pins
    # Configure ADC for 12-bit range (0-4095)
    for pin in analog_pins:
        pin.atten(ADC.ATTN_11DB)  # Full range: 0-3.3V
    
    # Read values and display
    oled.fill(0)  # Clear display
    for i, pin in enumerate(analog_pins):
        value = pin.read_u16() >> 4  # Convert 16-bit to 12-bit
        oled.text(f"A{i}: {value}", 0, i*10)  # Each line 10 pixels apart
    temperature, humidity = read_temp_humidity()
    oled.text(f"T: {temperature:.1f}C H: {humidity:.1f}%", 0, 50)
    oled.show()

# Replace the existing read_temp_humidity function with this one
def read_temp_humidity():
    """Read temperature and humidity from sensor"""
    try:
        # 1. Reset sequence - Ensures the sensor is in a known state
        i2c.writeto(0x38, b'\xBA')  # Soft reset command
        time.sleep(0.02)  # 20ms delay after reset

        # 2. Trigger measurement - Tells sensor to take a new reading
        i2c.writeto(0x38, b'\xAC\x33\x00')  # Start measurement command
        time.sleep(0.1)  # Wait for measurement to complete

        # 3. Read command - Prepares sensor to send data
        i2c.writeto(0x38, b'\x2A')  # Trigger data transmission
        time.sleep(0.1)  # Wait for data to be ready
        
        # 4. Read 6 bytes of data
        data = i2c.readfrom(0x38, 6)
        
        # 5. Calculate humidity
        humid_raw = (data[1] << 12) | (data[2] << 4) | (data[3] >> 4)
        humidity = (humid_raw / 1048576.0) * 100
        
        # 6. Calculate temperature
        temp_raw = ((data[3] & 0x0F) << 16) | (data[4] << 8) | data[5]
        temp = (temp_raw / 1048576.0) * 200 - 50
        
        return temp, humidity
        
    except Exception as e:
        print(f"Error reading temp/humidity: {e}")
        return None, None

# Add this function to handle sending data with error checking
def send_response(cs, response):
    try:
        cs.sendall(response)
    except OSError as e:
        if e.errno == 104:  # ECONNRESET
            print("Connection reset by peer")
        else:
            print(f"Error sending response: {e}")


if not init_camera():
    print("Camera initialization failed")
    raise RuntimeError('Camera initialization failed')

# Connect to Wi-Fi with retry mechanism
wifi = network.WLAN(network.STA_IF)
wifi.active(True)

# Define networks as a list of tuples for guaranteed order in MicroPython
networks = [
    (First_network, First_network_password),      # 10 West will try first
    (Second_network, Second_network_password),    # Starlink will try second
    (Third_network, Third_network_password),      # genechaser will try third
    (Fourth_network, Fourth_network_password)     # genemachine will try last
]

# Try connecting to each network in order
for ssid, password in networks:
    print(f"Trying to connect to {ssid} with password {password}...")
    display_message(f"Trying {ssid}")
    if connect_wifi(ssid, password):
        print(f"Successfully connected to {ssid}")
        display_message(f"Connected to {ssid}")
        break
else:  # This runs if no break occurred (no successful connection)
    error_msg = "Failed to connect to any network"
    print(error_msg)
    display_message(error_msg)
    raise RuntimeError(error_msg)

print('Connected to Wi-Fi')
print('Network config:', wifi.ifconfig())

# After connecting to Wi-Fi and before the TCP server setup
ip = wifi.ifconfig()[0]
url = f"http://{ip}"
oled.fill(0)
oled.text(f"Connect to:", 0, 0)
oled.text(f"{ip}", 0, 10)
oled.show()

# Start the pump worker thread
_thread.start_new_thread(pump_worker, ())

# TCP server setup
port = 80
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # Allow reuse of the address
s.bind(('0.0.0.0', port))
s.listen(5)
print(f"Server listening on {wifi.ifconfig()[0]}:{port}")
oled.text(f"Server listening on {wifi.ifconfig()[0]}:{port}", 0, 20)
oled.show()

print("Starting main loop")
oled.text(f"Starting main loop", 0, 30)
oled.show()

last_activity = time.time()
loop_counter = 0
last_cmd = "idle"
last_cmd_time = time.time()
cs = None
message = ""
while True:
    try:
        loop_counter += 1
        current_time = time.time()
        
        if loop_counter % 10 == 0:
            read_and_display_analog()   

        if loop_counter % 100 == 0:  # Log every 100 iterations
            print(f"Main loop iteration {loop_counter}, uptime: {current_time - last_activity:.2f}s")
            print(f"Free memory: {gc.mem_free()} bytes")
            display_status() 
        
        if pump_status['display_update']:
            with status_lock:
                message = pump_status['message']  # Get message while locked
                print(f"Display update: {message}")
                display_message(message)
                pump_status['display_update'] = False
                
        s.settimeout(10.0)
        try:        
            cs, ca = s.accept()
        except OSError as e:
            if e.errno == 110:  # ETIMEDOUT
                continue
            print(f'Error accepting connection: {e}')
            continue
        
        cs.settimeout(5)  # 5 seconds timeout
       
        request = cs.recv(1024).decode()

        if 'GET / ' in request:
            response = "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n" + main_page()
            send_response(cs, response.encode())
        elif 'GET /capture' in request:
            frame = camera.capture()
            response = b'HTTP/1.1 200 OK\r\nContent-Type: image/jpeg\r\nConnection: close\r\n\r\n' + frame
            send_response(cs, response)
        elif 'GET /distance' in request:
            sensor_data = []
            for i, pin in enumerate(analog_pins):
                value = pin.read_u16() >> 4  # Using same conversion as in display function
                sensor_data.append(f"A{i}: {value}")
           
            temperature, humidity = read_temp_humidity()
            sensor_data.append(f"T: {temperature:.1f}C H: {humidity:.1f}%")
            #distance = get_distance(trigger, echo) #inactive until we add ultrasound
            #height = 100 - distance
            height = "offline"
            sensor_data.append(f"Height: {height}")
            with status_lock:
                if pump_status['message']:
                    update_display = pump_status['message']
                else:
                    update_display = "No new message"
            response = f"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nConnection: close\r\n\r\n{update_display} | {' | '.join(sensor_data)}"
            send_response(cs, response.encode())
            
        elif 'GET /command' in request:
            try:
                cmd = request.split('cmd=')[1].split(' ')[0]  # Get the raw command
                print(f"Processing command: {cmd}")  # Debug print
                response_msg = process_command(cmd)
                print(f"Response message: {response_msg}")
                response = f"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nConnection: close\r\n\r\n{response_msg}"
                send_response(cs, response.encode())
            except Exception as e:
                print(f"Error processing command: {e}")
                response = f"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nConnection: close\r\n\r\nError: {str(e)}"
                send_response(cs, response.encode())
        else:
            print("Invalid request, sending 404")
            send_response(cs, b'HTTP/1.1 404 Not Found\r\n\r\nInvalid Request')
        
        #print("Request processed successfully")
        
    except Exception as e:
        print(f'Error in main loop: {e}')
        
    finally:
        if cs:
            #print("Closing connection...")
            cs.close()
        gc.collect()
   
    if time.time() - last_cmd_time > 10:
        last_cmd = "idle"
    
