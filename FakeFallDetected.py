"""
FakeData.py — Simulates sensor data and fall alerts over MQTT.

Usage:
    python FakeData.py            → sends normal sensor data every 2s
    python FakeData.py --fall     → sends one fall alert immediately, then normal data
    python FakeData.py --loop     → sends normal data, and a fall every 15s

Install dependency if needed:
    pip install paho-mqtt
"""

import json
import time
import random
import argparse
from datetime import datetime
import paho.mqtt.client as mqtt

MQTT_BROKER = 'broker.hivemq.com'
MQTT_PORT = 1883
MQTT_TOPIC = 'zsa/sensor/data'
MQTT_ALERT_TOPIC = 'zsa/sensor/alerts'


def make_sensor_data():
    """Generate realistic-looking fake sensor data."""
    return {
        "heartRate": random.randint(60, 100),
        "spo2": random.randint(94, 100),
        "temperatureC": round(random.uniform(36.0, 37.5), 1),
        "accelX": round(random.uniform(-0.3, 0.3), 3),
        "accelY": round(random.uniform(-0.3, 0.3), 3),
        "accelZ": round(random.uniform(0.85, 1.15), 3),
        "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }


def make_fall_data():
    """Generate a fake fall alert payload."""
    return {
        "spo2": random.randint(88, 95),
        "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "event": "FALL"
    }


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("✅ Verbonden met MQTT broker")
    else:
        print(f"❌ MQTT verbinding mislukt, code: {rc}")


def send_normal_data(client):
    data = make_sensor_data()
    payload = json.dumps(data)
    client.publish(MQTT_TOPIC, payload)
    print(f"📡 Sensordata verstuurd: {data}")


def send_fall_alert(client):
    data = make_fall_data()
    payload = json.dumps(data)
    client.publish(MQTT_ALERT_TOPIC, payload)
    print(f"🚨 Val alert verstuurd: {data}")


def main():
    parser = argparse.ArgumentParser(description='Wristly Fake Data Publisher')
    parser.add_argument('--fall', action='store_true', help='Stuur meteen een val alert')
    parser.add_argument('--loop', action='store_true', help='Stuur elke 15s een val')
    args = parser.parse_args()

    client = mqtt.Client()
    client.on_connect = on_connect
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_start()

    time.sleep(1)  # Wait for connection

    print("🟢 FakeData.py gestart — druk Ctrl+C om te stoppen\n")

    counter = 0
    try:
        while True:
            send_normal_data(client)

            if args.fall and counter == 0:
                time.sleep(1)
                send_fall_alert(client)

            if args.loop and counter > 0 and counter % 20 == 0:
                send_fall_alert(client)

            counter += 1
            time.sleep(2)

    except KeyboardInterrupt:
        print("\n🔴 Gestopt.")
        client.loop_stop()
        client.disconnect()


if __name__ == '__main__':
    main()
