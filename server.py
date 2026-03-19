import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO
from flask_mail import Mail, Message
import threading
import json
import paho.mqtt.client as mqtt
import numpy as np
import pickle
from collections import deque
from datetime import datetime

# --- Try to import TensorFlow, fall back gracefully ---
try:
    import tensorflow as tf
    TF_AVAILABLE = True
except ImportError:
    TF_AVAILABLE = False
    print("⚠️  TensorFlow niet gevonden, AI-voorspelling uitgeschakeld.")

MQTT_ALERT_TOPIC = 'zsa/sensor/alerts'
MQTT_BROKER = 'broker.hivemq.com'
MQTT_PORT = 1883
MQTT_TOPIC = 'zsa/sensor/data'
PATIENTS = ['patient1', 'patient2', 'patient3']
MQTT_TOPIC_BASE = 'zsa/sensor'

patient_data = {p: None for p in PATIENTS}
patient_buffers = {p: deque(maxlen=5) for p in PATIENTS}

app = Flask(__name__)
app.config['SECRET_KEY'] = 'wristly-secret'          # FIXED: SocketIO requires a secret key
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# --- Flask-Mail ---
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'teamzsa2025@gmail.com'
app.config['MAIL_PASSWORD'] = ''   # Fill in your app password
app.config['MAIL_DEFAULT_SENDER'] = 'teamzsa2025@gmail.com'
mail = Mail(app)

fall_log_history = []
latest_data = None
last_heart_rate = '--'
sensor_data_buffer = deque(maxlen=5)
userEmail = ''

# --- AI Model ---
model = None
scaler = None
label_mapping = {}

if TF_AVAILABLE:
    try:
        model = tf.keras.models.load_model('my_model.h5')
        with open('scaler.pkl', 'rb') as f:
            scaler = pickle.load(f)
        with open('label_map.json', 'r') as f:
            raw_label_map = json.load(f)
            label_mapping = {int(k): v for k, v in raw_label_map.items()}
        print("✅ AI Model en Scaler succesvol geladen!")
    except Exception as e:
        print(f"⚠️  AI niet geladen (model-bestanden ontbreken?): {e}")


def send_email(subject, recipient, body):
    try:
        msg = Message(subject, recipients=[recipient])
        msg.body = body
        with app.app_context():
            mail.send(msg)
        print(f"📧 Mail verstuurd naar {recipient}")
    except Exception as e:
        print(f"📧 Mail fout: {e}")


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("✅ MQTT verbonden")
        client.subscribe(MQTT_ALERT_TOPIC)
        for patient in PATIENTS:
            client.subscribe(f"{MQTT_TOPIC_BASE}/{patient}")
            print(f"📡 Subscribed to {MQTT_TOPIC_BASE}/{patient}")
    else:
        print(f"❌ MQTT verbinding mislukt, code: {rc}")


def on_message(client, userdata, msg):
    global latest_data, userEmail
    try:
        topic = msg.topic
        data = json.loads(msg.payload.decode('utf-8'))
        patient_id = topic.split('/')[-1]
        data['patient_id'] = patient_id

        # --- ALERT topic ---
        if topic == MQTT_ALERT_TOPIC:
            print("🚨 VAL GEDETECTEERD:", data)
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            heartRate = data.get('heartRate', '--')

            # Emit alert to main dashboard
            socketio.emit('alert', {"status": "FALL_DETECTED"})

            # FIXED: Emit fall_log so special.html also receives it
            socketio.emit('fall_log', {
                "timestamp": timestamp,
                "spo2": spo2
            })

            if userEmail:
                send_email(
                    "🚨 VAL GEDETECTEERD!",
                    userEmail,
                    f"Er is een val gedetecteerd op: {timestamp}\nSpO2 op moment van val: {spo2}%"
                )
            return

        # --- Normal sensor data ---
        latest_data = data
        sensor_data_buffer.append(data)
        last_heart_rate = data.get('heartRate',)
        prediction_label = "Buffer vullen..."

        if model and scaler and len(sensor_data_buffer) == sensor_data_buffer.maxlen:
            hr = np.array([d.get('heartRate', 0) for d in sensor_data_buffer])
            ax = np.array([d.get('accelX', 0) for d in sensor_data_buffer])
            ay = np.array([d.get('accelY', 0) for d in sensor_data_buffer])
            az = np.array([d.get('accelZ', 0) for d in sensor_data_buffer])

            features = np.array([
                np.mean(hr), np.std(hr),
                np.mean(ax), np.mean(ay), np.mean(az),
                np.std(ax), np.std(ay), np.std(az)
            ]).reshape(1, -1)

            scaled = scaler.transform(features)
            prediction_prob = model.predict(scaled)[0]
            prediction_label = label_mapping.get(np.argmax(prediction_prob), "Onbekend")

            prediction_label = label_mapping.get(np.argmax(prediction_prob), "Onbekend")

            if prediction_label == 'fall':
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                spo2 = data.get('spo2', '--')
                fall_entry = {
                    "timestamp": timestamp,
                    "spo2": spo2
                }
                fall_log_history.append(fall_entry)
                socketio.emit('alert', {"status": "FALL_DETECTED"})
                socketio.emit('fall_log', fall_entry)
                if userEmail:
                    send_email(
                        "🚨 VAL GEDETECTEERD!",
                        userEmail,
                        f"Val gedetecteerd op: {timestamp}\nSpO2: {spo2}%"
                    )

        data['prediction'] = prediction_label
        data['buffer_length'] = len(sensor_data_buffer)
        print(f"📤 Emitting mqtt_data to browser: HR={data.get('heartRate')}")
        socketio.emit('mqtt_data', data)
        print(f"✅ Emit done")

    except Exception as e:
        print(f"🚫 MQTT Fout: {e}")


# --- Routes ---
@app.route('/')
def index():
    return render_template('index.html')

# FIXED: Added route for special.html
@app.route('/special')
def special():
    return render_template('special.html')

@app.route('/submit_feedback', methods=['POST'])
def submit_feedback():
    fb = request.json
    global userEmail
    userEmail = fb.get('email', '')
    with open('feedback.txt', 'a') as f:
        f.write(
            f"Naam: {fb.get('name')}, Email: {userEmail}, "
            f"Feedback: {fb.get('feedback')}, Rating: {fb.get('rating')}\n"
        )
    return jsonify({"message": "Bedankt!"}), 200


if __name__ == '__main__':
    mqtt_client = mqtt.Client()
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message

    try:
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        threading.Thread(target=mqtt_client.loop_forever, daemon=True).start()
        print("✅ MQTT thread gestart")
    except Exception as e:
        print(f"⚠️  MQTT verbinding mislukt: {e} — server start toch.")

    print("🌐 Server draait op: http://localhost:8000")
    print("📊 Dashboard:    http://localhost:8000/")
    print("📋 Val logging:  http://localhost:8000/special")
    print("🔴 Stop met:     Ctrl+C")
    socketio.run(app, debug=False, host='0.0.0.0', port=8000)
