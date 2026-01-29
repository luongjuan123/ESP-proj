import streamlit as st
import paho.mqtt.client as mqtt
import json
import time
import os
from datetime import datetime, timedelta, timezone
from streamlit_google_auth import Authenticate

# =====================================================
# CONFIG & AUTH SETUP
# =====================================================
MQTT_BROKER = "broker.hivemq.com"
TOPIC_STATUS = "vju/dung_luong/fish_tank_99xx/status"
TOPIC_COMMAND = "vju/dung_luong/fish_tank_99xx/command"
CONFIG_FILE = "fish_config.json"
OFFLINE_TIMEOUT = 30

# Initialize Page Config FIRST
st.set_page_config(page_title="VJU Fish Tank", layout="wide")

# Check for config file
if not os.path.exists(CONFIG_FILE):
    st.error(f"Missing {CONFIG_FILE}. Please create it with your Google Credentials.")
    st.stop()

# Initialize Authenticator
authenticator = Authenticate(
    secret_credentials_path=CONFIG_FILE,
    cookie_name='vju_fish_cookie',
    cookie_key='random_secret_key_signature',
    redirect_uri='http://localhost:8501',
)

# Run Authentication Check
authenticator.check_authentification()

# =====================================================
# LOGIN GATEKEEPER
# =====================================================
if not st.session_state.get('connected'):
    st.title("🔒 VJU Secure Access")
    st.write("Please sign in with your Google account to access the Fish Tank controls.")
    authenticator.login()
    st.stop()  # STOPS execution here if not logged in

# =====================================================
# MAIN DASHBOARD (Only runs if logged in)
# =====================================================

# --- Sidebar Profile ---
with st.sidebar:
    if 'user_info' in st.session_state and st.session_state['user_info']:
        user = st.session_state['user_info']
        st.image(user.get('picture'), width=50)
        st.write(f"**{user.get('name')}**")
    if st.button("Log Out"):
        authenticator.logout()
    st.divider()


def get_vietnam_time():
    return datetime.now(timezone.utc) + timedelta(hours=7)


def save_config(bridge_data):
    """Saves automation settings while preserving Auth keys."""
    # 1. Read existing file to keep 'auth' data safe
    with open(CONFIG_FILE, "r") as f:
        full_config = json.load(f)

    # 2. Update only the bridge parts
    times_str = [t.strftime("%H:%M") for t in bridge_data["feed_times"]]
    full_config.update({
        "auto_feed_enabled": bridge_data["auto_feed_enabled"],
        "feed_times": times_str,
        "input_mode": bridge_data.get("input_mode", "Picker"),
        "triggered_today": bridge_data["triggered_today"],
        "last_check_date": bridge_data["last_check_date"]
    })

    # 3. Write back
    with open(CONFIG_FILE, "w") as f:
        json.dump(full_config, f)


def load_bridge():
    bridge = {
        "auto_feed_enabled": False,
        "feed_times": [datetime.strptime("08:00", "%H:%M").time()],
        "input_mode": "Picker",
        "triggered_today": [],
        "last_check_date": None,
    }
    # Load defaults from file if they exist
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


# Shared State
if "bridge" not in st.session_state:
    st.session_state.bridge = load_bridge()

bridge = st.session_state.bridge

if "sensor_value" not in st.session_state:
    st.session_state.sensor_value = 0
    st.session_state.pump_status = "OFF"
    st.session_state.feeder_status = "READY"
    st.session_state.last_seen = time.time()


# MQTT Client
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
    client_id = f"VJU-SECURE-{int(time.time())}"
    c = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    c.on_message = on_message
    c.connect(MQTT_BROKER, 1883, keepalive=60)
    c.subscribe(TOPIC_STATUS)
    c.loop_start()
    return c


client = mqtt_client()

# =====================================================
# UI RENDERING (Rest of your app)
# =====================================================
st.title("🐠 VJU Smart Fish Tank (Secured)")

vn_now = get_vietnam_time()
online = (time.time() - st.session_state.last_seen) < OFFLINE_TIMEOUT

# Sidebar Status
st.sidebar.markdown(f"### 🕒 Time: {vn_now.strftime('%H:%M:%S')}")
if online:
    st.sidebar.success("✅ ONLINE")
else:
    st.sidebar.error("❌ OFFLINE")

# Main Metric
st.metric("🍽 Feeder State", st.session_state.feeder_status)
st.divider()

# Controls
st.subheader("🕹️ Manual Overrides")
mc1, mc2 = st.columns(2)
with mc1:
    if st.button("🚀 Turn Pump ON", use_container_width=True, disabled=not online):
        client.publish(TOPIC_COMMAND, "PUMP_ON")
    if st.button("🛑 Turn Pump OFF", use_container_width=True, disabled=not online):
        client.publish(TOPIC_COMMAND, "PUMP_OFF")
with mc2:
    if st.button("▶️ Manual Feed ON", use_container_width=True, disabled=not online):
        client.publish(TOPIC_COMMAND, "FEEDER_ON")
    if st.button("⏹ Manual Feed OFF", use_container_width=True, disabled=not online):
        client.publish(TOPIC_COMMAND, "FEEDER_OFF")

st.divider()

# Automation
st.subheader("⏰ Scheduled Feeding")
col_cfg, col_times = st.columns([1, 2])
with col_cfg:
    bridge["auto_feed_enabled"] = st.toggle("Enable Automation", value=bridge["auto_feed_enabled"])
    num_feeds = st.number_input("Feeds per day", 1, 10, len(bridge["feed_times"]))
    mode_selection = st.radio("Input Style:", ["Picker", "Text"], horizontal=True,
                              index=0 if bridge["input_mode"] == "Picker" else 1)
    bridge["input_mode"] = mode_selection

with col_times:
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

# Logic Loop
if bridge["auto_feed_enabled"] and online:
    curr_str = vn_now.strftime("%H:%M")
    today_str = vn_now.date().isoformat()
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
            st.toast(f"🤖 Auto Feed: {check_str}")

# Debugger
with st.sidebar:
    st.divider()
    with st.expander("🛠 Diagnostics"):
        st.write(f"TDS: {st.session_state.sensor_value} ppm")
        st.write(f"Pump: {st.session_state.pump_status}")
        latency = int((time.time() - st.session_state.last_seen) * 1000)
        st.code(f"Latency: {latency} ms")

time.sleep(1)
st.rerun()