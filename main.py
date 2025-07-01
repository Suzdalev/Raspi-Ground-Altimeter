# Required libraries:
# pip install flask flask-sock eventlet matplotlib smbus2 bmp280

from flask import Flask, render_template_string, request
from flask_sock import Sock
from smbus2 import SMBus
from bmp280 import BMP280
import threading
import time
import math
import json

# Initialize I2C bus for BMP280
bus_bmp = SMBus(1)
bmp280 = BMP280(i2c_dev=bus_bmp, i2c_addr=0x77)
bmp280.setup()

# Globals
reference_altitude = None
temperature_history = []
altitude_history = []
time_history = []

app = Flask(__name__)
sock = Sock(app)
clients = []

def calculate_altitude(pressure, sea_level_pressure=1013.25):
    return 44330.0 * (1.0 - (pressure / sea_level_pressure) ** (1/5.255))

def sensor_thread():
    while True:
        try:
            temperature = round(bmp280.get_temperature(), 1)
            pressure = bmp280.get_pressure()
            altitude = round(calculate_altitude(pressure), 1)

            global reference_altitude
            relative_altitude = round(altitude - reference_altitude, 1) if reference_altitude is not None else 0.0

            timestamp = time.time()
            temperature_history.append((timestamp, temperature))
            altitude_history.append((timestamp, relative_altitude))

            # Keep only last 2 hours
            cutoff = timestamp - 7200
            temperature_history[:] = [(t, v) for t, v in temperature_history if t >= cutoff]
            altitude_history[:] = [(t, v) for t, v in altitude_history if t >= cutoff]

            json_data = json.dumps({
                'temperature': temperature,
                'pressure': pressure,
                'altitude': altitude,
                'relative_altitude': relative_altitude,
                'temperature_history': temperature_history,
                'altitude_history': altitude_history,
            })

            for ws in clients[:]:
                try:
                    ws.send(json_data)
                except:
                    clients.remove(ws)
        except Exception as e:
            print("Sensor read error:", e)

        time.sleep(1)

@app.route('/')
def index():
    return render_template_string(PAGE_HTML)

@sock.route('/ws')
def websocket(ws):
    clients.append(ws)
    while True:
        try:
            msg = ws.receive()
            if msg == 'set_reference':
                global reference_altitude
                pressure = bmp280.get_pressure()
                reference_altitude = calculate_altitude(pressure)
            elif msg == 'set_baro_offset':
                print("BARO_ALT_OFFSET called (placeholder)")
        except:
            break

PAGE_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>BMP280 Dashboard</title>
    <script>
        let socket;
        let tempChart, altChart;

        function initCharts() {
            const ctxAlt = document.getElementById('altChart').getContext('2d');
            const ctxTemp = document.getElementById('tempChart').getContext('2d');

            altChart = new Chart(ctxAlt, {
                type: 'line',
                data: { labels: [], datasets: [{ label: 'Altitude', data: [], borderColor: 'blue' }] },
                options: { scales: { x: { type: 'time', time: { unit: 'minute' }, title: { display: true, text: 'Local Time' } } } }
            });

            tempChart = new Chart(ctxTemp, {
                type: 'line',
                data: { labels: [], datasets: [{ label: 'Temperature', data: [], borderColor: 'red' }] },
                options: { scales: { x: { type: 'time', time: { unit: 'minute' }, title: { display: true, text: 'Local Time' } } } }
            });
        }

        function connect() {
            socket = new WebSocket('ws://' + window.location.host + '/ws');
            socket.onmessage = function(event) {
                const data = JSON.parse(event.data);
                document.getElementById('temp').textContent = data.temperature.toFixed(1);
                document.getElementById('press').textContent = data.pressure.toFixed(2);
                document.getElementById('alt').textContent = data.altitude.toFixed(1);
                document.getElementById('ralt').textContent = data.relative_altitude.toFixed(1);

                const tempData = data.temperature_history.map(p => ({ x: new Date(p[0]*1000), y: p[1] }));
                const altData = data.altitude_history.map(p => ({ x: new Date(p[0]*1000), y: p[1] }));

                tempChart.data.datasets[0].data = tempData;
                altChart.data.datasets[0].data = altData;
                tempChart.update();
                altChart.update();
            };
        }

        function sendCommand(cmd) {
            socket.send(cmd);
        }

        window.onload = function() {
            initCharts();
            connect();
        }
    </script>
    <script src="/static/chart.min.js"></script>
</head>
<body>
    <h1>Live Sensor Data</h1>
    <div>Temperature: <span id="temp">--</span> °C</div>
    <div>Pressure: <span id="press">--</span> hPa</div>
    <div>Altitude: <span id="alt">--</span> m</div>
    <div>Relative Altitude: <span id="ralt">--</span> m</div>
    <button onclick="sendCommand('set_reference')">Set Reference Altitude</button>
    <button onclick="sendCommand('set_baro_offset')">Set BARO_ALT_OFFSET</button>

    <h2>Altitude over Time</h2>
    <canvas id="altChart"></canvas>

    <h2>Temperature over Time</h2>
    <canvas id="tempChart"></canvas>
</body>
</html>
'''

if __name__ == '__main__':
    thread = threading.Thread(target=sensor_thread)
    thread.daemon = True
    thread.start()
    app.run(host='0.0.0.0', port=5000)
