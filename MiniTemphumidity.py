# JMR 11/12/24 mini temp humidity sensor AHT10 can change address if needed to 0x39
import time
from machine import I2C, Pin

# Deinitialize pins
for pin_num in range(45):  # ESP32-CAM has pins 0-44
    try:
        pin = Pin(pin_num)
        pin.init(Pin.IN)  # Reset to input mode
    except:
        pass  # Skip pins that can't be accessed

i2c = I2C(1, scl=Pin(6), sda=Pin(5), freq=100000)
SENSOR_ADDR = 0x38

# Scan for I2C devices (optional, for debugging)
print("Scanning I2C bus...")
devices = i2c.scan()
if devices:
    for device in devices:
        print(f"I2C device found at address: 0x{device:02X}")
else:
    print("No I2C devices found")

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
    
if __name__ == "__main__":
    for i in range(10):
        temperature, humidity = read_temp_humidity()
        print(f"Temperature: {temperature:.1f}C, Humidity: {humidity:.1f}%")
        time.sleep(1)
