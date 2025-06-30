## 📑 Indice

- [📋 Panoramica](#-panoramica)
- [🎯 Setup in 4 Passi (15-30 minuti)](#-setup-in-4-passi-15-30-minuti)
  - [✅ Passo 1: Installa Visual Studio Code](#-passo-1-installa-visual-studio-code)
  - [✅ Passo 2: Installa Estensione ESP-IDF](#-passo-2-installa-estensione-esp-idf)
  - [✅ Passo 3: Configurazione Automatica ESP-IDF](#-passo-3-configurazione-automatica-esp-idf)
  - [✅ Passo 4: Test Installazione](#-passo-4-test-installazione)
- [🎛️ Interfaccia VS Code ESP-IDF](#interfaccia-vs-code-esp-idf)
- [🔌 Setup Hardware](#-setup-hardware)
- [🧪 Test Completo](#-test-completo)
- [🏭 IoT ESP32 Modbus RTU - MQTT Bridge System](#-iot-esp32-modbus-rtu---mqtt-bridge-system)
  - [🎯 Panoramica](#-panoramica-1)
  - [🏗️ Architettura](#architettura)
- [⚡ Quick Start](#-quick-start)
- [🔧 Installazione](#-installazione)
- [📱 Configurazione ESP32](#-configurazione-esp32)
- [⚙️ Config Service](#-config-service)
  - [Dashboard Web](#dashboard-web)
  - [API REST](#api-rest)
- [🎮 Scrittura Modbus](#-scrittura-modbus)
- [📊 Template System](#-template-system)
- [📡 MQTT Topics](#-mqtt-topics)
- [🔍 Monitoring](#-monitoring)
- [📄 License](#-license)
- [👥 Autori e Riconoscimenti](#-autori-e-riconoscimenti)

# ESP32-C6 Development Environment Setup

[![ESP-IDF](https://img.shields.io/badge/ESP--IDF-v5.4.1-blue)](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/get-started/windows-setup.html)
[![ESP-IDF](https://img.shields.io/badge/ESP--IDF-v5.4.1-blue)](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/get-started/linux-macos-setup.html)
[![VS Code](https://img.shields.io/badge/VS%20Code-ESP--IDF%20Extension-green)](https://marketplace.visualstudio.com/items?itemName=espressif.esp-idf-extension)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux-lightgrey)](https://github.com/espressif/esp-idf)

## 📋 Panoramica

Guida completa per configurare l'ambiente di sviluppo ESP32-C6 con VS Code e ESP-IDF in modo semplice e veloce.

## 🎯 Setup in 4 Passi (15-30 minuti)

### ✅ Passo 1: Installa Visual Studio Code

**Windows:**
- Scarica da: https://code.visualstudio.com/
- Esegui installer come **amministratore**
- ⚠️ **Importante**: Seleziona "Add to PATH" durante installazione

**Linux (Ubuntu/Debian):**
```bash
sudo snap install --classic code
```

### ✅ Passo 2: Installa Estensione ESP-IDF

1. Apri VS Code
2. Vai a **Extensions** (`Ctrl+Shift+X`)
3. Cerca: **ESP-IDF**
4. Installa: **ESP-IDF** by Espressif Systems
5. Riavvia VS Code

### ✅ Passo 3: Configurazione Automatica ESP-IDF

1. **Command Palette**: `F1`
2. **Digita**: `ESP-IDF: Configure ESP-IDF Extension`
3. **Seleziona**: `Express Installation`
4. **Configura**:
   - Select download server: Github
   - Select ESP-IDF version: **Find ESP-IDF in your system** 
     - Windows: `Directory inserita durante l'installazione di ESP-IDF (LINK SOPRA INDICATI)`
     - Linux: `Directory inserita durante l'installazione di ESP-IDF (LINK SOPRA INDICATI)`
5. **Click**: `Install` e aspetta **15-30 minuti**

> 🤖 **L'estensione installa automaticamente tutto il necessario:**
> - ESP-IDF Framework completo
> - Toolchain per ESP32-C6  
> - Python + dipendenze
> - OpenOCD, CMake, Ninja
> - Driver USB

### ✅ Passo 4: Test Installazione

1. **Command Palette**: `F1` → `ESP-IDF: Show Examples`
2. **Scegli**: `hello_world`
3. **Crea progetto** in una cartella di test
4. **Verifica target**: `esp32c6` (barra inferiore VS Code)
5. **Build**: `Ctrl+E B`

**🎉 Se il build completa senza errori, sei pronto!**

## Interfaccia VS Code ESP-IDF

### Barra Inferiore (Status Bar)
```
🎯 esp32c6 | 🔌 /dev/ttyUSB0 | 🔨 Build | ⚡ Flash | 📱 Monitor
```

### Comandi Principali (`F1`)
- `ESP-IDF: Set Target` → Seleziona ESP32-C6
- `ESP-IDF: Select Port` → Seleziona porta seriale  
- `ESP-IDF: Build Project` → Compila progetto
- `ESP-IDF: Flash Device` → Flash su ESP32
- `ESP-IDF: Monitor Device` → Monitor seriale
- `ESP-IDF: Show Examples` → Progetti esempio

### Shortcut Essenziali
- **`Ctrl+E B`** → Build
- **`Ctrl+E F`** → Flash
- **`Ctrl+E M`** → Monitor
- **`Ctrl+E D`** → Build + Flash + Monitor

## 🔌 Setup Hardware

### Connessione ESP32-C6
1. **Collega ESP32-C6** al PC via USB
2. **Seleziona porta** nella barra VS Code:
   - Linux: `/dev/ttyUSB0` o `/dev/ttyACM0`
   - Windows: `COM3`, `COM4`, ecc.

### Permessi Linux (se necessario)
```bash
sudo usermod -a -G dialout $USER
# Richiede logout/login
```

## 🧪 Test Completo

### Hello World Test
```
1. F1 → ESP-IDF: Show Examples
2. Cerca: "hello_world"  
3. Crea progetto test
4. Build: Ctrl+E B
5. Flash: Ctrl+E F  
6. Monitor: Ctrl+E M
```

### Output Atteso
```
Hello world!
This is esp32c6 chip with 1 CPU core(s), WiFi 6, BLE
Minimum free heap size: XXXXX bytes
Restarting in 10 seconds...
```

**🚀 Ambiente di sviluppo pronto!**

# 🏭 IoT ESP32 Modbus RTU - MQTT Bridge System

Sistema completo per la comunicazione tra ESP32C6 e centraline Modbus RTU, con architettura distribuita Kafka-MQTT e dashboard web per gestione e monitoraggio.

[![ESP32](https://img.shields.io/badge/ESP32-C6-red?style=flat-square&logo=espressif)](https://www.espressif.com/)
[![Docker](https://img.shields.io/badge/Docker-Compose-blue?style=flat-square&logo=docker)](https://docker.com/)
[![Python](https://img.shields.io/badge/Python-3.9+-yellow?style=flat-square&logo=python)](https://python.org/)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

## 🎯 Panoramica

### Cosa fa il sistema

Il progetto implementa un bridge IoT che permette la comunicazione bidirezionale tra dispositivi ESP32C6 e centraline industriali tramite protocollo Modbus RTU, utilizzando MQTT e Kafka per la distribuzione dei dati.

### Flusso principale

```
Centraline Modbus ←→ ESP32C6 ←→ MQTT ←→ Kafka Bridge ←→ Dashboard Web
```

### Caratteristiche principali

- **🔧 Captive Portal**: Configurazione iniziale ESP32 via web
- **⚙️ Template dinamici**: Configurazione registri da XML
- **📊 Dual Config**: Versione essenziale (ESP32) + completa (Dashboard)
- **✏️ Scrittura Modbus**: Write registers, coils e comandi predefiniti
- **🌐 Architettura scalabile**: Kafka-MQTT con Docker
- **📱 Dashboard moderna**: Monitoraggio real-time e controllo

## Architettura

### Componenti del sistema

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Centraline    │◄──►│     ESP32C6     │◄──►│   MQTT Bridge   │◄──►│    Dashboard    │
│   Industriali   │    │   (Modbus RTU)  │    │     (Kafka)     │    │   Web + APIs    │
└─────────────────┘    └─────────────────┘    └─────────────────┘    └─────────────────┘
```

### Stack tecnologico

- **ESP32C6**: Firmware C con ESP-IDF
- **Config Service**: Python Flask + Dashboard HTML/JS
- **Bridge**: Python con kafka-python e paho-mqtt
- **Infrastructure**: Docker Compose con Kafka, Zookeeper, Mosquitto
- **Storage**: Docker volumes per persistenza + ESP32 NVS

### 🔌 Setup Hardware e Cablaggio - ESP32C6 + MAX485 + Centralina Carel

<details>
<summary>🏗️ Architettura Sistema Completa</summary>
<pre><code>
                    ┌─────────────────┐
                    │    INTERNET     │
                    │                 │
                    └─────────┬───────┘
                              │
                              │ WiFi/Ethernet
                    ┌─────────▼───────┐
                    │      ROUTER     │
                    │                 │
                    └─────────┬───────┘
                              │ Network
                              │
          ┌───────────────────▼───────────────────┐
          │          DOCKER HOST SERVER           │
          │                                       │
          │                                       │
          │  ┌─────────┐  ┌─────────┐  ┌─────────┐│
          │  │ Config  │  │  Kafka  │  │  MQTT   ││
          │  │Service  │  │   +     │  │ Broker  ││
          │  │ :8080   │  │ Bridge  │  │ :1883   ││
          │  └─────────┘  └─────────┘  └─────────┘│
          └───────────────────▲───────────────────┘
                              │ WiFi MQTT
                              │
                    ┌─────────▼───────┐
                    │     ESP32C6     │
                    │     GATEWAY     │
                    │                 │
                    │                 │
                    └─────────┬───────┘
                              │ RS485 (MAX485)
                    ┌─────────▼───────┐
                    │   CENTRALINA    │
                    │  INDUSTRIALE    │
                    │                 │ 
                    │ Slave Addr: XXX │ 
                    └─────────────────┘
</code></pre>
</details>

<details>
<summary>⚡ Schema Elettrico Dettagliato ESP32C6 + MAX485</summary>
<pre><code>
╔═════════════╗       ╔═════════════╗       ╔══════════════════╗
║   ESP32C6   ║       ║  MAX485     ║       ║  CENTRALINA      ║
╠═════════════╣       ╠═════════════╣       ╠══════════════════╣
║             ║       ║             ║       ║                  ║
║ GPIO4 (TX) ────────> DI           ║       ║                  ║
║             ║       ║             ║       ║                  ║
║ GPIO5 (RX) <──────── RO           ║       ║                  ║
║             ║       ║             ║       ║                  ║
║ GPIO2 ─────────────> DE+RE        ║       ║                  ║
║             ║       ║             ║       ║                  ║
║ 5V ────────────────> VCC          ║       ║                  ║
║             ║       ║             ║       ║                  ║
║ GND ───────────────> GND ───────────────> GND                ║
╚════════════╝        ╠═════════════╣       ╠══════════════════╣
                      ║ A+ ────────────────> A+                ║
                      ║ B- ────────────────> B-                ║ 
                      ╚═════════════╝       ╚══════════════════╝
         
</code></pre>
</details>

📌 Note Implementative:
1. Alimentazione:
   - MAX485 alimentato a 5V dall'ESP32C6
   - GND comune a tutti i dispositivi

2. Collegamenti ESP32-MAX485:
   - DI → GPIO4 (TX)
   - RO → GPIO5 (RX)
   - DE+RE → GPIO2 (collegati assieme)

## ⚡ Quick Start
### 1. Accesso interfacce

- **Dashboard**: http://localhost:8080
- **Kafka UI**: http://localhost:8090
- **MQTT**: localhost:1883

### 2. Flash firmware ESP32

```bash
idf.py build flash monitor
```

### 3. Configurazione ESP32

1. ESP32 crea AP `DEVICE-xxxxxx` (password: `mosaico123`)
2. Connettiti e vai su http://192.168.4.1/config
3. Inserisci WiFi e broker MQTT (default: 192.168.1.100:1883)

### 4. Configurazione registri

1. Dashboard → dispositivi pending
2. Scegli template (MX, Dixell)
3. Configura slave address e parametri
4. ESP32 riceve config e inizia letture

## 🔧 Installazione

### Prerequisiti

- **Docker & Docker Compose** (v20.10+)
- **ESP-IDF** (v5.0+) 
- **Python 3.9+** (per development)
- **Hardware**: ESP32C6 + modulo RS485

## 📱 Configurazione ESP32

### Setup iniziale (Captive Portal)

L'ESP32 al primo avvio crea un access point per la configurazione.

#### 1. Connessione AP

- **SSID**: `DEVICE-xxxxxx` (xxxxxx = ultime 6 cifre MAC)
- **Password**: `mosaico123`
- **IP Gateway**: `192.168.4.1`

#### 2. Interfaccia web

Vai su http://192.168.4.1/config

**Parametri richiesti:**
- WiFi SSID e password
- IP broker MQTT 
- Porta MQTT (default: 1883)
- Configurazione IP (DHCP o statico)

#### 3. Salvataggio e riavvio

Dopo il salvataggio, ESP32 si riavvia e si connette al WiFi configurato.

### Device ID dinamico

L'ESP32 genera automaticamente un Device ID:
- **Iniziale**: `device_xxxxxx` (MAC based)
- **Post-config**: `{device_type}_{slave_address}` (es: `mpx_197`)

### Topic MQTT generati

```bash
# Configurazione (ricezione)
device/config/{device_id}/registers

# Dati (invio)
device/data/{device_id}/registers
device/data/{device_id}/status

# Scrittura (ricezione comandi)
device/write/{device_id}/register
device/write/{device_id}/coil  
device/write/{device_id}/command

# Feedback (invio risposte)
device/write/{device_id}/response
device/write/{device_id}/error
```

## ⚙️ Config Service

### Dashboard Web

La dashboard fornisce un'interfaccia completa per la gestione del sistema.

#### Funzionalità principali

- **Gestione dispositivi**: Visualizzazione pending e configurati
- **Template manager**: Selezione e configurazione template
- **Monitoraggio real-time**: Stato dispositivi e letture registri
- **Controllo Modbus**: Scrittura parametri e comandi
- **Diagnostics**: Health check e troubleshooting

#### Sezioni dashboard

1. **Statistiche generali**
   - Dispositivi totali, pending, configurati
   - Template disponibili
   - Stato broker MQTT

2. **Dispositivi pending** 
   - Lista ESP32 in attesa di configurazione
   - Pulsante "Configura" per setup registri

3. **Dispositivi configurati**
   - Tabella con stato, RSSI, registri
   - Pulsante "Controlla" per modal avanzato

4. **Modal controllo dispositivo**
   - **Tab Letture**: Visualizzazione registri
   - **Tab Parametri**: Scrittura registri scrivibili
   - **Tab Comandi**: Esecuzione comandi predefiniti

### API REST

Il Config Service espone API REST complete per tutte le operazioni.

#### Device Management

```bash
# Lista dispositivi pending
GET /api/pending_devices

# Lista dispositivi configurati  
GET /api/configured_devices

# Stato generale sistema
GET /api/dashboard_stats
```

#### Configuration

```bash
# Template disponibili
GET /api/available_templates

# Genera e invia configurazione
POST /api/generate_and_send_config
{
  "device_id": "device_abc123",
  "template": "mx", 
  "device_name": "mpx",
  "slave_address": 197,
  "baud_rate": 19200
}

# Configurazione dispositivo
GET /api/device/{device_id}/configuration?type=essential|complete

# Registri dispositivo
GET /api/device/{device_id}/registers
```

#### Write Operations

```bash
# Scrivi registro
POST /api/device/{device_id}/write_register
{
  "address": 123,
  "value": 1500,
  "register_name": "SetPoint"
}

# Scrivi coil
POST /api/device/{device_id}/write_coil  
{
  "address": 65,
  "value": 1,
  "coil_name": "Defrost"
}

# Invia comando
POST /api/device/{device_id}/send_command
{
  "command_name": "DeviceON",
  "address": 107,
  "value_command": 0
}
```

## 🎮 Scrittura Modbus

Il sistema supporta la scrittura bidirezionale su dispositivi Modbus RTU.

### Tipi di scrittura supportati

#### 1. Write Register (Function Code 0x06)

Scrittura registro holding singolo.

```bash
# API
POST /api/device/mpx_197/write_register
{
  "address": 45,
  "value": 2250,  
  "register_name": "Temperature_SetPoint"
}

# Flusso
Dashboard → Config Service → Kafka → Bridge → MQTT → ESP32 → Modbus → Centralina
```

#### 2. Write Coil (Function Code 0x05)

Scrittura coil singolo (ON/OFF).

```bash
# API  
POST /api/device/mpx_197/write_coil
{
  "address": 65,
  "value": 1,
  "coil_name": "Defrost_Enable"
}
```

#### 3. Send Command (Comandi Predefiniti)

Esecuzione comandi configurati nel template.

```bash
# API
POST /api/device/mpx_197/send_command  
{
  "command_name": "StartDefrost",
  "address": 65,
  "value_command": 1,
  "alias": "Avvia Sbrinamento"
}
```

### Feedback e conferme

Ogni operazione di scrittura genera feedback automatico:

```json
// Successo
{
  "datetime": "2024-06-30 15:30:45",
  "device_id": "mpx_197", 
  "command_type": "write_register",
  "success": true,
  "message": "Registro 45 scritto con valore 2250"
}

// Errore
{
  "datetime": "2024-06-30 15:30:45",
  "device_id": "mpx_197",
  "command_type": "write_register", 
  "error": "Timeout Modbus - device non risponde"
}
```

## 📊 Template System

### Dual Configuration System

Il sistema genera due tipi di configurazioni da ogni template XML:

#### Configurazione Essenziale (per ESP32)

Contiene solo i campi necessari per l'ESP32:

```json
{
  "metadata": {
    "device": "mpx",
    "slave_address": 197,
    "baud_rate": 19200,
    "total_registers": 392,
    "total_commands": 7
  },
  "holding_registers": [
    {
      "address": 14,
      "name": "Param1", 
      "register_type": "Register"
    }
  ],
  "coils": [...],
  "commands": [
    {
      "address": 65,
      "name": "Defrost",
      "register_type": "Coils",
      "value_command": 1
    }
  ]
}
```

#### Configurazione Completa (per Dashboard)

Include tutti i parametri per dashboard:

```json
{
  "holding_registers": [
    {
      "address": 14,
      "name": "Param1",
      "register_type": "Register",
      "decimals": 1,
      "gain": 1.0,
      "measurement": "°C",
      "descriptions": {
        "it": "Sonda seriale S8",
        "en": "Serial probe S8"  
      },
      "source": "Parameters",
      "access_level": "2",
      "access_write_level": "12"
      ...
    }
  ]
}
```

### Template XML supportati

#### MPXProV4.xml (CAREL MX)
- **Applicazione**: Centraline refrigerazione CAREL
- **Registri**: ~400 tra holding registers e coils
- **Comandi**: 7 comandi predefiniti (Defrost, Device ON/OFF, etc.)
- **Caratteristiche**: Multi-lingua, parametri configurazione completa

#### XR75CX_9_8_NT.xml (Dixell)  
- **Applicazione**: Controller Dixell per refrigerazione
- **Registri**: Configurazione parametri e letture
- **Comandi**: Comandi controllo specifici Dixell

### Aggiunta nuovi template

1. **Crea file XML** in `/templates/xml/`
2. **Segui struttura** esistente con sezioni:
   - `<ContinuosRead>`: Registri di lettura continua
   - `<Parameters>`: Parametri scrivibili  
   - `<Commands>`: Comandi predefiniti
3. **Riavvia Config Service** per rilevamento automatico
4. **Test** tramite dashboard

### Parser XML

Il parser `xml_parser.py` gestisce:
- **Parsing struttura XML** complessa con namespaces
- **Estrazione multilingua** (IT/EN)
- **Validazione parametri** (range, tipi, etc.)
- **Generazione dual config** ottimizzata
- **Gestione errori** e logging dettagliato

## 📡 MQTT Topics

### Struttura topic

Tutti i topic seguono la convenzione: `device/{category}/{device_id}/{type}`

### Topic di configurazione

```bash
# ESP32 si sottoscrive per ricevere configurazioni
device/config/{device_id}/registers

# Esempio: device/config/mpx_197/registers
```

### Topic dati ESP32

```bash  
# Dati registri Modbus
device/data/{device_id}/registers

# Status dispositivo
device/data/{device_id}/status

# Errori e diagnostics
device/data/{device_id}/errors
```

### Topic comandi scrittura

```bash
# Scrittura registro holding
device/write/{device_id}/register

# Scrittura coil
device/write/{device_id}/coil

# Comando predefinito
device/write/{device_id}/command
```

### Topic feedback

```bash
# Conferma operazione riuscita
device/write/{device_id}/response

# Errore operazione
device/write/{device_id}/error
```

### Esempi payload

#### Status Message
```json
{
  "datetime": "2024-06-30 15:30:45",
  "timestamp_ms": 1719754245000,
  "device_id": "mpx_197",
  "status": "online",
  "device_type": "mpx", 
  "slave_address": 197,
  "total_registers": 392,
  "total_commands": 7,
  "uptime_seconds": 3600,
  "free_heap_bytes": 180000,
  "wifi_rssi": -45,
  "config_loaded": true,
  "write_support": true
}
```

#### Register Data
```json
{
  "datetime": "2024-06-30 15:30:45",
  "timestamp_ms": 1719754245000,
  "device_id": "mpx_197",
  "slave_address": 197,
  "registers": [
    {
      "address": 14,
      "name": "Param1",
      "value": 1250,
      "type": "Register",
      "register_type": "Register",
      "composite_key": "14_Register"
    }
  ]
}
```

#### Write Command
```json
{
  "device_id": "mpx_197",
  "command_type": "write_register",
  "timestamp": "2024-06-30 15:30:45", 
  "timestamp_ms": 1719754245000,
  "address": 45,
  "value": 2250,
  "register_name": "SetPoint",
  "source": "dashboard_api"
}
```

## 🔍 Monitoring

### Dashboard di sistema

#### Statistiche principali
- **Dispositivi totali**: Pending + Configurati
- **Template disponibili**: Count template XML caricati
- **Stato broker**: Online/Offline con uptime
- **Messaggi elaborati**: Counter totale

#### Monitoring dispositivi

**Dispositivi pending:**
- Device ID temporaneo
- Tempo rilevamento
- Stato WiFi (RSSI)
- Heap memory ESP32

**Dispositivi configurati:**
- Device ID finale
- Tipo e slave address
- Numero registri configurati
- Stato connessione (online/offline)
- Ultimo dato ricevuto
- Supporto scrittura

### Kafka UI

Accesso: http://localhost:8090

**Funzionalità:**
- **Topics**: Lista e dettagli topic Kafka
- **Messages**: Ispezione messaggi in real-time
- **Consumers**: Stato consumer groups
- **Performance**: Metriche throughput e latenza

### Logs e debugging

#### ESP32 Serial Monitor
```bash
cd firmware/
idf.py monitor

# Output esempio:
# I (12345) DEVICE_MASTER: ✅ Configurazione caricata da MQTT
# I (12346) DEVICE_MASTER: 📊 Device: mpx, Slave: 197, Registri: 392
# I (12347) DEVICE_MASTER: 🚀 Avvio lettura registri...
```

#### Docker Services Logs
```bash
# Tutti i servizi
docker-compose logs -f

# Config Service
docker logs -f config-service

# Bridge con filtro
docker logs -f kafka-mqtt-bridge | grep "Write command"
```

#### MQTT Real-time Monitoring
```bash
# Tutti i topic
mosquitto_sub -h localhost -t "device/+/+/+"

# Solo dati
mosquitto_sub -h localhost -t "device/data/+/+"

# Solo comandi scrittura
mosquitto_sub -h localhost -t "device/write/+/+"
```

### Health checks automatici

Il sistema include health check automatici:

#### Config Service Health
```bash
GET /health

Response:
{
  "status": "OK",
  "service": "config-service-dual-persistent-storage-with-commands", 
  "kafka": "connected",
  "mqtt_broker": "running",
  "connected_devices": 3,
  "pending_devices": 1,
  "persistent_storage": {
    "exists": true,
    "writable": true,
    "essential_configs_cached": 3,
    "complete_configs_cached": 3
  },
  "features": [
    "dashboard", "broker_control", "device_monitoring",
    "dynamic_config", "dual_persistent_config_storage", 
    "modbus_write_commands"
  ]
}
```



## 📄 License

Questo progetto è rilasciato sotto **MIT License**.

```
MIT License

Copyright (c) 2024 IoT ESP32 Modbus Bridge

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## 👥 Autori e Riconoscimenti

### Autori principali
- **[Soufian Markouni]** 
- **[Riccardo Lunardelli]**


---

<div align="center">



[![ESP32](https://img.shields.io/badge/ESP32-C6-red?style=flat-square&logo=espressif)](https://www.espressif.com/)
[![Docker](https://img.shields.io/badge/Docker-Compose-blue?style=flat-square&logo=docker)](https://docker.com/)
[![Kafka](https://img.shields.io/badge/Apache-Kafka-orange?style=flat-square&logo=apache-kafka)](https://kafka.apache.org/)
[![MQTT](https://img.shields.io/badge/MQTT-Mosquitto-green?style=flat-square&logo=eclipse-mosquitto)](https://mosquitto.org/)
</div>
