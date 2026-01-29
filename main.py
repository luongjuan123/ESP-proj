import streamlit as st
import paho.mqtt.client as mqtt
import json
import time
import os
from datetime import datetime, timedelta, timezone

# =====================================================
# CONFIGURATION & PERSISTENCE
# =====================================================
MQTT_BROKER = "broker.hivemq.com"
TOPIC_STATUS = "vju/dung_luong/fish_tank_99xx/status"
TOPIC_COMMAND = "vju/dung_luong/fish_tank_99xx/command"
CONFIG_FILE = "fish_config.json"
OFFLINE_TIMEOUT = 30  # Seconds before system shows as offline


def get_vietnam_time():
    """Returns UTC+7 time using modern timezone-aware objects."""
    return datetime.now(timezone.utc) + timedelta(hours=7)


def save_config(bridge_data):
    """Saves automation settings to local JSON file."""
    times_str = [t.strftime("%H:%M") for t in bridge_data["feed_times"]]
    data = {
        "auto_feed_enabled": bridge_data["auto_feed_enabled"],
        "feed_times": times_str,
        "input_mode": bridge_data.get("input_mode", "Picker"),
        "triggered_today": bridge_data["triggered_today"],
        "last_check_date": bridge_data["last_check_date"]
    }
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f)


def load_config():
    """Initializes and loads the bridge data structure."""
    bridge = {
        "auto_feed_enabled": False,
        "feed_times": [datetime.strptime("08:00", "%H:%M").time()],
        "input_mode": "Picker",
        "triggered_today": [],
        "last_check_date": None,
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
                bridge["auto_feed_enabled"] = data.get("auto_feed_enabled", False)
                bridge["input_mode"] = data.get("input_mode", "Picker")
                raw_times = data.get("feed_times", ["08:00"])
                bridge["feed_times"] = [datetime.strptime(t, "%H:%M").time() for t in raw_times]
                bridge["triggered_today"] = data.get("triggered_today", [])
                bridge["last_check_date"] = data.get("last_check_date", None)
        except:
            pass
    return bridge


# =====================================================
# SHARED STATE (Session Management)
# =====================================================
if "bridge" not in st.session_state:
    st.session_state.bridge = load_config()

# Bridge handles automation logic
bridge = st.session_state.bridge

# Status states for real-time updates
if "sensor_value" not in st.session_state:
    st.session_state.sensor_value = 0
    st.session_state.pump_status = "OFF"
    st.session_state.feeder_status = "READY"
    st.session_state.last_seen = time.time()
    st.session_state.mqtt_connected = False


# =====================================================
# MQTT CLIENT LOGIC
# =====================================================
def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        st.session_state.mqtt_connected = True
        client.subscribe(TOPIC_STATUS)
    else:
        st.session_state.mqtt_connected = False


def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode())
        if "sensor_value" in data: st.session_state.sensor_value = int(data["sensor_value"])
        if "pump_status" in data: st.session_state.pump_status = str(data["pump_status"]).upper()
        if "feeder_status" in data: st.session_state.feeder_status = str(data["feeder_status"]).upper()
        st.session_state.last_seen = time.time()
    except:
        pass


@st.cache_resource
def mqtt_client():
    client_id = f"VJU-SmartFish-{int(time.time())}"
    c = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    c.on_connect = on_connect
    c.on_message = on_message
    c.connect(MQTT_BROKER, 1883, keepalive=60)
    c.loop_start()
    return c


client = mqtt_client()

# =====================================================
# UI RENDERING
# =====================================================
st.set_page_config(page_title="VJU Smart Fish Care", layout="wide")
st.title("🐠 VJU Smart Fish Care System")

vn_now = get_vietnam_time()
online = (time.time() - st.session_state.last_seen) < OFFLINE_TIMEOUT

# SIDEBAR STATUS MONITOR
st.sidebar.markdown(f"### 🕒 Current Time\n## {vn_now.strftime('%H:%M:%S')}")
st.sidebar.divider()
if online:
    st.sidebar.success("✅ SYSTEM ONLINE")
else:
    st.sidebar.error("❌ SYSTEM OFFLINE")

# MAIN METRICS (Hidden: Pump & TDS as per request)
# Only Feeder is displayed prominently
col1, col2 = st.columns([1, 3])
with col1:
    st.metric("🍽 Food Feeder", st.session_state.feeder_status)

st.divider()

# MANUAL CONTROLS
st.subheader("🕹️ Manual Overrides")
mc1, mc2 = st.columns(2)
with mc1:
    # Pump control remains available but the value is not displayed above
    if st.button("🚀 Activate Pump", use_container_width=True, disabled=not online, type="primary"):
        client.publish(TOPIC_COMMAND, "PUMP_ON")
    if st.button("🛑 Deactivate Pump", use_container_width=True, disabled=not online):
        client.publish(TOPIC_COMMAND, "PUMP_OFF")
with mc2:
    if st.button("▶️ Start Feeding", use_container_width=True, disabled=not online, type="primary"):
        client.publish(TOPIC_COMMAND, "FEED_AUTO")
    if st.button("⏹ Stop Feeding", use_container_width=True, disabled=not online):
        client.publish(TOPIC_COMMAND, "FEEDER_OFF")

st.divider()

# AUTOMATED FEEDING SCHEDULE
st.subheader("⏰ Automated Feeding Schedule")
col_cfg, col_times = st.columns([1, 2])

with col_cfg:
    bridge["auto_feed_enabled"] = st.toggle("Enable Auto-Feeding", value=bridge["auto_feed_enabled"])
    num_feeds = st.number_input("Feeds per Day", 1, 10, len(bridge["feed_times"]))
    mode_selection = st.radio("Time Input Style:", ["Picker", "Text"], horizontal=True,
                              index=0 if bridge["input_mode"] == "Picker" else 1)
    bridge["input_mode"] = mode_selection

with col_times:
    # Ghost-box cleanup logic: removes session state for deleted slots
    if len(bridge["feed_times"]) > num_feeds:
        for i in range(num_feeds, len(bridge["feed_times"])):
            for key in [f"t_txt_{i}", f"t_p_{i}"]:
                if key in st.session_state: del st.session_state[key]
        bridge["feed_times"] = bridge["feed_times"][:num_feeds]
        save_config(bridge)

    new_schedule = []
    cols = st.columns(3)
    for i in range(num_feeds):
        if i >= len(bridge["feed_times"]):
            bridge["feed_times"].append(datetime.strptime("08:00", "%H:%M").time())

        current_t = bridge["feed_times"][i]
        with cols[i % 3]:
            if bridge["input_mode"] == "Text":
                t_str = st.text_input(f"Slot #{i + 1}", value=current_t.strftime("%H:%M"), key=f"t_txt_{i}")
                try:
                    new_schedule.append(datetime.strptime(t_str, "%H:%M").time())
                except:
                    new_schedule.append(current_t)
            else:
                new_schedule.append(st.time_input(f"Slot #{i + 1}", value=current_t, key=f"t_p_{i}"))

    if new_schedule != bridge["feed_times"]:
        bridge["feed_times"] = new_schedule
        save_config(bridge)

# AUTOMATION BRAIN (Logic Loop)
if bridge["auto_feed_enabled"] and online:
    curr_str = vn_now.strftime("%H:%M")
    today_str = vn_now.date().isoformat()

    # Daily reset for feeding memory
    if bridge["last_check_date"] != today_str:
        bridge["triggered_today"] = []
        bridge["last_check_date"] = today_str
        save_config(bridge)

    for t in bridge["feed_times"]:
        check_str = t.strftime("%H:%M")
        if curr_str == check_str and check_str not in bridge["triggered_today"]:
            bridge["triggered_today"].append(check_str)
            save_config(bridge)
            client.publish(TOPIC_COMMAND, "FEED_AUTO")
            st.toast(f"🤖 Auto Feed Triggered: {check_str}")

# SYSTEM DIAGNOSTICS (Hidden Sensor Display)
with st.sidebar:
    st.divider()
    with st.expander("🛠 System Diagnostics (Hidden)"):
        st.write(f"**TDS Value:** {st.session_state.sensor_value} ppm")
        st.write(f"**Pump State:** {st.session_state.pump_status}")
        latency = int((time.time() - st.session_state.last_seen) * 1000)
        st.code(f"Latency: {latency} ms")
        st.code(f"MQTT: {'Connected' if st.session_state.mqtt_connected else 'Disconnected'}")

# AUTO-REFRESH (1-Second Loop for Stability)
time.sleep(1)
st.rerun()