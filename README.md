#  Smart Fish Tank System

A **web-controlled, MQTT-based smart fish tank** that lets you **monitor status, control pump & feeder**, and **automatically schedule daily feeding**.  
The system consists of:

-  **Streamlit Web Dashboard** (main.py)
-  **ESP32 firmware** (sketch_jan29a.ino)
- ️ **MQTT broker** (HiveMQ public broker)

---

##  Features

### Web Dashboard (Streamlit)
-  Password-protected login
-  Real-time system status via MQTT
-  Manual control:
  - Pump ON / OFF
  - Feeder ON / OFF
-  Smart auto-feeding scheduler
  - Multiple feed times per day
  - One-trigger-per-day safety logic
  - Automatic midnight reset
-  Vietnam local time handling (UTC7)
-  Persistent configuration (fish_config.json)

### ESP32 Firmware
-  Auto WiFi connection (WiFiManager)
-  MQTT publish/subscribe
- ️ Controls:
  - Relay-driven pump
  - Servo / motor feeder
-  Sends real-time status updates
-  Listens for commands from dashboard

---

##  System Architecture


[ Streamlit Web UI ]
          
            MQTT (commands)
          
[  HiveMQ Broker  ]
          
            MQTT (status)
[     ESP32      ]
          
[ Pump / Feeder / Sensors ]


---

##  Project Structure


.
 main.py              # Streamlit web dashboard
 sketch_jan29a.ino    # ESP32 firmware
 fish_config.json     # Auto-generated config & schedule storage
 README.md            # This file


---

##  Getting Started

### 1️⃣ ESP32 Setup

**Requirements**
- ESP32 board
- Arduino IDE
- Libraries:
  - WiFiManager
  - PubSubClient
  - ArduinoJson
  - Adafruit SSD1306 (if OLED used)

**Steps**
1. Open sketch_jan29a.ino in Arduino IDE
2. Install required libraries
3. Select correct ESP32 board & port
4. Upload firmware
5. On first boot, connect to the ESP32 WiFi AP and configure WiFi

The ESP32 will automatically connect to:
- **Broker:** broker.hivemq.com
- **Topics:**
  - Status: dung_luong/fish_tank_99xx/status
  - Command: dung_luong/fish_tank_99xx/command

---

### 2️⃣ Web Dashboard Setup

**Requirements**
- Python 3.9

**Install dependencies**
bash
pip install streamlit paho-mqtt


**Run the app**
bash
streamlit run main.py


**Default login**
- Password: admin

(Stored in fish_config.json)

---

##  Auto-Feeding Logic (Important)

- Feeding triggers **only once per scheduled time per day**
- Prevents repeated triggers even if the page refreshes
- At midnight (Vietnam time):
  - Daily memory resets automatically
- Uses **non-retained MQTT messages** to prevent ghost feeding

---

##  MQTT Commands

 Command  Action 
------------
 PUMP_ON  Turn pump ON 
 PUMP_OFF  Turn pump OFF 
 FEEDER_ON  Manual feeding 
 FEEDER_OFF  Stop feeder 
 FEED_AUTO  Auto feeding trigger 

---

##  Diagnostics

The dashboard includes a hidden diagnostics panel showing:
- Sensor value (e.g. TDS)
- Pump status
- Feeds already triggered today

Useful for debugging automation logic.

---

## ️ Notes & Safety

- Public MQTT broker  **do not use for production** without auth
- Add physical safety limits for feeder & pump
- Ensure relays are rated for pump voltage

---

##  License

MIT License — free to use, modify, and improve.

---

## ️ Credits

Built as a **DIY IoT  AI fish care system** using:
- ESP32
- MQTT
- Streamlit

Happy hacking 

