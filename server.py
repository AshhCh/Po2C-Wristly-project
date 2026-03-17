from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO
from flask_mail import Mail, Message
import threading
import json
import paho.mqtt.client as mqtt
import tensorflow as tf
import numpy as np
import pickle
from collections import deque

from dotenv import load_dotenv
import os
load_dotenv()

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# Configure Flask-Mail
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = 'teamzsa2025@gmail.com'  # Default sender

mail = Mail(app)

# Instead of one topic, Multiple patiens are defined, each with their own topic and data buffer
PATIENTS = ['patient1', 'patient2', 'patient3']
MQTT_TOPIC_BASE = 'zsa/sensor'

# Separate data storage for each patient to avoid overwriting and ensure accurate predictions
patient_data = {p: None for p in PATIENTS}
patient_buffers = {p: deque(maxlen=5) for p in PATIENTS}

MQTT_BROKER = 'broker.hivemq.com'
MQTT_PORT = 1883
MQTT_TOPIC = 'zsa/sensor/data'

latest_data = None
sensor_data_buffer = deque(maxlen=5)
userEmail = ''  # Global variable to store user email

# --- AI Model and Scaler Loading ---
model = None
scaler = None
label_mapping = {}

try:
    model = tf.keras.models.load_model('my_model.h5')
    with open('scaler.pkl', 'rb') as f:
        scaler = pickle.load(f)
    print("✅ AI Model and StandardScaler loaded successfully!")

    with open('label_map.json', 'r') as f:
        raw_label_map = json.load(f)
        label_mapping = {int(k): v for k, v in raw_label_map.items()}
    print(f"✅ Label map loaded: {label_mapping}")

except Exception as e:
    print(f"🚫 Error loading AI Model, StandardScaler, or Label Map: {e}")
    model = None
    scaler = None
    label_mapping = {}

# Email sending function
def send_email(subject, recipient, body):
    msg = Message(subject, recipients=[recipient])
    msg.body = body
    with app.app_context():
        mail.send(msg)

# MQTT callbacks UPDATED FOR MULTIPLE PATIENTS
def on_connect(client, userdata, flags, rc):
    print("✅ MQTT connected with result code", rc)
    for patient in PATIENTS:
        client.subscribe(f"{MQTT_TOPIC_BASE}/{patient}")
        print(f"📡 Subscribed to {MQTT_TOPIC_BASE}/{patient}")

def on_message(client, userdata, msg):
    global patient_data
    try:
        # Figure out which patient this data belongs to
        patient_id = msg.topic.split('/')[-1]
        data = json.loads(msg.payload.decode('utf-8'))
        data['patient_id'] = patient_id
        patient_data[patient_id] = data
        patient_buffers[patient_id].append(data)
        
        socketio.emit('mqtt_data', data)
        print(f"📦 Received data for {patient_id}: {data}")
    except Exception as e:
        print(f"🚫 MQTT message error: {e}")

        if model and scaler and len(sensor_data_buffer) == sensor_data_buffer.maxlen:
            heart_rates = np.array([d.get('heartRate', 0) for d in sensor_data_buffer])
            accel_x_values = np.array([d.get('accelX', 0) for d in sensor_data_buffer])
            accel_y_values = np.array([d.get('accelY', 0) for d in sensor_data_buffer])
            accel_z_values = np.array([d.get('accelZ', 0) for d in sensor_data_buffer])

            heart_mean = np.mean(heart_rates)
            heart_std = np.std(heart_rates)
            accel_x_mean = np.mean(accel_x_values)
            accel_y_mean = np.mean(accel_y_values)
            accel_z_mean = np.mean(accel_z_values)
            accel_x_std = np.std(accel_x_values)
            accel_y_std = np.std(accel_y_values)
            accel_z_std = np.std(accel_z_values)

            features_for_prediction = np.array([
                heart_mean, heart_std,
                accel_x_mean, accel_y_mean, accel_z_mean,
                accel_x_std, accel_y_std, accel_z_std
            ]).reshape(1, -1)

            scaled_features = scaler.transform(features_for_prediction)
            prediction_prob = model.predict(scaled_features)[0]
            prediction_class = np.argmax(prediction_prob)
            prediction_label = label_mapping.get(prediction_class, "Unknown Prediction")

            # Check for fall or seizure predictions
            if prediction_label in ['fall', 'seizure'] and userEmail:
                send_email(
                    subject=f"Alert: {prediction_label.capitalize()} Detected!",
                    recipient=userEmail,  # Use the captured email address
                    body=f"A {prediction_label} has been detected based on the latest sensor data."
                )

            print(f"🤖 Prediction: Probabilities={prediction_prob}, Class={prediction_class}, Label={prediction_label}")
        else:
            print("AI model or scaler not loaded or buffer not full, skipping prediction.")
            if not model or not scaler:
                sensor_data_buffer.clear()

        data['prediction'] = prediction_label
        data['buffer_length'] = len(sensor_data_buffer)

        print(f"DEBUG: Data dictionary before emitting: {data}")
        socketio.emit('mqtt_data', data)
    except Exception as e:
        print(f"🚫 MQTT message error: {e}")
        socketio.emit('mqtt_error', {'message': str(e), 'raw_data': msg.payload.decode('utf-8')})

@socketio.on('connect')
def handle_connect():
    print("🔌 Browser connected via SocketIO")
    if latest_data:
        temp_data = latest_data.copy()
        temp_data['prediction'] = "Waiting for data window..."
        temp_data['buffer_length'] = len(sensor_data_buffer)
        print("📤 Sending cached data to client")
        socketio.emit('mqtt_data', temp_data)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/submit_feedback', methods=['POST'])
def submit_feedback():
    feedback_data = request.json
    name = feedback_data.get('name')
    global userEmail  # Use the global variable to store the email
    userEmail = feedback_data.get('email')  # Get the email address
    feedback = feedback_data.get('feedback')
    rating = feedback_data.get('rating')

    # Save feedback to a text file
    with open('feedback.txt', 'a') as f:
        f.write(f"Name: {name}, Email: {userEmail}, Feedback: {feedback}, Rating: {rating}\n")

    return jsonify({"message": "Thank you for your feedback!"}), 200

if __name__ == '__main__':
    mqtt_client = mqtt.Client()
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)

    threading.Thread(target=mqtt_client.loop_forever, daemon=True).start()
    socketio.run(app, debug=False, host='0.0.0.0', port=8000)
