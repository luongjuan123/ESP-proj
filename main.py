import streamlit as st
import paho.mqtt.client as mqtt
import json
import time
import os
from datetime import datetime, timedelta, timezone

# =====================================================
# CONFIGURATION
# =====================================================
MQTT_BROKER = "broker.hivemq.com"
TOPIC_STATUS = "dung_luong/fish_tank_99xx/status"
TOPIC_COMMAND = "dung_luong/fish_tank_99xx/command"
CONFIG_FILE = "fish_config.json"
OFFLINE_TIMEOUT = 30

st.set_page_config(page_title="Fish Tank Control", layout="wide")


def load_config_data():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return {"system_password": "admin", "auto_feed_enabled": False, "feed_times": ["08:00"], "triggered_today": [],
            "last_check_date": ""}


if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

config_data = load_config_data()
SYSTEM_PASSWORD = config_data.get("system_password", "admin123")

if not st.session_state.logged_in:
    st.title("🔒 System Login")
    pwd = st.text_input("Password:", type="password")
    if st.button("Login"):
        if pwd == SYSTEM_PASSWORD:
            st.session_state.logged_in = True
            st.rerun()
        else:
            st.error("Wrong password.")
    st.stop()

# =====================================================
# STATE & MQTT
# =====================================================
if "sensor_value" not in st.session_state:
    st.session_state.sensor_value = 0
    st.session_state.pump_status = "OFF"
    st.session_state.feeder_status = "READY"
    st.session_state.last_seen = 0


def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode())
        st.session_state.sensor_value = data.get("sensor_value", 0)
        st.session_state.pump_status = str(data.get("pump_status", "OFF")).upper()
        st.session_state.feeder_status = str(data.get("feeder_status", "READY")).upper()
        st.session_state.last_seen = time.time()
    except:
        pass


@st.cache_resource
def mqtt_client():
    client_id = f"WebClient-{int(time.time())}"
    c = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    c.on_message = on_message
    c.connect(MQTT_BROKER, 1883, 60)
    c.subscribe(TOPIC_STATUS)
    c.loop_start()
    return c


client = mqtt_client()


def send_command(payload):
    client.publish(TOPIC_COMMAND, payload, qos=1)


def get_vn_now():
    return datetime.now(timezone.utc) + timedelta(hours=7)


# =====================================================
# LOGIC & UI
# =====================================================
vn_now = get_vn_now()
today_str = vn_now.date().isoformat()

# Load/Update Bridge state
if "bridge" not in st.session_state:
    st.session_state.bridge = config_data
    # Convert string times to time objects
    st.session_state.bridge["feed_times_obj"] = [datetime.strptime(t, "%H:%M").time() for t in
                                                 config_data["feed_times"]]

bridge = st.session_state.bridge

# --- SIDEBAR & STATUS ---
online = (time.time() - st.session_state.last_seen) < OFFLINE_TIMEOUT
with st.sidebar:
    st.title("Control Panel")
    if online:
        st.success("✅ SYSTEM ONLINE")
    else:
        st.error("❌ SYSTEM OFFLINE")
    st.write(f"Last update: {vn_now.strftime('%H:%M:%S')}")
    if st.button("Log Out"):
        st.session_state.logged_in = False
        st.rerun()

# --- MAIN DASHBOARD ---
st.title("🐠 Smart Fish Tank")
m1, m2, m3 = st.columns(3)
m1.metric("TDS Level", f"{st.session_state.sensor_value} ppm")
m2.metric("Pump Status", st.session_state.pump_status)
m3.metric("Feeder Status", st.session_state.feeder_status)

st.divider()

# --- MANUAL CONTROLS ---
col1, col2 = st.columns(2)
with col1:
    if st.button("🚀 PUMP ON", use_container_width=True): send_command("PUMP_ON")
    if st.button("🛑 PUMP OFF", use_container_width=True): send_command("PUMP_OFF")
with col2:
    if st.button("▶️ FEED NOW (MANUAL)", use_container_width=True): send_command("FEEDER_ON")
    if st.button("⏹ STOP FEEDER", use_container_width=True): send_command("FEEDER_OFF")

st.divider()

# --- SCHEDULER ---
st.subheader("⏰ Daily Schedule")
c_auto, c_times = st.columns([1, 2])

with c_auto:
    bridge["auto_feed_enabled"] = st.toggle("Enable Automation", value=bridge["auto_feed_enabled"])
    if st.button("♻️ Reset Today's History"):
        bridge["triggered_today"] = []
        st.rerun()

with c_times:
    num_feeds = st.number_input("Feeds per day", 1, 5, len(bridge["feed_times_obj"]))
    new_times = []
    cols = st.columns(3)
    for i in range(num_feeds):
        t_val = bridge["feed_times_obj"][i] if i < len(bridge["feed_times_obj"]) else datetime.strptime("08:00",
                                                                                                        "%H:%M").time()
        with cols[i % 3]:
            new_t = st.time_input(f"Feed #{i + 1}", t_val, key=f"time_{i}")
            new_times.append(new_t)

    if new_times != bridge["feed_times_obj"]:
        bridge["feed_times_obj"] = new_times
        bridge["feed_times"] = [t.strftime("%H:%M") for t in new_times]
        # Save to file
        with open(CONFIG_FILE, "w") as f:
            json.dump({k: v for k, v in bridge.items() if k != "feed_times_obj"}, f)

# =====================================================
# AUTOMATION BRAIN (THE FIX)
# =====================================================
if bridge["auto_feed_enabled"] and online:
    # 1. Reset history if new day
    if bridge.get("last_check_date") != today_str:
        bridge["triggered_today"] = []
        bridge["last_check_date"] = today_str

    # 2. Check scheduled times
    curr_time_obj = vn_now.time()
    for t_obj in bridge["feed_times_obj"]:
        t_str = t_obj.strftime("%H:%M")

        # Check if current time is within 5 minutes AFTER scheduled time
        # AND hasn't been triggered yet today
        if curr_time_obj >= t_obj and t_str not in bridge["triggered_today"]:
            # If we are within a 10 minute window, trigger it
            # (Prevents old triggers from firing if you open the app 5 hours late)
            diff = (datetime.combine(vn_now.date(), curr_time_obj) - datetime.combine(vn_now.date(),
                                                                                      t_obj)).total_seconds()

            if diff < 600:  # 10 minute window
                send_command("FEED_AUTO")
                bridge["triggered_today"].append(t_str)
                # Save state
                with open(CONFIG_FILE, "w") as f:
                    json.dump({k: v for k, v in bridge.items() if k != "feed_times_obj"}, f)
                st.toast(f"Feeding triggered for {t_str}!")

# Periodic Rerun
time.sleep(2)
st.rerun()