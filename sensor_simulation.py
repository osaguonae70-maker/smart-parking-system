import requests
import random
import time
import json

API_BASE = "http://127.0.0.1:5000"
SENSOR_UPDATE_URL = f"{API_BASE}/sensor-update"
SLOTS_URL = f"{API_BASE}/api/slots"
SIMULATION_REFRESH_SECONDS = 3

def simulate_sensors():
    print("--- Starting IoT Sensor Simulation ---")
    print("Press Ctrl+C to stop simulation.")
    
    while True:
        try:
            slots_response = requests.get(SLOTS_URL, timeout=5)
            slots_response.raise_for_status()
            slots = slots_response.json()

            simulated_occupied_slots = [s for s in slots if s.get('zone') == 'simulation' and s.get('is_occupied')]
            releases_to_do = min(len(simulated_occupied_slots), random.randint(1, 3))

            random.shuffle(simulated_occupied_slots)
            actions = [{'slot_id': s.get('id'), 'occupied': False} for s in simulated_occupied_slots[:releases_to_do]]

            if not actions:
                print("[Sim] Simulation zone already synchronized. No replacements this cycle.")
            else:
                headers = {'Content-Type': 'application/json'}
                for act in actions:
                    response = requests.post(SENSOR_UPDATE_URL, data=json.dumps(act), headers=headers, timeout=5)
                    slot_id = act.get('slot_id')
                    if response.status_code == 200:
                        body = response.json()
                        event = body.get('event', 'ok')
                        vehicle = body.get('vehicle')
                        replacement_vehicle = body.get('replacement_vehicle')
                        slot_label = body.get('slot_label', f"S{slot_id}")

                        if event == 'released_and_replaced':
                            print(f"[Sim] Replaced {vehicle} in {slot_label} with {replacement_vehicle}")
                        else:
                            reason = body.get('reason')
                            print(f"[Sim] No change for {slot_label} ({reason})")
                    else:
                        print(f"[Error] Failed to update Slot #{slot_id}. Status: {response.status_code}")
                
        except requests.exceptions.ConnectionError:
            print("[Error] Flask server is not running. Please start app.py first.")
            time.sleep(5)
            continue
        except requests.exceptions.Timeout:
            print("[Error] Request timed out. Retrying...")
            time.sleep(2)
            continue
        except KeyboardInterrupt:
            print("\nSimulation stopped.")
            break
        except Exception as e:
            print(f"[Error] {e}")
            
        time.sleep(SIMULATION_REFRESH_SECONDS)

if __name__ == "__main__":
    simulate_sensors()
