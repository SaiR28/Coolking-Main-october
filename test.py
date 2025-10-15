#!/usr/bin/env python3
"""
Coolking Temperature Monitor - ESP32 API Test Script
This script simulates ESP32 temperature sensor data transmission to test the API endpoint.
"""

import requests
import json
import time
import random
from datetime import datetime

# Server Configuration
SERVER_URL = "https://coolkingengineering.in/api/data"
# API Key bypassed for testing (commented out)
# API_KEY = "Cool2814"

# Test Configuration
TEST_ESP32_MAC = "AA:BB:CC:DD:EE:FF"  # Simulated ESP32 MAC address
TEST_SENSORS = [
    "289FBDBB4024BC6",   # Sensor 1 ID (continuous format like ESP32 sends)
    "28BBCCDDEE001122",  # Sensor 2 ID
    "28CCDDEE00112233",  # Sensor 3 ID
]

def generate_realistic_temperature():
    """Generate realistic cold room temperature readings."""
    # Normal cold room temperature range: -2°C to +8°C
    base_temp = random.uniform(-2.0, 8.0)
    # Add small random fluctuation
    fluctuation = random.uniform(-0.5, 0.5)
    return round(base_temp + fluctuation, 1)

def create_test_payload(num_sensors=3):
    """Create a test JSON payload matching ESP32 format."""
    readings = []

    for i in range(min(num_sensors, len(TEST_SENSORS))):
        sensor_id = TEST_SENSORS[i]
        temperature = generate_realistic_temperature()

        readings.append({
            "sensor_id": sensor_id,
            "temperature": temperature
        })

    payload = {
        "esp32_mac": TEST_ESP32_MAC,
        "readings": readings
    }

    return payload

def send_test_data(payload, test_name="Test"):
    """Send test data to the Coolking server."""
    try:
        print(f"\n=== {test_name} ===")
        print(f"🚀 Sending to: {SERVER_URL}")
        print(f"📊 ESP32 MAC: {payload['esp32_mac']}")
        print(f"📈 Sensors: {len(payload['readings'])}")

        # Display sensor data
        for i, reading in enumerate(payload['readings'], 1):
            print(f"   Sensor {i}: {reading['sensor_id']} = {reading['temperature']}°C")

        # Prepare headers (no API key for testing)
        headers = {
            "Content-Type": "application/json"
            # "X-API-Key": API_KEY  # Commented out for testing
        }

        # Send POST request
        print(f"\n📤 Sending JSON payload...")
        print(f"📋 Payload: {json.dumps(payload, indent=2)}")

        response = requests.post(
            SERVER_URL,
            json=payload,
            headers=headers,
            timeout=10
        )

        # Process response
        print(f"\n📡 Response Status: {response.status_code}")

        try:
            response_json = response.json()
            print(f"📄 Response Body: {json.dumps(response_json, indent=2)}")
        except:
            print(f"📄 Response Body: {response.text}")

        if response.status_code == 200:
            print("✅ SUCCESS: Data sent successfully!")
            return True
        else:
            print(f"❌ ERROR: Server returned status {response.status_code}")
            return False

    except requests.exceptions.ConnectTimeout:
        print("❌ ERROR: Connection timeout - Check internet connection")
        return False
    except requests.exceptions.ConnectionError:
        print("❌ ERROR: Connection failed - Server may be down")
        return False
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        return False

def run_basic_test():
    """Run a basic single transmission test."""
    payload = create_test_payload(3)
    return send_test_data(payload, "Basic API Test")

def run_single_sensor_test():
    """Test with single sensor."""
    payload = create_test_payload(1)
    return send_test_data(payload, "Single Sensor Test")

def run_multi_sensor_test():
    """Test with multiple sensors."""
    payload = create_test_payload(3)
    return send_test_data(payload, "Multi-Sensor Test")

def run_continuous_test(duration_minutes=2, interval_seconds=30):
    """Run continuous data transmission test."""
    print(f"\n🔄 Starting continuous test for {duration_minutes} minutes...")
    print(f"⏱️  Sending data every {interval_seconds} seconds")

    start_time = time.time()
    end_time = start_time + (duration_minutes * 60)
    test_count = 0
    success_count = 0

    while time.time() < end_time:
        test_count += 1
        payload = create_test_payload(3)

        if send_test_data(payload, f"Continuous Test #{test_count}"):
            success_count += 1

        # Wait before next transmission
        remaining_time = end_time - time.time()
        if remaining_time > interval_seconds:
            print(f"\n⏳ Waiting {interval_seconds} seconds before next transmission...")
            time.sleep(interval_seconds)
        else:
            break

    print(f"\n📊 Continuous Test Results:")
    print(f"   Total Tests: {test_count}")
    print(f"   Successful: {success_count}")
    print(f"   Failed: {test_count - success_count}")
    print(f"   Success Rate: {(success_count/test_count)*100:.1f}%")

def test_invalid_payload():
    """Test server response to invalid payloads."""
    print("\n🧪 Testing invalid payloads...")

    # Test 1: Missing esp32_mac
    invalid_payload_1 = {
        "readings": [{"sensor_id": "28AABBCCDDEE0011", "temperature": 2.5}]
    }
    send_test_data(invalid_payload_1, "Invalid Test - Missing MAC")

    # Test 2: Missing readings
    invalid_payload_2 = {
        "esp32_mac": TEST_ESP32_MAC
    }
    send_test_data(invalid_payload_2, "Invalid Test - Missing Readings")

    # Test 3: Empty readings array
    invalid_payload_3 = {
        "esp32_mac": TEST_ESP32_MAC,
        "readings": []
    }
    send_test_data(invalid_payload_3, "Invalid Test - Empty Readings")

def main():
    """Main test function with interactive menu."""
    print("=" * 60)
    print("🌡️  COOLKING TEMPERATURE MONITOR - API TEST SCRIPT")
    print("=" * 60)
    print("This script simulates ESP32 temperature sensor data transmission")
    print("to test the Coolking server API endpoint.")
    print(f"🎯 Target Server: {SERVER_URL}")
    print(f"🔧 API Key: BYPASSED (Testing Mode)")
    print(f"📱 Simulated ESP32 MAC: {TEST_ESP32_MAC}")
    print(f"🌡️  Test Sensors: {len(TEST_SENSORS)}")

    while True:
        print(f"\n{'='*40}")
        print("📋 TEST OPTIONS:")
        print("1. Basic API Test (3 sensors)")
        print("2. Single Sensor Test")
        print("3. Multi-Sensor Test")
        print("4. Continuous Test (2 minutes)")
        print("5. Invalid Payload Tests")
        print("6. Custom Test")
        print("0. Exit")
        print(f"{'='*40}")

        try:
            choice = input("\n👉 Select test option (0-6): ").strip()

            if choice == '0':
                print("\n👋 Goodbye!")
                break
            elif choice == '1':
                run_basic_test()
            elif choice == '2':
                run_single_sensor_test()
            elif choice == '3':
                run_multi_sensor_test()
            elif choice == '4':
                run_continuous_test()
            elif choice == '5':
                test_invalid_payload()
            elif choice == '6':
                try:
                    num_sensors = int(input("Number of sensors (1-3): "))
                    if 1 <= num_sensors <= 3:
                        payload = create_test_payload(num_sensors)
                        send_test_data(payload, f"Custom Test - {num_sensors} Sensors")
                    else:
                        print("❌ Please enter 1, 2, or 3 sensors")
                except ValueError:
                    print("❌ Please enter a valid number")
            else:
                print("❌ Invalid option. Please try again.")

        except KeyboardInterrupt:
            print("\n\n⏹️  Test interrupted by user")
            break
        except Exception as e:
            print(f"❌ Unexpected error: {e}")

if __name__ == "__main__":
    main()