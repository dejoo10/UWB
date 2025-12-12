# ESP32 Ultra-Wideband (UWB) Testing

![Platform](https://img.shields.io/badge/Platform-ESP32-blue?style=for-the-badge&logo=espressif)
![Language](https://img.shields.io/badge/Language-C%2B%2B-red?style=for-the-badge&logo=c%2B%2B)
![Status](https://img.shields.io/badge/Status-Active-green?style=for-the-badge)

<div align="center">
  <img src="./images/UWB%20top%20image.jpeg" alt="UWB Setup" width="100%">
</div>

---

## 📖 About This Project

This project explores the capabilities of **Ultra-Wideband (UWB)** technology for precise indoor positioning and secure data transfer. The primary goal is to investigate UWB's performance in real-world scenarios, specifically focusing on applications for **Hockey Sport**.

We compare UWB with existing technologies like **Bluetooth (BLE)** and **GPS**, highlighting its superiority in indoor accuracy and resistance to interference.

### 🌟 Key Features
*   **High Precision**: ±10 cm indoor accuracy using Time-of-Flight (ToF).
*   **Low Power**: Efficient communication suitable for battery-operated tags.
*   **Dual Functionality**: Combines ESP32's WiFi/BLE with Decawave's UWB capabilities.

---

## 🛠️ Hardware Requirements

For this setup, we utilize **ESP32 UWB modules** acting as **Anchors** (fixed reference points) and **Tags** (mobile devices to be tracked).

| Component | Description | Quantity |
| :--- | :--- | :--- |
| **ESP32 UWB Module** | Core hardware (DW1000 + ESP32) | 3 (2 Tags, 1 Anchor) |
| **Micro-USB Cable** | For power and programming | 3 |
| **Power Source** | Power bank or PC USB port | 3 |

> **Note**: We use the standard DW1000 version which offers a typical range of ~45m.

<div align="center">
  <img src="./images/esp32-uwb-frontt.png" alt="ESP32 UWB Front" width="45%">
  <img src="./images/esp32-uwb-backk.png" alt="ESP32 UWB Back" width="45%">
</div>

---

## 💻 Software Requirements

To replicate this project, you will need the following software and libraries:

*   **Arduino IDE**: For programming the ESP32 modules.
*   **Board Support**: `ESP32 Dev Module` installed in Arduino IDE.
*   **Libraries**:
    *   `DW1000` (Based on Makerfabs library)
    *   `Adafruit_SSD1306` (For OLED display support)
*   **Python 3**: For running the visualization script on a PC.

---

## 🚀 Getting Started

Follow these steps to set up your indoor positioning system.

### Step 1: Install Dependencies
1.  Download and install the [Arduino IDE](https://www.arduino.cc/en/software).
2.  In Arduino IDE, go to **Tools > Board > Boards Manager** and install the **ESP32** package.
3.  Install the `Adafruit_SSD1306` library via the Library Manager.
4.  Download the `DW1000.zip` library (rename `mf_DW1000.zip` if necessary) and add it via **Sketch > Include Library > Add .ZIP Library**.

### Step 2: Flash the Firmware
You need to flash different code for **Anchors** and **Tags**.

**For Anchors:**
1.  Open `Code/Anchor/anchor_code.ino` (verify path in repo).
2.  Select board: **ESP32 Dev Module**.
3.  Connect the Anchor ESP32 to your PC.
4.  Upload the sketch.

**For Tags:**
1.  Open `Code/Tag/tag_code.ino` (verify path in repo).
2.  Select board: **ESP32 Dev Module**.
3.  Connect the Tag ESP32 to your PC.
4.  Upload the sketch.

### Step 3: Device Discovery & Network
1.  Connect devices to your computer to identify their MAC addresses.
2.  Ensure devices are added to your home network if using WiFi features.
3.  Power up all Anchors in their fixed locations.
4.  Power up the Tag.

### Step 4: Run Visualization
We use a Python script to visualize the position of the tag relative to the anchors.

1.  Navigate to the directory containing the Python script.
2.  Run the script:
    ```bash
    python3 uwb_positioning.py
    ```
    *(Note: Refer to the Code folder for the specific script name)*

3.  The output will show real-time distance and coordinates.

<div align="center">
  <img src="./images/UWB_1c.png" alt="Positioning Screen" width="80%">
  <p><em>Figure: Real-time positioning visualization</em></p>
</div>

---

## 📊 How It Works: Time-of-Arrival (ToA)

The system uses **Time-of-Arrival (ToA)** to measure distance. The Tag sends a 
radio pulse, the Anchor receives it and sends a response. The time taken for this round trip is used to calculate distance with high precision ($Speed \times Time = Distance$).

![TOA Calculation](./images/UWB_distanceCalcwithTOA.jpg)

---


---

## 📡 Data Transfer Testing

In addition to positioning, we experimented with data transfer between two ESP32 UWB devices. One device acted as a **Transmitter**, and the other as a **Receiver**.

<div align="center">
  <img src="./images/UWB_2a.png" alt="Data Transfer Setup" width="50%">
  <p><em>Figure: Data Transfer In Progress</em></p>
</div>

### 🚀 Speed & Performance Limitations

The Qorvo DW1000 chip supports a maximum theoretical data rate of **6.8 Mbps** (based on IEEE 802.15.4a). However, achieving this in real-world scenarios is challenging due to:
1.  **Protocol Limitations**: The fundamental overhead of PHY and MAC headers reduces actual application throughput.
2.  **Packet Size**: The maximum packet length is **1023 bytes**. While larger packets improve throughput, they increase latency and error susceptibility in noisy environments.
3.  **Duty Cycle**: The chip is optimized for short bursts (localization) rather than sustained bulk data transfer.
4.  **Environmental Factors**: While UWB is robust against multipath fading, signal blockage and interference still impact range and effective throughput.

**Recommendation**: For reliable operation, use the 6.8 Mbps mode for short-range, interference-free conditions. For larger files, maximizing packet size (up to 1023 bytes) can help, but error control mechanisms are essential.

### 🔒 Security Considerations

Our implementation uses the **Qorvo DW1000**, which complies with the older **IEEE 802.15.4a** standard.
*   **Limitation**: It lacks native support for the **Scrambled Timestamp Sequence (STS)** field introduced in the newer **IEEE 802.15.4z** standard.
*   **Implication**: Without STS, the system is more vulnerable to physical-layer attacks (like distance reduction attacks) compared to modern chips like the DW3000.
*   **Modern Alternatives**: Newer chips (e.g., DW3000) use AES-128 encryption to generate pseudo-random sequences (STS), ensuring that only devices with the shared key can perform valid ranging, effectively preventing standard relay or replay attacks.

---

## 👥 Authors

*   **Adedeji Babalola**
*   **Dmitri Oikarinen**
*   **Vali Maleki**

---

## 📚 References & Credits

*   [Makerfabs ESP32 UWB Wiki](https://wiki.makerfabs.com/ESP32_UWB.html)
*   [RobotShop Product Page](https://ca.robotshop.com/products/esp32-uwb-pro))
*   [Qorvo, “Qorvo DW3000 Transceivers](https://www.mouser.fi/new/qorvo/qorvo-dw3000-transceivers
*   [Qorvo, "Getting Back to basics with Ultra-Wideband](https://www.qorvo.com/resources/d/qorvo-gettingback-
to-basics-with-ultra-wideband-uwb-white-paper.)
*   [Qorvo, "Qorvo, "DW1000"](https://www.qorvo.com/products/p/DW1000.)
*   Based on original research and implementations from Makerfabs GitHub.
