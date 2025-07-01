# Required libraries:
# pip install flask flask-socketio eventlet matplotlib smbus2 bmp280

from flask import Flask, render_template_string, request
from flask_socketio import SocketIO
from smbus2 import SMBus
from bmp280 import BMP280
import threading
import time
import eventlet
import math

# Initialize BMP280
bus = SMBus(1)
bmp280 = BMP280(i2c_dev=bus, i2c_addr=0x77)
bmp280.setup()

# Globals
reference_altitude = None
temperature_history = []
altitude_history = []
time_history = []

app = Flask(__name__)
socketio = SocketIO(app)

def calculate_altitude(pressure, sea_level_pressure=1013.25):
    return 44330.0 * (1.0 - (pressure / sea_level_pressure) ** (1/5.255))

def sensor_thread():
    while True:
        temperature = bmp280.get_temperature()
        pressure = bmp280.get_pressure()
        altitude = calculate_altitude(pressure)

        global reference_altitude
        relative_altitude = altitude - reference_altitude if reference_altitude is not None else 0.0

        timestamp = time.time()
        temperature_history.append((timestamp, temperature))
        altitude_history.append((timestamp, relative_altitude))
        time_history.append(timestamp)

        # Keep only last 2 hours
        cutoff = timestamp - 7200
        temperature_history[:] = [(t, v) for t, v in temperature_history if t >= cutoff]
        altitude_history[:] = [(t, v) for t, v in altitude_history if t >= cutoff]

        socketio.emit('sensor_update', {
            'temperature': temperature,
            'pressure': pressure,
            'altitude': altitude,
            'relative_altitude': relative_altitude,
            'temperature_history': temperature_history,
            'altitude_history': altitude_history,
        })
        socketio.sleep(1)

@app.route('/')
def index():
    return render_template_string(PAGE_HTML)

@socketio.on('set_reference')
def handle_set_reference():
    global reference_altitude
    pressure = bmp280.get_pressure()
    reference_altitude = calculate_altitude(pressure)

@socketio.on('set_baro_offset')
def handle_baro_offset():
    print("BARO_ALT_OFFSET called (placeholder)")

PAGE_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>BMP280 Dashboard</title>
    <script src="https://cdn.socket.io/4.6.1/socket.io.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body>
    <h1>Live Sensor Data</h1>
    <div>Temperature: <span id="temp">--</span> °C</div>
    <div>Pressure: <span id="press">--</span> hPa</div>
    <div>Altitude: <span id="alt">--</span> m</div>
    <div>Relative Altitude: <span id="ralt">--</span> m</div>
    <button onclick="socket.emit('set_reference')">Set Reference Altitude</button>
    <button onclick="socket.emit('set_baro_offset')">Set BARO_ALT_OFFSET</button>

    <h2>Temperature over Time</h2>
    <canvas id="tempChart"></canvas>

    <h2>Altitude over Time</h2>
    <canvas id="altChart"></canvas>

    <script>
        const socket = io();
        const tempDisplay = document.getElementById('temp');
        const pressDisplay = document.getElementById('press');
        const altDisplay = document.getElementById('alt');
        const raltDisplay = document.getElementById('ralt');

        const tempChart = new Chart(document.getElementById('tempChart'), {
            type: 'line',
            data: { labels: [], datasets: [{ label: 'Temperature', data: [], borderColor: 'red' }] },
            options: { scales: { x: { type: 'time', time: { unit: 'minute' } } } }
        });

        const altChart = new Chart(document.getElementById('altChart'), {
            type: 'line',
            data: { labels: [], datasets: [{ label: 'Altitude', data: [], borderColor: 'blue' }] },
            options: { scales: { x: { type: 'time', time: { unit: 'minute' } } } }
        });

        socket.on('sensor_update', data => {
            tempDisplay.textContent = data.temperature.toFixed(2);
            pressDisplay.textContent = data.pressure.toFixed(2);
            altDisplay.textContent = data.altitude.toFixed(2);
            raltDisplay.textContent = data.relative_altitude.toFixed(2);

            const tempData = data.temperature_history.map(p => ({ x: p[0]*1000, y: p[1] }));
            const altData = data.altitude_history.map(p => ({ x: p[0]*1000, y: p[1] }));
            tempChart.data.labels = tempData.map(p => p.x);
            tempChart.data.datasets[0].data = tempData;
            altChart.data.labels = altData.map(p => p.x);
            altChart.data.datasets[0].data = altData;
            tempChart.update();
            altChart.update();
        });
    </script>
</body>
</html>
'''

if __name__ == '__main__':
    thread = threading.Thread(target=sensor_thread)
    thread.daemon = True
    thread.start()
    socketio.run(app, host='0.0.0.0', port=5000)
