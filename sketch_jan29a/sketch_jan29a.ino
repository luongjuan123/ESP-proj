#include <WiFiManager.h>
#include <PubSubClient.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <ArduinoJson.h>

// ================= HARDWARE CONFIG =================
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);

const int tdsPin  = 35;
const int relayK1 = 26;   // Pump (ACTIVE LOW)
const int relayK2 = 27;   // Feeder (ACTIVE LOW)
const int statusLed = 2;  

// ================= MQTT CONFIG (MATCHING WEB APP) =================
const char* mqtt_server   = "broker.hivemq.com";

// REMOVED "vju/" TO MATCH PYTHON CODE
const char* topic_status  = "dung_luong/fish_tank_99xx/status"; 
const char* topic_command = "dung_luong/fish_tank_99xx/command"; 

WiFiClient espClient;
PubSubClient client(espClient);

// ================= SYSTEM STATE =================
String pumpStatus   = "OFF";
String feederStatus = "READY";
bool feederAuto     = false;
bool feederManual   = false;
unsigned long feederStartTime = 0;
const unsigned long AUTO_FEED_DURATION = 4000; 

#define SCOUNT 30
int analogBuffer[SCOUNT];
int bufferIndex = 0;
int tdsPPM = 0;

unsigned long lastSample  = 0;
unsigned long lastReport  = 0;
unsigned long lastOLED    = 0;
unsigned long lastReconnectAttempt = 0;

// ================= FILTERING LOGIC =================
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
  tdsPPM = (voltage * 0.5) * 1000; 
}

// ================= COMMUNICATION =================
void sendUpdate() {
  if (!client.connected()) return;

  StaticJsonDocument<200> doc;
  pumpStatus = (digitalRead(relayK1) == LOW) ? "ON" : "OFF";
  if (digitalRead(relayK2) == LOW) {
    feederStatus = feederAuto ? "AUTO" : "MANUAL";
  } else {
    feederStatus = "READY";
  }

  doc["sensor_value"]  = tdsPPM;
  doc["pump_status"]   = pumpStatus;
  doc["feeder_status"] = feederStatus;
  doc["rssi"]          = WiFi.RSSI();

  char buffer[200];
  serializeJson(doc, buffer);
  client.publish(topic_status, buffer, true); 
}

void callback(char* topic, byte* payload, unsigned int length) {
  digitalWrite(statusLed, HIGH); 
  String msg;
  for (unsigned int i = 0; i < length; i++) msg += (char)payload[i];

  if (msg == "PUMP_ON") digitalWrite(relayK1, LOW);
  else if (msg == "PUMP_OFF") digitalWrite(relayK1, HIGH);
  else if (msg == "FEEDER_ON") { digitalWrite(relayK2, LOW); feederManual = true; feederAuto = false; }
  else if (msg == "FEEDER_OFF") { digitalWrite(relayK2, HIGH); feederManual = false; feederAuto = false; }
  else if (msg == "FEED_AUTO" && !feederAuto && !feederManual && (millis() - feederStartTime > 2000)) {
    digitalWrite(relayK2, LOW);
    feederAuto = true;
    feederStartTime = millis();
  }
  
  sendUpdate(); 
  delay(10);
  digitalWrite(statusLed, LOW);
}

boolean reconnect() {
  // UNIQUE CLIENT ID to avoid conflicts
  String clientId = "ESP32-Tank-" + String(random(0xffff), HEX);
  if (client.connect(clientId.c_str())) {
    client.subscribe(topic_command);
    sendUpdate();
  }
  return client.connected();
}

// ================= CORE SETUP =================
void setup() {
  Serial.begin(115200);
  pinMode(relayK1, OUTPUT); digitalWrite(relayK1, HIGH); 
  pinMode(relayK2, OUTPUT); digitalWrite(relayK2, HIGH);
  pinMode(statusLed, OUTPUT);
  
  display.begin(SSD1306_SWITCHCAPVCC, 0x3C);
  display.clearDisplay();
  display.setTextColor(WHITE);
  display.setCursor(0,10);
  display.println("System Starting...");
  display.display();

  WiFiManager wm;
  if (!wm.autoConnect("FishTank_Config_AP")) {
    ESP.restart();
  }

  client.setServer(mqtt_server, 1883);
  client.setCallback(callback);
  client.setKeepAlive(15);
}

// ================= MAIN LOOP =================
void loop() {
  if (!client.connected()) {
    unsigned long now = millis();
    if (now - lastReconnectAttempt > 5000) {
      lastReconnectAttempt = now;
      if (reconnect()) {
        lastReconnectAttempt = 0;
      }
    }
  } else {
    client.loop();
  }

  if (millis() - lastSample >= 10) {
    lastSample = millis();
    readStableTDS(); 
  }

  if (millis() - lastReport >= 1000) {
    lastReport = millis();
    sendUpdate(); 
  }

  if (feederAuto && (millis() - feederStartTime >= AUTO_FEED_DURATION)) {
    digitalWrite(relayK2, HIGH);
    feederAuto = false;
    sendUpdate();
  }

  if (millis() - lastOLED >= 500) {
    lastOLED = millis();
    display.clearDisplay();
    display.setTextSize(1);
    display.setCursor(0, 0);
    display.println("FISH TANK SYSTEM"); // Removed VJU branding
    display.drawLine(0, 12, 128, 12, WHITE);
    
    display.setCursor(0, 20);
    display.print("TDS:  "); display.print(tdsPPM); display.println(" ppm");
    display.print("Pump: "); display.println(pumpStatus);
    
    display.setCursor(0, 55);
    display.print(client.connected() ? "Online" : "Connecting...");
    display.display();
  }
}