import paho.mqtt.client as mqtt
import json
import time
import random

MQTT_BROKER = 'broker.hivemq.com'
MQTT_PORT = 1883
MQTT_TOPIC = 'zsa/sensor/data'

client = mqtt.Client()
client.connect(MQTT_BROKER, MQTT_PORT, 60)

print("Sending fake Wristly data...")

while True:
    fake_data = {
        "heartRate": random.randint(60, 100),
        "accelX": round(random.uniform(-1, 1), 2),
        "accelY": round(random.uniform(-1, 1), 2),
        "accelZ": round(random.uniform(9, 10), 2),
        "temperatureC": round(random.uniform(36.0, 37.5), 1),
        "spo2": random.randint(95, 100),
    }

    client.publish(MQTT_TOPIC, json.dumps(fake_data))
    print("Sent:", fake_data)
    time.sleep(2)