import paho.mqtt.client as mqtt
import json
import time
import random
import threading

MQTT_BROKER = 'broker.hivemq.com'
MQTT_PORT = 1883
PATIENTS = ['patient1', 'patient2', 'patient3']

client = mqtt.Client()
client.connect(MQTT_BROKER, MQTT_PORT, 60)

def send_patient_data(patient_id):
    while True:
        fake_data = {
            "heartRate": random.randint(60, 100),
            "accelX": round(random.uniform(-1, 1), 2),
            "accelY": round(random.uniform(-1, 1), 2),
            "accelZ": round(random.uniform(9, 10), 2),
            "temperatureC": round(random.uniform(36.0, 37.5), 1),
            "spo2": random.randint(95, 100)
        }
        topic = f"zsa/sensor/{patient_id}"
        client.publish(topic, json.dumps(fake_data))
        print(f"Sent data for {patient_id}: {fake_data}")
        time.sleep(2)

# Run each patient in its own thread
for patient in PATIENTS:
    thread = threading.Thread(target=send_patient_data, args=(patient,), daemon=True)
    thread.start()

# Keep the main program running
while True:
    time.sleep(1)