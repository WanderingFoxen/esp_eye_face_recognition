#include "src/OV2640.h"
#include <WiFi.h>
#include <WebServer.h>
#include <WiFiClient.h>

#define CAMERA_MODEL_ESP_EYE
#include "camera_pins.h"

OV2640 cam;

// --- Configuration Changes ---
#define SERIAL_BAUD 921600
#define FRAME_DELAY_MS 2

// WiFi Configuration
const char* ssid = "meow";
const char* password = "69696969";
// -----------------------------

WebServer server(80);

void setup() {
  Serial.begin(SERIAL_BAUD);
  Serial.println("ESP32-CAM Face Capture High Res with WiFi Streaming");

  // Camera Configuration
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sscb_sda = SIOD_GPIO_NUM;
  config.pin_sscb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = FRAMESIZE_XGA;
  config.jpeg_quality = 20;
  config.fb_count = 2;

  // Initialize camera
  esp_err_t err = cam.init(config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed: 0x%x\n", err);
    ESP.restart();
  }
  Serial.println("Camera ready");

  // Connect to WiFi
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("");
  Serial.println("WiFi connected");
  
  Serial.print("Camera Stream Ready! Go to: http://");
  Serial.println(WiFi.localIP());

  // Start HTTP server
  server.on("/", HTTP_GET, handleRoot);
  server.on("/stream", HTTP_GET, handleStream);
  server.begin();
}

void loop() {
  server.handleClient();
  
  // Original serial streaming functionality
  cam.run();
  size_t len = cam.getSize();
  uint8_t *fb = cam.getfb();

  if (fb && len > 0) {
    // Serial output
    Serial.printf("IMAGE_START:%d\n", len);
    Serial.write(fb, len);
    Serial.println("IMAGE_END");
    Serial.flush();
  }
  delay(FRAME_DELAY_MS);
}

// HTML Page with embedded stream
void handleRoot() {
  String html = "<html><head><title>ESP-EYE Stream</title></head><body>";
  html += "<h1>ESP-EYE Camera Stream</h1>";
  html += "<img src='/stream' style='width:100%; max-width:800px;'/>";
  html += "</body></html>";
  server.send(200, "text/html", html);
}

// Handle the JPEG stream
void handleStream() {
  WiFiClient client = server.client();
  
  // Send response headers
  String response = "HTTP/1.1 200 OK\r\n";
  response += "Content-Type: multipart/x-mixed-replace; boundary=frame\r\n\r\n";
  server.sendContent(response);

  while (true) {
    cam.run();
    size_t len = cam.getSize();
    uint8_t *fb = cam.getfb();

    if (!fb || len == 0) {
      continue;
    }

    // Send the image
    client.print("--frame\r\n");
    client.print("Content-Type: image/jpeg\r\n\r\n");
    client.write(fb, len);
    client.print("\r\n\r\n");
    
    if (!client.connected()) {
      break;
    }
  }
}
