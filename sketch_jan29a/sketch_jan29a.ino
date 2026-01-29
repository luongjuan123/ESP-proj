#include <WiFiManager.h>
#include <PubSubClient.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <ArduinoJson.h>

// ================= HARDWARE =================
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);

const int tdsPin  = 35;
const int relayK1 = 26;   // Pump (ACTIVE LOW)
const int relayK2 = 27;   // Feeder (ACTIVE LOW)

// ================= MQTT CONFIG =================
const char* mqtt_server   = "broker.hivemq.com";
const char* topic_status  = "vju/dung_luong/fish_tank_99xx/status";
const char* topic_command = "vju/dung_luong/fish_tank_99xx/command";

WiFiClient espClient;
PubSubClient client(espClient);

// ================= STATE =================
String pumpStatus   = "OFF";
String feederStatus = "READY";
bool feederAuto     = false;
bool feederManual   = false;
unsigned long feederStartTime = 0;
const unsigned long AUTO_FEED_DURATION = 4000; // 4 seconds

#define SCOUNT 30
int analogBuffer[SCOUNT];
int bufferIndex = 0;
int tdsPPM = 0;

// ================= HELPERS =================
int getMedian(int arr[], int len) {
  int temp[len];
  memcpy(temp, arr, sizeof(int) * len);
  for (int i = 0; i < len - 1; i++){
    for (int j = i + 1; j < len; j++){
      if(temp[i] > temp[j]){
        int t = temp[i]; temp[i] = temp[j]; temp[j] = t;
      }
    }
  }
  return temp[len / 2];
}

void readStableTDS() {
  analogBuffer[bufferIndex++] = analogRead(tdsPin);
  if (bufferIndex >= SCOUNT) bufferIndex = 0;
  int median = getMedian(analogBuffer, SCOUNT);
  float voltage = median * (3.3 / 4095.0);
  // Linear approximation: change 0.5 to your calibration factor if needed
  tdsPPM = (voltage * 0.5) * 1000; 
}

void sendUpdate() {
  StaticJsonDocument<256> doc;

  // Read actual relay states
  pumpStatus = (digitalRead(relayK1) == LOW) ? "ON" : "OFF";
  if (digitalRead(relayK2) == LOW) {
    feederStatus = feederAuto ? "AUTO" : "MANUAL";
  } else {
    feederStatus = "READY";
  }

  doc["sensor_value"]  = tdsPPM;
  doc["pump_status"]   = pumpStatus;
  doc["feeder_status"] = feederStatus;
  doc["uptime"]        = millis();

  char buffer[256];
  serializeJson(doc, buffer);
  // Publish with RETAIN=true so the web app gets data instantly on load
  client.publish(topic_status, buffer, true); 
}

void callback(char* topic, byte* payload, unsigned int length) {
  String msg;
  for (unsigned int i = 0; i < length; i++) msg += (char)payload[i];

  if (msg == "PUMP_ON") digitalWrite(relayK1, LOW);
  else if (msg == "PUMP_OFF") digitalWrite(relayK1, HIGH);
  else if (msg == "FEEDER_ON") { digitalWrite(relayK2, LOW); feederManual = true; feederAuto = false; }
  else if (msg == "FEEDER_OFF") { digitalWrite(relayK2, HIGH); feederManual = false; feederAuto = false; }
  // Auto-feed with 10s cooldown to prevent double-firing
  else if (msg == "FEED_AUTO" && !feederAuto && !feederManual && (millis() - feederStartTime > 10000)) {
    digitalWrite(relayK2, LOW);
    feederAuto = true;
    feederStartTime = millis();
  }
  sendUpdate(); 
}

void reconnectMQTT() {
  while (!client.connected()) {
    // NEW CLIENT ID to bypass the previous clogged queue
    String clientId = "ESP32-STABLE-" + String(random(0xffff), HEX);
    if (client.connect(clientId.c_str())) {
      client.subscribe(topic_command);
      sendUpdate();
    } else {
      delay(5000);
    }
  }
}

// ================= SETUP =================
void setup() {
  Serial.begin(115200);
  pinMode(relayK1, OUTPUT); digitalWrite(relayK1, HIGH); // Default OFF
  pinMode(relayK2, OUTPUT); digitalWrite(relayK2, HIGH); // Default OFF
  
  display.begin(SSD1306_SWITCHCAPVCC, 0x3C);
  display.clearDisplay();

  WiFiManager wm;
  wm.autoConnect("VJU_FishTank_Setup");

  client.setServer(mqtt_server, 1883);
  client.setCallback(callback);
  client.setKeepAlive(10);
}

// ================= LOOP =================
void loop() {
  if (!client.connected()) reconnectMQTT();
  client.loop();

  // 1. High-speed sampling (10ms) for median filter accuracy
  static unsigned long lastSample = 0;
  if (millis() - lastSample >= 10) {
    lastSample = millis();
    readStableTDS(); 
  }

  // 2. Controlled reporting (1 second) to keep latency low
  static unsigned long lastReport = 0;
  if (millis() - lastReport >= 1000) {
    lastReport = millis();
    sendUpdate(); 
  }

  // 3. Auto-off logic for feeder
  if (feederAuto && (millis() - feederStartTime >= AUTO_FEED_DURATION)) {
    digitalWrite(relayK2, HIGH);
    feederAuto = false;
    sendUpdate();
  }

  // 4. OLED Refresh (readable speed)
  static unsigned long lastOLED = 0;
  if (millis() - lastOLED >= 500) {
    lastOLED = millis();
    display.clearDisplay();
    display.setTextSize(1);
    display.setTextColor(WHITE);
    display.setCursor(0, 0);
    display.println("VJU STABLE SYSTEM");
    display.print("TDS: "); display.print(tdsPPM); display.println(" ppm");
    display.print("Pump: "); display.println(pumpStatus);
    display.display();
  }
}