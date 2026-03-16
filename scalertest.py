import pickle
import os

scaler_path = 'scaler.pkl'

try:
    with open(scaler_path, 'rb') as f: # Note 'rb' for read binary
        scaler = pickle.load(f)
    print("✅ scaler.pkl loaded successfully in test script!")
    print("Type of loaded object:", type(scaler))
except Exception as e:
    print(f"🚫 Error loading scaler.pkl in test script: {e}")
    print("The file might be corrupted or not a valid pickle file.")

if os.path.exists(scaler_path):
    print(f"Size of {scaler_path}: {os.path.getsize(scaler_path)} bytes")
else:
    print(f"{scaler_path} not found.")