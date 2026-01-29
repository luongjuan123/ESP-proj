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

# =====================================================
# AUTHENTICATION (Standard Password)
# =====================================================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False


def load_config_data():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return {"system_password": "admin"}


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

with st.sidebar:
    if st.button("Log Out"):
        st.session_state.logged_in = False
        st.rerun()
    st.divider()


# =====================================================
# CORE FUNCTIONS
# =====================================================
def get_vietnam_time():
    return datetime.now(timezone.utc) + timedelta(hours=7)


def save_config(bridge_data):
    # Load existing to preserve password
    current_conf = load_config_data()

    times_str = [t.strftime("%H:%M") for t in bridge_data["feed_times"]]
    current_conf.update({
        "auto_feed_enabled": bridge_data["auto_feed_enabled"],
        "feed_times": times_str,
        "input_mode": bridge_data.get("input_mode", "Picker"),
        "triggered_today": bridge_data["triggered_today"],
        "last_check_date": bridge_data["last_check_date"]
    })

    with open(CONFIG_FILE, "w") as f:
        json.dump(current_conf, f)


def load_bridge_settings():
    bridge = {
        "auto_feed_enabled": False,
        "feed_times": [datetime.strptime("08:00", "%H:%M").time()],
        "input_mode": "Picker",
        "triggered_today": [],
        "last_check_date": None,
    }
    data = load_config_data()
    if "auto_feed_enabled" in data:
        bridge["auto_feed_enabled"] = data["auto_feed_enabled"]
        bridge["input_mode"] = data.get("input_mode", "Picker")
        raw_times = data.get("feed_times", ["08:00"])
        bridge["feed_times"] = [datetime.strptime(t, "%H:%M").time() for t in raw_times]
        bridge["triggered_today"] = data.get("triggered_today", [])
        bridge["last_check_date"] = data.get("last_check_date", None)
    return bridge


# =====================================================
# STATE & MQTT
# =====================================================
if "bridge" not in st.session_state:
    st.session_state.bridge = load_bridge_settings()
bridge = st.session_state.bridge

if "sensor_value" not in st.session_state:
    st.session_state.sensor_value = 0
    st.session_state.pump_status = "OFF"
    st.session_state.feeder_status = "READY"
    st.session_state.last_seen = time.time()


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
    # Dynamic ID prevents session collision
    client_id = f"WebClient-{int(time.time())}"
    c = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    c.on_message = on_message
    c.connect(MQTT_BROKER, 1883, keepalive=60)
    c.subscribe(TOPIC_STATUS)
    c.loop_start()
    return c


client = mqtt_client()


# Helper to send commands properly (NO RETAIN to prevent ghost triggers)
def send_command(payload):
    client.publish(TOPIC_COMMAND, payload, qos=1, retain=False)


# =====================================================
# DASHBOARD
# =====================================================
st.title("🐠 Smart Fish Tank System")

vn_now = get_vietnam_time()
online = (time.time() - st.session_state.last_seen) < OFFLINE_TIMEOUT

# Sidebar Info
st.sidebar.markdown(f"### 🕒 {vn_now.strftime('%H:%M:%S')}")
if online:
    st.sidebar.success("✅ SYSTEM ONLINE")
else:
    st.sidebar.error("❌ SYSTEM OFFLINE")

# Main Status
st.metric("🍽 Feeder State", st.session_state.feeder_status)
st.divider()

# Controls
st.subheader("🕹️ Manual Controls")
mc1, mc2 = st.columns(2)
with mc1:
    if st.button("🚀 Pump ON", use_container_width=True, disabled=not online):
        send_command("PUMP_ON")
    if st.button("🛑 Pump OFF", use_container_width=True, disabled=not online):
        send_command("PUMP_OFF")
with mc2:
    if st.button("▶️ Feed ON", use_container_width=True, disabled=not online):
        send_command("FEEDER_ON")
    if st.button("⏹ Feed OFF", use_container_width=True, disabled=not online):
        send_command("FEEDER_OFF")

st.divider()

# =====================================================
# IMPROVED SCHEDULER
# =====================================================
st.subheader("⏰ Daily Schedule")
col_cfg, col_times = st.columns([1, 2])

with col_cfg:
    bridge["auto_feed_enabled"] = st.toggle("Enable Automation", value=bridge["auto_feed_enabled"])

    # Calculate Next Feed Time for display
    next_feed_txt = "None"
    min_diff = 99999
    curr_minutes = vn_now.hour * 60 + vn_now.minute

    if bridge["auto_feed_enabled"]:
        for t in bridge["feed_times"]:
            feed_minutes = t.hour * 60 + t.minute
            diff = feed_minutes - curr_minutes
            if diff > 0 and diff < min_diff:
                min_diff = diff
                next_feed_txt = t.strftime("%H:%M")

        # If no more feeds today, show tomorrow's first
        if min_diff == 99999 and len(bridge["feed_times"]) > 0:
            next_feed_txt = f"{min(bridge['feed_times']).strftime('%H:%M')} (Tomorrow)"

    st.info(f"📅 **Next Feed:** {next_feed_txt}")

    if st.button("🔄 Reset Daily Logic"):
        bridge["triggered_today"] = []
        save_config(bridge)
        st.success("Daily memory cleared!")

with col_times:
    num_feeds = st.number_input("Feeds per day", 1, 10, len(bridge["feed_times"]))

    if len(bridge["feed_times"]) > num_feeds:
        bridge["feed_times"] = bridge["feed_times"][:num_feeds]
        save_config(bridge)

    new_schedule = []
    cols = st.columns(3)
    for i in range(num_feeds):
        if i >= len(bridge["feed_times"]):
            bridge["feed_times"].append(datetime.strptime("08:00", "%H:%M").time())
        current_t = bridge["feed_times"][i]
        with cols[i % 3]:
            # Always use Picker for smoothness, it's less error prone than text
            new_val = st.time_input(f"Slot #{i + 1}", value=current_t, key=f"t_p_{i}")
            new_schedule.append(new_val)

    if new_schedule != bridge["feed_times"]:
        bridge["feed_times"] = new_schedule
        save_config(bridge)

# =====================================================
# AUTOMATION LOGIC BRAIN
# =====================================================
if bridge["auto_feed_enabled"] and online:
    curr_str = vn_now.strftime("%H:%M")
    today_str = vn_now.date().isoformat()

    # 1. Midnight Reset
    if bridge["last_check_date"] != today_str:
        bridge["triggered_today"] = []
        bridge["last_check_date"] = today_str
        save_config(bridge)

    # 2. Check Triggers
    for t in bridge["feed_times"]:
        check_str = t.strftime("%H:%M")

        # Logic: If time matches AND we haven't fed yet today
        if curr_str == check_str:
            if check_str not in bridge["triggered_today"]:
                # EXECUTE
                send_command("FEED_AUTO")

                # MARK AS DONE
                bridge["triggered_today"].append(check_str)
                save_config(bridge)

                # VISUAL NOTIFICATION
                st.toast(f"🤖 Auto-Feeding Triggered at {check_str}!", icon="🍽")

# Hidden Diagnostics
with st.sidebar:
    st.divider()
    with st.expander("🛠 Diagnostics"):
        st.write(f"TDS: {st.session_state.sensor_value}")
        st.write(f"Pump: {st.session_state.pump_status}")
        st.write(f"Fed Today: {bridge['triggered_today']}")

time.sleep(1)
st.rerun()