# Impossible Vines Hydroponics Controller

A MicroPython-based hydroponics control system designed for ESP32-S3 microcontrollers with integrated camera support. This system provides automated plant care through moisture sensing, scheduled watering, and remote monitoring capabilities.

## Features

- **Web Interface**: Browser-based control panel with live camera feed
- **Automated Watering**: Smart watering system based on moisture sensor readings
- **Multi-Sensor Support**: 
  - 4 moisture sensors
  - Temperature and humidity monitoring
  - Optional ultrasound distance sensor
- **OLED Display**: Real-time status updates and system information
- **Multi-Network Support**: Automatic connection to configured WiFi networks
- **Calibration System**: Easy sensor calibration for wet/dry thresholds
- **Safety Features**: 
  - Daily watering limits
  - Timeout protection
  - Error handling
  - Memory management

## Hardware Requirements

- ESP32-S3 Development Board (Seeed Studio)
- 2MP Camera Module
- SSD1306 OLED Display (I2C)
- Temperature/Humidity Sensor (I2C - 0x38)
- 4x Moisture Sensors (Analog)
- 4x Water Pumps
- Power Supply

### Pin Configuration

- **I2C**:
  - SCL: GPIO6
  - SDA: GPIO5
- **Moisture Sensors**:
  - Sensor 0: GPIO1 (ADC)
  - Sensor 1: GPIO2 (ADC)
  - Sensor 2: GPIO7 (ADC)
  - Sensor 3: GPIO4 (ADC)
- **Pump Control**:
  - Pump 0: GPIO3
  - Pump 1: GPIO8
  - Pump 2: GPIO9
  - Pump 3: GPIO44
- **Optional Ultrasound**:
  - Trigger: GPIO41
  - Echo: GPIO42

## Web Interface Commands

- `water [pump] [duration]`: Activate specific pump for set duration
  - Example: `water 1 30` (runs pump 1 for 30 seconds)
- `auto on/off`: Enable/disable automatic watering
- `status`: Display current system status
- `setwet [sensor] [value]`: Set moisture threshold for "wet" condition
- `setdry [sensor] [value]`: Set moisture threshold for "dry" condition
- `reset`: Reset all pump timeouts
- `calibrate [sensor]`: Start calibration process (optional sensor number)

## Installation

1. Flash MicroPython to your ESP32-S3
2. Upload all project files to the device
3. Configure WiFi credentials in the code:
   ```python
   First_network = "Your_SSID"
   First_network_password = "Your_Password"
   ```
4. Reset the device

## Network Configuration

The system attempts to connect to configured networks in the following order:
1. Primary Network
2. Secondary Network
3. Tertiary Network
4. Fallback Network

## Automatic Operation

When auto mode is enabled:
1. System monitors moisture levels
2. Triggers watering when sensors exceed "dry" threshold
3. Waters for configured duration
4. Implements cooling-off period
5. Monitors daily water usage limits
6. Applies safety timeouts if needed

## Safety Features

- Maximum daily watering limits
- 24-hour timeout after reaching limits
- Error handling for sensor failures
- Connection loss recovery
- Memory management and garbage collection

## Troubleshooting

- **Display shows "No I2C devices found"**: Check I2C connections and addresses
- **Camera fails to initialize**: Ensure camera module is properly connected
- **WiFi connection fails**: Verify credentials and signal strength
- **Pumps not activating**: Check GPIO connections and power supply
- **Sensor readings incorrect**: Run calibration process

## Contributing

Feel free to submit issues and pull requests to improve the system.

## License

This project is open source and available under the MIT License.

## Acknowledgments

- Based on MicroPython for ESP32
- Uses SSD1306 OLED library
- Implements ESP32-CAM functionality

## Version History

- Nov 12, 2024: Added temperature and humidity sensor support
- Nov 11, 2024: Added automatic calibration
- Nov 9, 2024: Added analog input and vine control
- Sept 30, 2024: Added OLED display
- Sept 13, 2024: Fixed ultrasound timing
- Sept 12, 2024: Added movement commands
- Sept 1, 2024: Initial release
