from flask import Flask, render_template_string, request, redirect, url_for
from bmp280 import BMP280
from smbus2 import SMBus
import time
import threading

# Initialize I2C and BMP280
bus = SMBus(1)
bmp280 = BMP280(i2c_dev=bus, i2c_addr=0x77)

# Shared sensor readings
temperature = 0.0
pressure = 0.0
altitude = 0.0
reference_altitude = None

# Flask app
app = Flask(__name__)

# HTML Template
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Raspberry Pi Sensor Readings</title>
</head>
<body>
    <h1>Sensor Readings</h1>
    <p><strong>Temperature:</strong> {{ temperature }} °C</p>
    <p><strong>Pressure:</strong> {{ pressure }} hPa</p>
    <p><strong>Altitude:</strong> {{ altitude }} m</p>
    <form method="POST" action="/set_reference">
        <button type="submit">Set Altitude Reference</button>
    </form>
</body>
</html>
'''

def read_sensor():
    global temperature, pressure, altitude
    while True:
        temperature = round(bmp280.get_temperature(), 2)
        pressure = round(bmp280.get_pressure(), 2)
        # Calculate altitude using the barometric formula
        sea_level_pressure = 1013.25  # hPa
        altitude = round(44330.0 * (1.0 - (pressure / sea_level_pressure) ** (1/5.255)), 2)
        time.sleep(0.5)

@app.route('/')
def index():
    relative_altitude = altitude
    if reference_altitude is not None:
        relative_altitude = round(altitude - reference_altitude, 2)
    return render_template_string(HTML_TEMPLATE,
                                  temperature=temperature,
                                  pressure=pressure,
                                  altitude=relative_altitude)

@app.route('/set_reference', methods=['POST'])
def set_reference():
    global reference_altitude
    reference_altitude = altitude
    return redirect(url_for('index'))

if __name__ == '__main__':
    sensor_thread = threading.Thread(target=read_sensor)
    sensor_thread.daemon = True
    sensor_thread.start()
    app.run(host='0.0.0.0', port=5000)
