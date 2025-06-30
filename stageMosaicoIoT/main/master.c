#include <stdio.h>
#include <inttypes.h>
#include <string.h>
#include <time.h>
#include "driver/uart.h"
#include "driver/gpio.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/event_groups.h"
#include "cJSON.h"
#include "esp_spiffs.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "nvs_flash.h"
#include "esp_http_server.h"
#include "esp_netif.h"
#include "lwip/inet.h"
#include "lwip/netdb.h"
#include "lwip/sockets.h"
#include "lwip/err.h"
#include "lwip/sys.h"
#include "lwip/dns.h"
#include "esp_mac.h"
#include "nvs.h"
#include "mqtt_client.h"
#include "esp_sntp.h"

// Definizioni di base
char dynamic_ap_ssid[32];
#define AP_PASS "mosaico123"
#define AP_MAX_STA_CONN 4
#define AP_CHANNEL 1
#define DEFAULT_MQTT_BROKER "192.168.1.100"
#define DEFAULT_MQTT_PORT 1883
#define WIFI_CONNECT_TIMEOUT_MS 30000
#define CONFIG_TIMEOUT_MS 300000
#define MAX_WIFI_RETRY 3
#define TXD_PIN (GPIO_NUM_4)
#define RXD_PIN (GPIO_NUM_5)
#define DE_RE_PIN (GPIO_NUM_2)
#define UART_PORT_NUM UART_NUM_1
#define MAX_REGISTERS 400
#define MAX_COMMANDS 50
#define MAX_NAME_LEN 24
#define MAX_UNIT_LEN 12
#define MAX_DESC_LEN 64
#define NVS_NAMESPACE "device_config"
#define NVS_WIFI_SSID "wifi_ssid"
#define NVS_WIFI_PASS "wifi_pass"
#define NVS_MQTT_BROKER "mqtt_broker"
#define NVS_MQTT_PORT "mqtt_port"
#define NVS_STATIC_IP "static_ip"
#define NVS_GATEWAY "gateway"
#define NVS_NETMASK "netmask"
#define NVS_USE_STATIC_IP "use_static_ip"
#define NVS_CONFIG_DONE "config_done"
#define NVS_DEVICE_ID "device_id"
#define NVS_DEVICE_CONFIG "device_config_json"
#define RESET_PASSWORD "mosaico123"

// Chunked storage definitions
#define NVS_CHUNK_SIZE 3500
#define NVS_CONFIG_CHUNKS "config_chunks"
#define NVS_CONFIG_TOTAL_SIZE "config_size"
#define MAX_CONFIG_CHUNKS 20

static const char* TAG = "DEVICE_MASTER";

// MQTT Topics
#define MQTT_TOPIC_CONFIG_PREFIX "device/config/"
#define MQTT_TOPIC_DATA_PREFIX "device/data/"
#define MQTT_TOPIC_WRITE_PREFIX "device/write/"
#define MQTT_TOPIC_STATUS_SUFFIX "/status"
#define MQTT_TOPIC_REGISTERS_SUFFIX "/registers"
#define MQTT_TOPIC_ERRORS_SUFFIX "/errors"
#define MQTT_TOPIC_WRITE_REGISTER_SUFFIX "/register"
#define MQTT_TOPIC_WRITE_COIL_SUFFIX "/coil"
#define MQTT_TOPIC_WRITE_COMMAND_SUFFIX "/command"
#define MQTT_TOPIC_WRITE_RESPONSE_SUFFIX "/response"
#define MQTT_TOPIC_WRITE_ERROR_SUFFIX "/error"

typedef enum {
    STATE_INIT,
    STATE_CONFIG_MODE,
    STATE_CONNECTING,
    STATE_RUNNING,
    STATE_ERROR
} system_state_t;

static system_state_t current_state = STATE_INIT;
static EventGroupHandle_t wifi_event_group;
static EventGroupHandle_t mqtt_event_group;
#define WIFI_CONNECTED_BIT BIT0
#define CONFIG_DONE_BIT BIT1
#define MQTT_CONNECTED_BIT BIT2
#define CONFIG_RECEIVED_BIT BIT3

static bool wifi_connected = false;
static bool mqtt_connected = false;
static bool config_mode = false;
static bool config_loaded_from_mqtt = false;
static httpd_handle_t config_server = NULL;
static esp_mqtt_client_handle_t mqtt_client = NULL;

// Buffer per messaggi MQTT frammentati
static char* mqtt_config_buffer = NULL;
static size_t mqtt_config_buffer_size = 0;
static size_t mqtt_config_received = 0;
static size_t mqtt_config_total = 0;
static bool mqtt_config_receiving = false;

// Configurazione salvata
typedef struct {
    char wifi_ssid[64];
    char wifi_pass[64];
    char mqtt_broker[64];
    uint16_t mqtt_port;
    char static_ip[16];
    char gateway[16];
    char netmask[16];
    bool use_static_ip;
    bool config_done;
} device_wifi_config_t;

static device_wifi_config_t saved_config = {0};

// Device ID dinamico
static char device_id[32] = {0};

// Struttura registro
typedef struct {
    uint16_t address;
    char name[MAX_NAME_LEN];
    char register_type[12];
    uint16_t current_value;
    uint32_t last_read_time;
} device_register_t;

// 🆕 NUOVO: Struttura comando
typedef struct {
    uint16_t address;
    char name[MAX_NAME_LEN];
    char register_type[12];
    uint16_t value_command;
    char alias[MAX_NAME_LEN];
} device_command_t;

// Configurazione globale
typedef struct {
    char version[16];
    char device[16];
    uint8_t slave_address;
    uint32_t baud_rate;
    char template_id[64];
    uint16_t total_registers;
    uint16_t total_commands;
    device_register_t holding_registers[MAX_REGISTERS];
    device_register_t coils[MAX_REGISTERS];
    device_command_t commands[MAX_COMMANDS];
    uint16_t holding_count;
    uint16_t coils_count;
    uint16_t commands_count;
    bool config_loaded;
} device_config_t;

device_config_t device_config = {0};

// Forward declarations
esp_err_t load_wifi_config(void);
esp_err_t save_wifi_config(void);
esp_err_t clear_wifi_config(void);
esp_err_t start_wifi_sta(void);
void wifi_init(void);
esp_err_t init_spiffs(void);
char* load_html_file(const char* filename);
void print_register_value(device_register_t* reg, uint16_t value, const char* actual_type);
void read_all_registers(void);
void start_config_mode(void);
void start_running_server(void);
void config_task(void *pvParameters);
void generate_device_id_early(void);
void update_device_id(void);
esp_err_t load_device_config(void);
esp_err_t save_device_config_chunked(const char* json_str, size_t json_len);
esp_err_t load_device_config_chunked(void);
void get_current_datetime(char* buffer, size_t buffer_size);
esp_err_t send_mqtt_status_enhanced(const char* status);
esp_err_t send_mqtt_register_data(device_register_t* reg, uint16_t raw_value, const char* actual_type);
void handle_mqtt_config(const char* data, int data_len);
void handle_mqtt_config_with_save(const char* data, int data_len);
esp_err_t wait_for_mqtt_config(void);
void init_sntp(void);
void cleanup_mqtt_config_buffer(void);
void handle_fragmented_mqtt_message(esp_mqtt_event_handle_t event);
void print_memory_info(const char* context);
void print_nvs_stats(void);
void validate_loaded_config(void);
void post_config_diagnostics(void);
void init_uart(uint32_t baud_rate);

// 🆕 NUOVE: Forward declarations per scrittura Modbus
uint16_t modbus_crc16(const uint8_t *data, uint16_t length);
bool read_modbus_register(uint16_t reg_addr, uint16_t *value, bool is_coil);
bool write_modbus_register(uint16_t reg_addr, uint16_t value);
bool write_modbus_coil(uint16_t coil_addr, bool value);
void handle_mqtt_write_command(const char* topic, const char* data, int data_len);
esp_err_t send_mqtt_write_response(const char* command_type, bool success, const char* message);
esp_err_t send_mqtt_write_error(const char* command_type, const char* error_msg);

// Debug and monitoring functions
void print_memory_info(const char* context) {
    size_t free_heap = esp_get_free_heap_size();
    size_t min_free_heap = esp_get_minimum_free_heap_size();
    
    ESP_LOGI(TAG, "🔍 Memory Info [%s]:", context);
    ESP_LOGI(TAG, "   💾 Free Heap: %lu bytes (%.1f KB)", (unsigned long)free_heap, free_heap / 1024.0);
    ESP_LOGI(TAG, "   📉 Min Free: %lu bytes (%.1f KB)", (unsigned long)min_free_heap, min_free_heap / 1024.0);
    
    if (free_heap < 50000) {
        ESP_LOGW(TAG, "⚠️  Memoria bassa!");
    }
}

void print_nvs_stats(void) {
    nvs_stats_t nvs_stats;
    esp_err_t err = nvs_get_stats(NULL, &nvs_stats);
    if (err == ESP_OK) {
        ESP_LOGI(TAG, "📊 NVS Statistics:");
        ESP_LOGI(TAG, "   Used entries: %d", nvs_stats.used_entries);
        ESP_LOGI(TAG, "   Free entries: %d", nvs_stats.free_entries);
        ESP_LOGI(TAG, "   Total entries: %d", nvs_stats.total_entries);
        ESP_LOGI(TAG, "   Namespace count: %d", nvs_stats.namespace_count);
        
        float usage = (float)nvs_stats.used_entries / nvs_stats.total_entries * 100;
        ESP_LOGI(TAG, "   📈 Usage: %.1f%%", usage);
        
        if (usage > 80.0) {
            ESP_LOGW(TAG, "⚠️  NVS quasi pieno!");
        }
    }
}

void validate_loaded_config(void) {
    if (!device_config.config_loaded) {
        ESP_LOGE(TAG, "❌ Configurazione non caricata!");
        return;
    }
    
    ESP_LOGI(TAG, "✅ Validazione configurazione:");
    ESP_LOGI(TAG, "   📋 Device: '%s'", device_config.device);
    ESP_LOGI(TAG, "   🏷️  Version: '%s'", device_config.version);
    ESP_LOGI(TAG, "   📡 Slave Address: %d", device_config.slave_address);
    ESP_LOGI(TAG, "   📊 Holding Registers: %d", device_config.holding_count);
    ESP_LOGI(TAG, "   🔘 Coils: %d", device_config.coils_count);
    ESP_LOGI(TAG, "   🎮 Commands: %d", device_config.commands_count);
    ESP_LOGI(TAG, "   📈 Total Config: %d", device_config.total_registers);
    
    uint16_t actual_total = device_config.holding_count + device_config.coils_count;
    if (actual_total != device_config.total_registers) {
        ESP_LOGW(TAG, "⚠️  Discrepanza conteggio: %d effettivi vs %d configurati", 
                 actual_total, device_config.total_registers);
    }
    
    // Mostra primi 5 registri di ogni tipo
    for (int i = 0; i < device_config.holding_count && i < 5; i++) {
        ESP_LOGI(TAG, "   📊 Holding[%d]: addr=%d, name='%s', type='%s'", 
                 i, device_config.holding_registers[i].address,
                 device_config.holding_registers[i].name,
                 device_config.holding_registers[i].register_type);
    }
    
    for (int i = 0; i < device_config.coils_count && i < 5; i++) {
        ESP_LOGI(TAG, "   🔘 Coil[%d]: addr=%d, name='%s', type='%s'", 
                 i, device_config.coils[i].address,
                 device_config.coils[i].name,
                 device_config.coils[i].register_type);
    }
    
    // 🆕 NUOVO: Mostra primi 5 comandi
    for (int i = 0; i < device_config.commands_count && i < 5; i++) {
        ESP_LOGI(TAG, "   🎮 Command[%d]: addr=%d, name='%s', value=%d", 
                 i, device_config.commands[i].address,
                 device_config.commands[i].name,
                 device_config.commands[i].value_command);
    }
}

void post_config_diagnostics(void) {
    print_memory_info("Post-Config");
    print_nvs_stats();
    validate_loaded_config();
}

// Chunked NVS Storage Functions
esp_err_t save_device_config_chunked(const char* json_str, size_t json_len) {
    nvs_handle_t nvs_handle;
    esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READWRITE, &nvs_handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Errore apertura NVS per chunked save: %s", esp_err_to_name(err));
        return err;
    }

    ESP_LOGI(TAG, "Salvando configurazione in chunks (%zu bytes totali)", json_len);

    size_t total_chunks = (json_len + NVS_CHUNK_SIZE - 1) / NVS_CHUNK_SIZE;
    
    if (total_chunks > MAX_CONFIG_CHUNKS) {
        ESP_LOGE(TAG, "Configurazione troppo grande: %zu chunks (max %d)", total_chunks, MAX_CONFIG_CHUNKS);
        nvs_close(nvs_handle);
        return ESP_ERR_NO_MEM;
    }

    ESP_LOGI(TAG, "Dividendo in %zu chunks da %d bytes", total_chunks, NVS_CHUNK_SIZE);

    err = nvs_set_u32(nvs_handle, NVS_CONFIG_TOTAL_SIZE, (uint32_t)json_len);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Errore salvataggio dimensione totale: %s", esp_err_to_name(err));
        nvs_close(nvs_handle);
        return err;
    }

    err = nvs_set_u32(nvs_handle, NVS_CONFIG_CHUNKS, (uint32_t)total_chunks);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Errore salvataggio numero chunks: %s", esp_err_to_name(err));
        nvs_close(nvs_handle);
        return err;
    }

    for (size_t i = 0; i < total_chunks; i++) {
        char chunk_key[32];
        snprintf(chunk_key, sizeof(chunk_key), "chunk_%zu", i);
        
        size_t chunk_start = i * NVS_CHUNK_SIZE;
        size_t chunk_size = (chunk_start + NVS_CHUNK_SIZE > json_len) ? 
                           (json_len - chunk_start) : NVS_CHUNK_SIZE;
        
        char* chunk_data = malloc(chunk_size + 1);
        if (!chunk_data) {
            ESP_LOGE(TAG, "Errore allocazione memoria per chunk %zu", i);
            nvs_close(nvs_handle);
            return ESP_ERR_NO_MEM;
        }
        
        memcpy(chunk_data, json_str + chunk_start, chunk_size);
        chunk_data[chunk_size] = '\0';
        
        err = nvs_set_str(nvs_handle, chunk_key, chunk_data);
        free(chunk_data);
        
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "Errore salvataggio chunk %zu: %s", i, esp_err_to_name(err));
            nvs_close(nvs_handle);
            return err;
        }
        
        ESP_LOGI(TAG, "Chunk %zu/%zu salvato (%zu bytes)", i+1, total_chunks, chunk_size);
    }

    err = nvs_commit(nvs_handle);
    nvs_close(nvs_handle);
    
    if (err == ESP_OK) {
        ESP_LOGI(TAG, "Configurazione chunked salvata con successo (%zu chunks)", total_chunks);
    } else {
        ESP_LOGE(TAG, "Errore commit NVS chunked: %s", esp_err_to_name(err));
    }
    
    return err;
}

esp_err_t load_device_config_chunked(void) {
    nvs_handle_t nvs_handle;
    esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READONLY, &nvs_handle);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "NVS non inizializzato per chunked load: %s", esp_err_to_name(err));
        return err;
    }

    uint32_t total_chunks = 0;
    uint32_t total_size = 0;
    
    err = nvs_get_u32(nvs_handle, NVS_CONFIG_CHUNKS, &total_chunks);
    if (err != ESP_OK) {
        nvs_close(nvs_handle);
        ESP_LOGW(TAG, "Numero chunks non trovato, fallback al metodo tradizionale");
        return ESP_ERR_NOT_FOUND;
    }
    
    err = nvs_get_u32(nvs_handle, NVS_CONFIG_TOTAL_SIZE, &total_size);
    if (err != ESP_OK) {
        nvs_close(nvs_handle);
        ESP_LOGE(TAG, "Dimensione totale chunks non trovata: %s", esp_err_to_name(err));
        return err;
    }

    ESP_LOGI(TAG, "Caricando configurazione chunked: %"PRIu32" chunks, %"PRIu32" bytes totali", total_chunks, total_size);

    char* complete_json = malloc(total_size + 1);
    if (!complete_json) {
        nvs_close(nvs_handle);
        ESP_LOGE(TAG, "Errore allocazione memoria per configurazione completa");
        return ESP_ERR_NO_MEM;
    }

    size_t current_pos = 0;
    
    for (uint32_t i = 0; i < total_chunks; i++) {
        char chunk_key[32];
        snprintf(chunk_key, sizeof(chunk_key), "chunk_%"PRIu32, i);
        
        size_t chunk_size = 0;
        err = nvs_get_str(nvs_handle, chunk_key, NULL, &chunk_size);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "Errore dimensione chunk %"PRIu32": %s", i, esp_err_to_name(err));
            free(complete_json);
            nvs_close(nvs_handle);
            return err;
        }
        
        char* chunk_data = malloc(chunk_size);
        if (!chunk_data) {
            ESP_LOGE(TAG, "Errore allocazione chunk %"PRIu32, i);
            free(complete_json);
            nvs_close(nvs_handle);
            return ESP_ERR_NO_MEM;
        }
        
        err = nvs_get_str(nvs_handle, chunk_key, chunk_data, &chunk_size);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "Errore lettura chunk %"PRIu32": %s", i, esp_err_to_name(err));
            free(chunk_data);
            free(complete_json);
            nvs_close(nvs_handle);
            return err;
        }
        
        size_t copy_size = (i == total_chunks - 1) ? (chunk_size - 1) : (chunk_size - 1);
        if (current_pos + copy_size > total_size) {
            copy_size = total_size - current_pos;
        }
        
        memcpy(complete_json + current_pos, chunk_data, copy_size);
        current_pos += copy_size;
        
        free(chunk_data);
        ESP_LOGI(TAG, "Chunk %"PRIu32"/%"PRIu32" caricato (%zu bytes)", i+1, total_chunks, copy_size);
    }
    
    nvs_close(nvs_handle);
    complete_json[total_size] = '\0';

    ESP_LOGI(TAG, "Configurazione chunked ricostruita (%zu bytes)", current_pos);
    
    handle_mqtt_config(complete_json, current_pos);
    free(complete_json);

    if (device_config.config_loaded) {
        ESP_LOGI(TAG, "Configurazione chunked caricata con successo");
        config_loaded_from_mqtt = false;
        update_device_id();
        return ESP_OK;
    } else {
        ESP_LOGE(TAG, "Errore parsing configurazione chunked");
        return ESP_FAIL;
    }
}

// 🆕 NUOVE: Funzioni per scrittura Modbus
bool write_modbus_register(uint16_t reg_addr, uint16_t value) {
    ESP_LOGI(TAG, "🔧 Scrittura registro Modbus: addr=%d, value=%d", reg_addr, value);
    
    uint8_t request[8];
    request[0] = device_config.slave_address;
    request[1] = 0x06;  // Write Single Register
    request[2] = (reg_addr >> 8) & 0xFF;
    request[3] = reg_addr & 0xFF;
    request[4] = (value >> 8) & 0xFF;
    request[5] = value & 0xFF;
    
    uint16_t crc = modbus_crc16(request, 6);
    request[6] = crc & 0xFF;
    request[7] = (crc >> 8) & 0xFF;
    
    // Invia comando
    uart_flush_input(UART_PORT_NUM);
    gpio_set_level(DE_RE_PIN, 1);
    vTaskDelay(pdMS_TO_TICKS(10));
    uart_write_bytes(UART_PORT_NUM, (const char *)request, sizeof(request));
    uart_wait_tx_done(UART_PORT_NUM, pdMS_TO_TICKS(100));
    gpio_set_level(DE_RE_PIN, 0);
    vTaskDelay(pdMS_TO_TICKS(50));
    
    // Leggi risposta
    uint8_t response[16];
    int len = uart_read_bytes(UART_PORT_NUM, response, sizeof(response), pdMS_TO_TICKS(1000));
    
    if (len >= 8) {
        if (response[0] == device_config.slave_address && response[1] == 0x06) {
            uint16_t received_crc = response[6] | (response[7] << 8);
            uint16_t calculated_crc = modbus_crc16(response, 6);
            
            if (received_crc == calculated_crc) {
                uint16_t echo_addr = (response[2] << 8) | response[3];
                uint16_t echo_value = (response[4] << 8) | response[5];
                
                if (echo_addr == reg_addr && echo_value == value) {
                    ESP_LOGI(TAG, "✅ Scrittura registro completata con successo");
                    return true;
                }
            }
        } else if (response[0] == device_config.slave_address && (response[1] & 0x80)) {
            ESP_LOGE(TAG, "❌ Errore Modbus: exception code 0x%02X", response[2]);
        }
    }
    
    ESP_LOGE(TAG, "❌ Scrittura registro fallita");
    return false;
}

bool write_modbus_coil(uint16_t coil_addr, bool value) {
    ESP_LOGI(TAG, "🔧 Scrittura coil Modbus: addr=%d, value=%s", coil_addr, value ? "ON" : "OFF");
    
    uint8_t request[8];
    request[0] = device_config.slave_address;
    request[1] = 0x05;  // Write Single Coil
    request[2] = (coil_addr >> 8) & 0xFF;
    request[3] = coil_addr & 0xFF;
    request[4] = value ? 0xFF : 0x00;
    request[5] = 0x00;
    
    uint16_t crc = modbus_crc16(request, 6);
    request[6] = crc & 0xFF;
    request[7] = (crc >> 8) & 0xFF;
    
    // Invia comando
    uart_flush_input(UART_PORT_NUM);
    gpio_set_level(DE_RE_PIN, 1);
    vTaskDelay(pdMS_TO_TICKS(10));
    uart_write_bytes(UART_PORT_NUM, (const char *)request, sizeof(request));
    uart_wait_tx_done(UART_PORT_NUM, pdMS_TO_TICKS(100));
    gpio_set_level(DE_RE_PIN, 0);
    vTaskDelay(pdMS_TO_TICKS(50));
    
    // Leggi risposta
    uint8_t response[16];
    int len = uart_read_bytes(UART_PORT_NUM, response, sizeof(response), pdMS_TO_TICKS(1000));
    
    if (len >= 8) {
        if (response[0] == device_config.slave_address && response[1] == 0x05) {
            uint16_t received_crc = response[6] | (response[7] << 8);
            uint16_t calculated_crc = modbus_crc16(response, 6);
            
            if (received_crc == calculated_crc) {
                uint16_t echo_addr = (response[2] << 8) | response[3];
                uint16_t echo_value = (response[4] << 8) | response[5];
                
                if (echo_addr == coil_addr && echo_value == (value ? 0xFF00 : 0x0000)) {
                    ESP_LOGI(TAG, "✅ Scrittura coil completata con successo");
                    return true;
                }
            }
        } else if (response[0] == device_config.slave_address && (response[1] & 0x80)) {
            ESP_LOGE(TAG, "❌ Errore Modbus: exception code 0x%02X", response[2]);
        }
    }
    
    ESP_LOGE(TAG, "❌ Scrittura coil fallita");
    return false;
}

// 🆕 NUOVO: Handler per comandi di scrittura MQTT
void handle_mqtt_write_command(const char* topic, const char* data, int data_len) {
    ESP_LOGI(TAG, "🎮 Ricevuto comando scrittura: %s", topic);
    
    cJSON *json = cJSON_Parse(data);
    if (!json) {
        ESP_LOGE(TAG, "❌ Errore parsing JSON comando scrittura");
        send_mqtt_write_error("unknown", "JSON non valido");
        return;
    }
    
    cJSON *command_type = cJSON_GetObjectItem(json, "command_type");
    cJSON *address = cJSON_GetObjectItem(json, "address");
    cJSON *value = cJSON_GetObjectItem(json, "value");
    
    if (!command_type || !cJSON_IsString(command_type) || !address || !cJSON_IsNumber(address)) {
        ESP_LOGE(TAG, "❌ Campi comando mancanti o non validi");
        send_mqtt_write_error("unknown", "Campi richiesti mancanti");
        cJSON_Delete(json);
        return;
    }
    
    const char* cmd_type = command_type->valuestring;
    uint16_t addr = address->valueint;
    bool success = false;
    char response_msg[128];
    
    if (strcmp(cmd_type, "write_register") == 0) {
        if (!value || !cJSON_IsNumber(value)) {
            send_mqtt_write_error(cmd_type, "Valore registro mancante");
            cJSON_Delete(json);
            return;
        }
        
        uint16_t reg_value = value->valueint;
        success = write_modbus_register(addr, reg_value);
        
        if (success) {
            snprintf(response_msg, sizeof(response_msg), "Registro %d scritto con valore %d", addr, reg_value);
        } else {
            snprintf(response_msg, sizeof(response_msg), "Errore scrittura registro %d", addr);
        }
        
    } else if (strcmp(cmd_type, "write_coil") == 0) {
        if (!value || !cJSON_IsNumber(value)) {
            send_mqtt_write_error(cmd_type, "Valore coil mancante");
            cJSON_Delete(json);
            return;
        }
        
        bool coil_value = (value->valueint != 0);
        success = write_modbus_coil(addr, coil_value);
        
        if (success) {
            snprintf(response_msg, sizeof(response_msg), "Coil %d scritto con valore %s", addr, coil_value ? "ON" : "OFF");
        } else {
            snprintf(response_msg, sizeof(response_msg), "Errore scrittura coil %d", addr);
        }
        
    } else if (strcmp(cmd_type, "send_command") == 0) {
        // Per i comandi predefiniti, usa value_command invece di value
        cJSON *value_command = cJSON_GetObjectItem(json, "value_command");
        if (!value_command || !cJSON_IsNumber(value_command)) {
            send_mqtt_write_error(cmd_type, "value_command mancante");
            cJSON_Delete(json);
            return;
        }
        
        cJSON *command_name = cJSON_GetObjectItem(json, "command_name");
        const char* cmd_name = (command_name && cJSON_IsString(command_name)) ? command_name->valuestring : "Unknown";
        
        // I comandi sono sempre coils, usa value_command
        bool cmd_value = (value_command->valueint != 0);
        success = write_modbus_coil(addr, cmd_value);
        
        if (success) {
            snprintf(response_msg, sizeof(response_msg), "Comando '%s' eseguito (addr=%d, val=%s)", 
                     cmd_name, addr, cmd_value ? "ON" : "OFF");
        } else {
            snprintf(response_msg, sizeof(response_msg), "Errore esecuzione comando '%s' (addr=%d)", cmd_name, addr);
        }
        
    } else {
        ESP_LOGE(TAG, "❌ Tipo comando sconosciuto: %s", cmd_type);
        send_mqtt_write_error(cmd_type, "Tipo comando non supportato");
        cJSON_Delete(json);
        return;
    }
    
    // Invia feedback
    if (success) {
        send_mqtt_write_response(cmd_type, true, response_msg);
    } else {
        send_mqtt_write_error(cmd_type, response_msg);
    }
    
    cJSON_Delete(json);
}

// 🆕 NUOVO: Invio risposta positiva scrittura
esp_err_t send_mqtt_write_response(const char* command_type, bool success, const char* message) {
    if (!mqtt_connected || mqtt_client == NULL) {
        ESP_LOGW(TAG, "MQTT non connesso per write response");
        return ESP_FAIL;
    }
    
    char topic[128];
    snprintf(topic, sizeof(topic), "%s%s%s", MQTT_TOPIC_WRITE_PREFIX, device_id, MQTT_TOPIC_WRITE_RESPONSE_SUFFIX);
    
    cJSON *json = cJSON_CreateObject();
    
    char datetime_str[32];
    get_current_datetime(datetime_str, sizeof(datetime_str));
    cJSON_AddStringToObject(json, "datetime", datetime_str);
    cJSON_AddNumberToObject(json, "timestamp_ms", esp_timer_get_time() / 1000);
    cJSON_AddStringToObject(json, "device_id", device_id);
    cJSON_AddStringToObject(json, "command_type", command_type);
    cJSON_AddBoolToObject(json, "success", success);
    cJSON_AddStringToObject(json, "message", message);
    
    char *json_string = cJSON_Print(json);
    if (json_string == NULL) {
        cJSON_Delete(json);
        ESP_LOGE(TAG, "Errore creazione JSON write response");
        return ESP_FAIL;
    }
    
    int msg_id = esp_mqtt_client_publish(mqtt_client, topic, json_string, 0, 0, 0);
    ESP_LOGI(TAG, "✅ Write response inviato: %s (msg_id=%d)", command_type, msg_id);
    
    free(json_string);
    cJSON_Delete(json);
    return ESP_OK;
}

// 🆕 NUOVO: Invio errore scrittura
esp_err_t send_mqtt_write_error(const char* command_type, const char* error_msg) {
    if (!mqtt_connected || mqtt_client == NULL) {
        ESP_LOGW(TAG, "MQTT non connesso per write error");
        return ESP_FAIL;
    }
    
    char topic[128];
    snprintf(topic, sizeof(topic), "%s%s%s", MQTT_TOPIC_WRITE_PREFIX, device_id, MQTT_TOPIC_WRITE_ERROR_SUFFIX);
    
    cJSON *json = cJSON_CreateObject();
    
    char datetime_str[32];
    get_current_datetime(datetime_str, sizeof(datetime_str));
    cJSON_AddStringToObject(json, "datetime", datetime_str);
    cJSON_AddNumberToObject(json, "timestamp_ms", esp_timer_get_time() / 1000);
    cJSON_AddStringToObject(json, "device_id", device_id);
    cJSON_AddStringToObject(json, "command_type", command_type);
    cJSON_AddStringToObject(json, "error", error_msg);
    
    char *json_string = cJSON_Print(json);
    if (json_string == NULL) {
        cJSON_Delete(json);
        ESP_LOGE(TAG, "Errore creazione JSON write error");
        return ESP_FAIL;
    }
    
    int msg_id = esp_mqtt_client_publish(mqtt_client, topic, json_string, 0, 0, 0);
    ESP_LOGE(TAG, "❌ Write error inviato: %s (msg_id=%d)", error_msg, msg_id);
    
    free(json_string);
    cJSON_Delete(json);
    return ESP_OK;
}

// MQTT Event Handler AGGIORNATO
static void mqtt_event_handler(void *handler_args, esp_event_base_t base, int32_t event_id, void *event_data) {
    esp_mqtt_event_handle_t event = event_data;
    esp_mqtt_client_handle_t client = event->client;
    
    switch ((esp_mqtt_event_id_t)event_id) {
        case MQTT_EVENT_CONNECTED:
            ESP_LOGI(TAG, "MQTT Connesso");
            mqtt_connected = true;
            xEventGroupSetBits(mqtt_event_group, MQTT_CONNECTED_BIT);
            
            // Sottoscrivi al topic di configurazione
            char config_topic[128];
            snprintf(config_topic, sizeof(config_topic), "%s%s%s", 
                     MQTT_TOPIC_CONFIG_PREFIX, device_id, MQTT_TOPIC_REGISTERS_SUFFIX);
            
            int msg_id = esp_mqtt_client_subscribe(client, config_topic, 0);
            ESP_LOGI(TAG, "Sottoscritto a config: %s (msg_id=%d)", config_topic, msg_id);
            
            // 🆕 NUOVO: Sottoscrivi ai topic di scrittura
            char write_register_topic[128];
            snprintf(write_register_topic, sizeof(write_register_topic), "%s%s%s", 
                     MQTT_TOPIC_WRITE_PREFIX, device_id, MQTT_TOPIC_WRITE_REGISTER_SUFFIX);
            
            char write_coil_topic[128];
            snprintf(write_coil_topic, sizeof(write_coil_topic), "%s%s%s", 
                     MQTT_TOPIC_WRITE_PREFIX, device_id, MQTT_TOPIC_WRITE_COIL_SUFFIX);
            
            char write_command_topic[128];
            snprintf(write_command_topic, sizeof(write_command_topic), "%s%s%s", 
                     MQTT_TOPIC_WRITE_PREFIX, device_id, MQTT_TOPIC_WRITE_COMMAND_SUFFIX);
            
            esp_mqtt_client_subscribe(client, write_register_topic, 0);
            esp_mqtt_client_subscribe(client, write_coil_topic, 0);
            esp_mqtt_client_subscribe(client, write_command_topic, 0);
            
            ESP_LOGI(TAG, "🎮 Sottoscritto ai topic di scrittura:");
            ESP_LOGI(TAG, "   📊 Register: %s", write_register_topic);
            ESP_LOGI(TAG, "   🔘 Coil: %s", write_coil_topic);
            ESP_LOGI(TAG, "   🎮 Command: %s", write_command_topic);
            
            if (strstr(device_id, "device_") == device_id) {  // Inizia con "device_"
                send_mqtt_status_enhanced("awaiting_config");
                ESP_LOGI(TAG, "📡 Device temporaneo pronto per configurazione: %s", device_id);
            } else if (device_config.config_loaded) {
                // Se è già configurato, invia status normale
                send_mqtt_status_enhanced("connected");
                ESP_LOGI(TAG, "📡 Device configurato riconnesso: %s", device_id);
            }

            break;
            
        case MQTT_EVENT_DISCONNECTED:
            ESP_LOGI(TAG, "MQTT Disconnesso");
            mqtt_connected = false;
            xEventGroupClearBits(mqtt_event_group, MQTT_CONNECTED_BIT);
            
            if (mqtt_config_receiving) {
                ESP_LOGW(TAG, "Reset ricezione configurazione per disconnessione");
                cleanup_mqtt_config_buffer();
            }
            break;
            
        case MQTT_EVENT_DATA:
            ESP_LOGI(TAG, "Dati MQTT ricevuti");
            ESP_LOGI(TAG, "Topic len: %d, Data len: %d", event->topic_len, event->data_len);
            ESP_LOGI(TAG, "Current offset: %d, Total data: %d", 
                     event->current_data_offset, event->total_data_len);
            
            // Determina il tipo di topic
            char topic_str[256];
            if (event->topic_len > 0) {
                int copy_len = (event->topic_len < sizeof(topic_str) - 1) ? event->topic_len : sizeof(topic_str) - 1;
                strncpy(topic_str, event->topic, copy_len);
                topic_str[copy_len] = '\0';
            } else {
                strcpy(topic_str, "unknown");
            }
            
            ESP_LOGI(TAG, "📡 Topic: %s", topic_str);
            
            // 🆕 NUOVO: Gestisci topic di scrittura
            if (strstr(topic_str, "/write/") != NULL) {
                // È un comando di scrittura
                char data_buffer[1024];
                int copy_len = (event->data_len < sizeof(data_buffer) - 1) ? event->data_len : sizeof(data_buffer) - 1;
                strncpy(data_buffer, event->data, copy_len);
                data_buffer[copy_len] = '\0';
                
                ESP_LOGI(TAG, "🎮 Comando scrittura ricevuto su: %s", topic_str);
                handle_mqtt_write_command(topic_str, data_buffer, event->data_len);
                
            } else {
                // Topic di configurazione (comportamento esistente)
                char expected_config_topic[128];
                snprintf(expected_config_topic, sizeof(expected_config_topic), "%s%s%s", 
                         MQTT_TOPIC_CONFIG_PREFIX, device_id, MQTT_TOPIC_REGISTERS_SUFFIX);
                
                bool is_config_topic = false;
                if (event->topic_len > 0) {
                    if (strncmp(event->topic, expected_config_topic, event->topic_len) == 0) {
                        is_config_topic = true;
                    }
                } else {
                    is_config_topic = mqtt_config_receiving;
                }
                
                if (is_config_topic) {
                    ESP_LOGI(TAG, "📋 Ricevuta configurazione via MQTT (frammentata)");
                    handle_fragmented_mqtt_message(event);
                } else {
                    ESP_LOGW(TAG, "⚠️  Topic sconosciuto o non in ricezione");
                }
            }
            break;
            
        case MQTT_EVENT_ERROR:
            ESP_LOGE(TAG, "Errore MQTT");
            
            if (mqtt_config_receiving) {
                ESP_LOGW(TAG, "Reset ricezione configurazione per errore");
                cleanup_mqtt_config_buffer();
            }
            break;
            
        default:
            break;
    }
}

// Funzioni Data/Ora
void init_sntp(void) {
    ESP_LOGI(TAG, "Inizializzazione SNTP...");
    esp_sntp_setoperatingmode(SNTP_OPMODE_POLL);
    esp_sntp_setservername(0, "pool.ntp.org");
    esp_sntp_setservername(1, "time.nist.gov");
    esp_sntp_init();
    setenv("TZ", "CET-1CEST,M3.5.0/2,M10.5.0/3", 1);
    tzset();
}

void get_current_datetime(char* buffer, size_t buffer_size) {
    time_t now;
    struct tm timeinfo;
    time(&now);
    localtime_r(&now, &timeinfo);
    strftime(buffer, buffer_size, "%Y-%m-%d %H:%M:%S", &timeinfo);
}

// Device ID
void generate_device_id_early(void) {
    nvs_handle_t nvs_handle;
    esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READONLY, &nvs_handle);
    if (err == ESP_OK) {
        size_t length = sizeof(device_id);
        err = nvs_get_str(nvs_handle, NVS_DEVICE_ID, device_id, &length);
        nvs_close(nvs_handle);
        if (err == ESP_OK && strlen(device_id) > 0) {
            ESP_LOGI(TAG, "Device ID caricato da NVS: %s", device_id);
            return;
        }
    }

    uint8_t mac[6];
    err = esp_read_mac(mac, ESP_MAC_WIFI_STA);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Errore lettura MAC base: %s", esp_err_to_name(err));
        snprintf(device_id, sizeof(device_id), "device_err_%lu", esp_random() % 1000);
    } else {
        snprintf(device_id, sizeof(device_id), "device_%02x%02x%02x", mac[3], mac[4], mac[5]);
    }
    ESP_LOGI(TAG, "Device ID temporaneo generato: %s", device_id);
}

void update_device_id(void) {
    char new_device_id[32];
    snprintf(new_device_id, sizeof(new_device_id), "%s_%d", device_config.device, device_config.slave_address);
    
    if (strcmp(device_id, new_device_id) != 0) {
        ESP_LOGI(TAG, "Aggiornamento Device ID: %s -> %s", device_id, new_device_id);
       
        strncpy(device_id, new_device_id, sizeof(device_id) - 1);
        
        nvs_handle_t nvs_handle;
        esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READWRITE, &nvs_handle);
        if (err == ESP_OK) {
            nvs_set_str(nvs_handle, NVS_DEVICE_ID, device_id);
            nvs_commit(nvs_handle);
            nvs_close(nvs_handle);
            ESP_LOGI(TAG, "Device ID salvato in NVS: %s", device_id);
        } else {
            ESP_LOGE(TAG, "Errore salvataggio Device ID in NVS: %s", esp_err_to_name(err));
        }
        
        if (mqtt_connected) {
            esp_mqtt_client_stop(mqtt_client);
            esp_mqtt_client_destroy(mqtt_client);
            esp_mqtt_client_config_t mqtt_cfg = {
                .broker.address.hostname = saved_config.mqtt_broker,
                .broker.address.port = saved_config.mqtt_port,
                .broker.address.transport = MQTT_TRANSPORT_OVER_TCP,
                .credentials.client_id = device_id,
                .network.timeout_ms = 15000,
                .session.keepalive = 60,
                .session.disable_clean_session = false,
                .buffer.size = 40960,
                .buffer.out_size = 8192
            };
            mqtt_client = esp_mqtt_client_init(&mqtt_cfg);
            esp_mqtt_client_register_event(mqtt_client, ESP_EVENT_ANY_ID, mqtt_event_handler, NULL);
            esp_mqtt_client_start(mqtt_client);
            
            // 🆕 AGGIORNATO: Sottoscrivi a tutti i topic necessari
            char new_config_topic[128];
            snprintf(new_config_topic, sizeof(new_config_topic), "%s%s%s", 
                     MQTT_TOPIC_CONFIG_PREFIX, device_id, MQTT_TOPIC_REGISTERS_SUFFIX);
            esp_mqtt_client_subscribe(mqtt_client, new_config_topic, 0);
            
            char write_register_topic[128];
            snprintf(write_register_topic, sizeof(write_register_topic), "%s%s%s", 
                     MQTT_TOPIC_WRITE_PREFIX, device_id, MQTT_TOPIC_WRITE_REGISTER_SUFFIX);
            
            char write_coil_topic[128];
            snprintf(write_coil_topic, sizeof(write_coil_topic), "%s%s%s", 
                     MQTT_TOPIC_WRITE_PREFIX, device_id, MQTT_TOPIC_WRITE_COIL_SUFFIX);
            
            char write_command_topic[128];
            snprintf(write_command_topic, sizeof(write_command_topic), "%s%s%s", 
                     MQTT_TOPIC_WRITE_PREFIX, device_id, MQTT_TOPIC_WRITE_COMMAND_SUFFIX);
            
            esp_mqtt_client_subscribe(mqtt_client, write_register_topic, 0);
            esp_mqtt_client_subscribe(mqtt_client, write_coil_topic, 0);
            esp_mqtt_client_subscribe(mqtt_client, write_command_topic, 0);
        }
    }
}

// Funzione di cleanup buffer MQTT
void cleanup_mqtt_config_buffer() {
    if (mqtt_config_buffer) {
        free(mqtt_config_buffer);
        mqtt_config_buffer = NULL;
    }
    mqtt_config_receiving = false;
    mqtt_config_received = 0;
    mqtt_config_total = 0;
}

// Funzione per gestire messaggi MQTT frammentati con miglioramenti
void handle_fragmented_mqtt_message(esp_mqtt_event_handle_t event) {
    if (event->current_data_offset == 0) {
        ESP_LOGI(TAG, "🚀 Iniziando ricezione configurazione frammentata");
        ESP_LOGI(TAG, "📊 Dimensione totale: %d bytes", event->total_data_len);
        
        if (event->total_data_len > 35000) {
            ESP_LOGE(TAG, "❌ Configurazione troppo grande: %d bytes", event->total_data_len);
            return;
        }
        
        if (mqtt_config_buffer) {
            ESP_LOGW(TAG, "⚠️  Buffer precedente non liberato, cleanup...");
            free(mqtt_config_buffer);
            mqtt_config_buffer = NULL;
        }
        
        mqtt_config_buffer = malloc(event->total_data_len + 1);
        if (!mqtt_config_buffer) {
            ESP_LOGE(TAG, "💥 Errore allocazione buffer per configurazione (%d bytes)", 
                     event->total_data_len);
            ESP_LOGE(TAG, "🔍 Heap libero: %lu bytes", (unsigned long)esp_get_free_heap_size());
            return;
        }
        
        mqtt_config_buffer_size = event->total_data_len;
        mqtt_config_received = 0;
        mqtt_config_total = event->total_data_len;
        mqtt_config_receiving = true;
        
        ESP_LOGI(TAG, "✅ Buffer allocato: %d bytes (heap libero: %lu)", 
                 event->total_data_len, (unsigned long)esp_get_free_heap_size());
    }
    
    if (!mqtt_config_buffer || !mqtt_config_receiving) {
        ESP_LOGE(TAG, "❌ Buffer non allocato per frammento");
        return;
    }
    
    size_t copy_len = event->data_len;
    if (mqtt_config_received + copy_len > mqtt_config_buffer_size) {
        ESP_LOGE(TAG, "💥 Frammento troppo grande: received=%zu + new=%zu > buffer=%zu", 
                 mqtt_config_received, copy_len, mqtt_config_buffer_size);
        cleanup_mqtt_config_buffer();
        return;
    }
    
    memcpy(mqtt_config_buffer + mqtt_config_received, event->data, copy_len);
    mqtt_config_received += copy_len;
    
    float progress = (float)mqtt_config_received / mqtt_config_total * 100.0;
    ESP_LOGI(TAG, "📦 Frammento ricevuto: %zu/%zu bytes (%.1f%%) [heap: %lu]", 
             mqtt_config_received, mqtt_config_total, progress, (unsigned long)esp_get_free_heap_size());
    
    if (mqtt_config_received >= mqtt_config_total) {
        ESP_LOGI(TAG, "🎉 Configurazione completa ricevuta!");
        
        mqtt_config_buffer[mqtt_config_received] = '\0';
        
        ESP_LOGI(TAG, "💾 Processando configurazione completa...");
        handle_mqtt_config_with_save(mqtt_config_buffer, mqtt_config_received);
        
        free(mqtt_config_buffer);
        mqtt_config_buffer = NULL;
        mqtt_config_receiving = false;
        mqtt_config_received = 0;
        mqtt_config_total = 0;
        
        ESP_LOGI(TAG, "🧹 Buffer configurazione liberato (heap: %lu)", (unsigned long)esp_get_free_heap_size());
    }
}

// MQTT Client Init con buffer aumentato
esp_err_t init_mqtt_client() {
    if (device_id[0] == '\0') {
        generate_device_id_early();
    }
    
    esp_mqtt_client_config_t mqtt_cfg = {
        .broker.address.hostname = saved_config.mqtt_broker,
        .broker.address.port = saved_config.mqtt_port,
        .broker.address.transport = MQTT_TRANSPORT_OVER_TCP,
        .credentials.client_id = device_id,
        .network.timeout_ms = 15000,
        .session.keepalive = 60,
        .session.disable_clean_session = false,
        .buffer.size = 40960,             // 40KB buffer ripristinato!
        .buffer.out_size = 8192,          // 8KB out buffer
    };
    
    mqtt_client = esp_mqtt_client_init(&mqtt_cfg);
    if (mqtt_client == NULL) {
        ESP_LOGE(TAG, "Errore inizializzazione client MQTT");
        return ESP_FAIL;
    }
    
    esp_mqtt_client_register_event(mqtt_client, ESP_EVENT_ANY_ID, mqtt_event_handler, NULL);
    
    esp_err_t err = esp_mqtt_client_start(mqtt_client);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Errore avvio client MQTT: %s", esp_err_to_name(err));
        return err;
    }
    
    ESP_LOGI(TAG, "Client MQTT avviato verso %s:%d (buffer: 40KB, write support)", 
             saved_config.mqtt_broker, saved_config.mqtt_port);
    return ESP_OK;
}

// MQTT Status Enhanced
esp_err_t send_mqtt_status_enhanced(const char* status) {
    if (!mqtt_connected || mqtt_client == NULL) {
        ESP_LOGW(TAG, "MQTT non connesso per status");
        return ESP_FAIL;
    }
    
    char topic[128];
    snprintf(topic, sizeof(topic), "%s%s%s", MQTT_TOPIC_DATA_PREFIX, device_id, MQTT_TOPIC_STATUS_SUFFIX);
    
    cJSON *json = cJSON_CreateObject();
    
    char datetime_str[32];
    get_current_datetime(datetime_str, sizeof(datetime_str));
    cJSON_AddStringToObject(json, "datetime", datetime_str);
    cJSON_AddNumberToObject(json, "timestamp_ms", esp_timer_get_time() / 1000);
    cJSON_AddStringToObject(json, "device_id", device_id);
    cJSON_AddStringToObject(json, "status", status);
    cJSON_AddStringToObject(json, "device_type", device_config.device);
    cJSON_AddStringToObject(json, "template_id", device_config.template_id);
    cJSON_AddNumberToObject(json, "uptime_seconds", esp_timer_get_time() / 1000000);
    cJSON_AddNumberToObject(json, "free_heap_bytes", esp_get_free_heap_size());
    cJSON_AddNumberToObject(json, "slave_address", device_config.slave_address);
    cJSON_AddNumberToObject(json, "total_registers", device_config.total_registers);
    cJSON_AddNumberToObject(json, "total_commands", device_config.total_commands);  // 🆕 NUOVO
    cJSON_AddBoolToObject(json, "config_loaded", device_config.config_loaded);
    cJSON_AddBoolToObject(json, "config_from_mqtt", config_loaded_from_mqtt);
    cJSON_AddBoolToObject(json, "wifi_connected", wifi_connected);
    cJSON_AddBoolToObject(json, "mqtt_connected", mqtt_connected);
    cJSON_AddBoolToObject(json, "write_support", true);  // 🆕 NUOVO: Indica supporto scrittura
    
    if (wifi_connected) {
        wifi_ap_record_t ap_info;
        if (esp_wifi_sta_get_ap_info(&ap_info) == ESP_OK) {
            cJSON_AddNumberToObject(json, "wifi_rssi", ap_info.rssi);
            cJSON_AddStringToObject(json, "wifi_ssid", (char*)ap_info.ssid);
        }
    }
    
    char *json_string = cJSON_Print(json);
    if (json_string == NULL) {
        cJSON_Delete(json);
        ESP_LOGE(TAG, "Errore creazione JSON status");
        return ESP_FAIL;
    }
    
    int msg_id = esp_mqtt_client_publish(mqtt_client, topic, json_string, 0, 0, 0);
    ESP_LOGI(TAG, "Status enhanced inviato: %s (msg_id=%d)", status, msg_id);
    
    free(json_string);
    cJSON_Delete(json);
    return ESP_OK;
}

// MQTT Register Data
esp_err_t send_mqtt_register_data(device_register_t* reg, uint16_t raw_value, const char* actual_type) {
    if (!mqtt_connected || mqtt_client == NULL) {
        return ESP_FAIL;
    }
    
    char topic[128];
    snprintf(topic, sizeof(topic), "%s%s%s", MQTT_TOPIC_DATA_PREFIX, device_id, MQTT_TOPIC_REGISTERS_SUFFIX);
    
    cJSON *json = cJSON_CreateObject();
    
    char datetime_str[32];
    get_current_datetime(datetime_str, sizeof(datetime_str));
    cJSON_AddStringToObject(json, "datetime", datetime_str);
    cJSON_AddNumberToObject(json, "timestamp_ms", esp_timer_get_time() / 1000);
    cJSON_AddStringToObject(json, "device_id", device_id);
    cJSON_AddNumberToObject(json, "slave_address", device_config.slave_address);
    
    cJSON *registers_array = cJSON_CreateArray();
    cJSON *register_obj = cJSON_CreateObject();
    
    // ✅ FIX: Aggiungi campo type esplicito per distinguere Register da Coil
    cJSON_AddNumberToObject(register_obj, "address", reg->address);
    cJSON_AddStringToObject(register_obj, "name", reg->name);
    cJSON_AddNumberToObject(register_obj, "value", raw_value);
    cJSON_AddStringToObject(register_obj, "type", actual_type);  // ✅ NUOVO: Tipo esplicito
    cJSON_AddStringToObject(register_obj, "register_type", reg->register_type);  // Tipo dal config

    // 🆕 NUOVO: Aggiungi chiave composita per risolvere conflitti address
    char composite_key[32];
    snprintf(composite_key, sizeof(composite_key), "%d_%s", reg->address, actual_type);
    cJSON_AddStringToObject(register_obj, "composite_key", composite_key);
    
    cJSON_AddItemToArray(registers_array, register_obj);
    cJSON_AddItemToObject(json, "registers", registers_array);
    
    char *json_string = cJSON_Print(json);
    if (json_string == NULL) {
        cJSON_Delete(json);
        return ESP_FAIL;
    }
    
    int msg_id = esp_mqtt_client_publish(mqtt_client, topic, json_string, 0, 0, 0);
    printf("   -> MQTT %s (msg_id=%d)\n", actual_type, msg_id);
    
    free(json_string);
    cJSON_Delete(json);
    return ESP_OK;
}

// Handle MQTT Config with Save
void handle_mqtt_config_with_save(const char* data, int data_len) {
    ESP_LOGI(TAG, "🔄 Processing configurazione MQTT (%d bytes)...", data_len);
    
    print_memory_info("Pre-Save");
    
    esp_err_t save_result = save_device_config_chunked(data, data_len);
    if (save_result != ESP_OK) {
        ESP_LOGW(TAG, "⚠️  Fallback: salvataggio chunked fallito, uso solo memoria");
    }
    
    handle_mqtt_config(data, data_len);
    
    if (device_config.config_loaded) {
        ESP_LOGI(TAG, "✅ Configurazione processata con successo:");
        ESP_LOGI(TAG, "   📋 Device: %s v%s", device_config.device, device_config.version);
        ESP_LOGI(TAG, "   🏷️  Slave Address: %d", device_config.slave_address);
        ESP_LOGI(TAG, "   📊 Holding Registers: %d", device_config.holding_count);
        ESP_LOGI(TAG, "   🔘 Coils: %d", device_config.coils_count);
        ESP_LOGI(TAG, "   🎮 Commands: %d", device_config.commands_count);
        ESP_LOGI(TAG, "   📈 Total Registers: %d", device_config.total_registers);
        ESP_LOGI(TAG, "   💾 Salvato in NVS: %s", (save_result == ESP_OK) ? "✅" : "❌");
        
        post_config_diagnostics();
    }
}

// Handle MQTT Config (parsing originale) - AGGIORNATO CON COMMANDS
void handle_mqtt_config(const char* data, int data_len) {
    ESP_LOGI(TAG, "Parsing configurazione MQTT completa (%d bytes)...", data_len);
    
    memset(&device_config, 0, sizeof(device_config_t));
    
    cJSON *json = cJSON_Parse(data);
    if (json == NULL) {
        ESP_LOGE(TAG, "Errore parsing JSON configurazione");
        return;
    }
    
    // Parse metadata
    cJSON *metadata = cJSON_GetObjectItem(json, "metadata");
    if (metadata) {
        cJSON *version = cJSON_GetObjectItem(metadata, "version");
        if (version && cJSON_IsString(version)) {
            strncpy(device_config.version, version->valuestring, sizeof(device_config.version) - 1);
        }
        
        cJSON *device = cJSON_GetObjectItem(metadata, "device");
        if (device && cJSON_IsString(device)) {
            strncpy(device_config.device, device->valuestring, sizeof(device_config.device) - 1);
        }
        
        cJSON *slave_address = cJSON_GetObjectItem(metadata, "slave_address");
        if (slave_address && cJSON_IsNumber(slave_address)) {
            device_config.slave_address = slave_address->valueint;
        }
        
        cJSON *baud_rate = cJSON_GetObjectItem(metadata, "baud_rate");
        if (baud_rate && cJSON_IsNumber(baud_rate)) {
            device_config.baud_rate = baud_rate->valueint;
            ESP_LOGI(TAG, "📡 Baud rate configurato: %lu", device_config.baud_rate);
        } else {
            device_config.baud_rate = 19200; // Default fallback
            ESP_LOGW(TAG, "⚠️  Baud rate non trovato, uso default: 19200");
        }
        
        cJSON *template_id = cJSON_GetObjectItem(metadata, "template_id");
        if (template_id && cJSON_IsString(template_id)) {
            strncpy(device_config.template_id, template_id->valuestring, sizeof(device_config.template_id) - 1);
        }
        
        cJSON *total_registers = cJSON_GetObjectItem(metadata, "total_registers");
        if (total_registers && cJSON_IsNumber(total_registers)) {
            device_config.total_registers = total_registers->valueint;
        }
        
        // 🆕 NUOVO: Parse total_commands
        cJSON *total_commands = cJSON_GetObjectItem(metadata, "total_commands");
        if (total_commands && cJSON_IsNumber(total_commands)) {
            device_config.total_commands = total_commands->valueint;
        }
    }
    
    // Parse holding registers SEMPLIFICATO
    cJSON *holding_registers = cJSON_GetObjectItem(json, "holding_registers");
    if (holding_registers && cJSON_IsArray(holding_registers)) {
        cJSON *reg_item = NULL;
        int index = 0;
        
        cJSON_ArrayForEach(reg_item, holding_registers) {
            if (index >= MAX_REGISTERS) break;
            
            device_register_t *reg = &device_config.holding_registers[index];
            memset(reg, 0, sizeof(device_register_t));
            
            // SOLO I CAMPI ESSENZIALI
            cJSON *address = cJSON_GetObjectItem(reg_item, "address");
            if (address && cJSON_IsNumber(address)) {
                reg->address = address->valueint;
            }
            
            cJSON *name = cJSON_GetObjectItem(reg_item, "name");
            if (name && cJSON_IsString(name)) {
                strncpy(reg->name, name->valuestring, MAX_NAME_LEN - 1);
            }
            
            cJSON *register_type = cJSON_GetObjectItem(reg_item, "register_type");
            if (register_type && cJSON_IsString(register_type)) {
                strncpy(reg->register_type, register_type->valuestring, 11);
            } else {
                strncpy(reg->register_type, "Register", 11);
            }
            
            index++;
        }
        
        device_config.holding_count = index;
    }
    
    // Parse coils SEMPLIFICATO
    cJSON *coils = cJSON_GetObjectItem(json, "coils");
    if (coils && cJSON_IsArray(coils)) {
        cJSON *coil_item = NULL;
        int index = 0;
        
        cJSON_ArrayForEach(coil_item, coils) {
            if (index >= MAX_REGISTERS) break;
            
            device_register_t *coil = &device_config.coils[index];
            memset(coil, 0, sizeof(device_register_t));
            
            // SOLO I CAMPI ESSENZIALI
            cJSON *address = cJSON_GetObjectItem(coil_item, "address");
            if (address && cJSON_IsNumber(address)) {
                coil->address = address->valueint;
            }
            
            cJSON *name = cJSON_GetObjectItem(coil_item, "name");
            if (name && cJSON_IsString(name)) {
                strncpy(coil->name, name->valuestring, MAX_NAME_LEN - 1);
            }
            
            cJSON *register_type = cJSON_GetObjectItem(coil_item, "register_type");
            if (register_type && cJSON_IsString(register_type)) {
                strncpy(coil->register_type, register_type->valuestring, 11);
            } else {
                strncpy(coil->register_type, "Coils", 11);
            }
            
            index++;
        }
        
        device_config.coils_count = index;
    }
    
    // 🆕 NUOVO: Parse commands SEMPLIFICATO
    cJSON *commands = cJSON_GetObjectItem(json, "commands");
    if (commands && cJSON_IsArray(commands)) {
        cJSON *cmd_item = NULL;
        int index = 0;
        
        cJSON_ArrayForEach(cmd_item, commands) {
            if (index >= MAX_COMMANDS) break;
            
            device_command_t *cmd = &device_config.commands[index];
            memset(cmd, 0, sizeof(device_command_t));
            
            // SOLO I CAMPI ESSENZIALI PER COMMANDS
            cJSON *address = cJSON_GetObjectItem(cmd_item, "address");
            if (address && cJSON_IsNumber(address)) {
                cmd->address = address->valueint;
            }
            
            cJSON *name = cJSON_GetObjectItem(cmd_item, "name");
            if (name && cJSON_IsString(name)) {
                strncpy(cmd->name, name->valuestring, MAX_NAME_LEN - 1);
            }
            
            cJSON *register_type = cJSON_GetObjectItem(cmd_item, "register_type");
            if (register_type && cJSON_IsString(register_type)) {
                strncpy(cmd->register_type, register_type->valuestring, 11);
            } else {
                strncpy(cmd->register_type, "Coils", 11);
            }
            
            cJSON *value_command = cJSON_GetObjectItem(cmd_item, "value_command");
            if (value_command && cJSON_IsNumber(value_command)) {
                cmd->value_command = value_command->valueint;
            }
            
            cJSON *alias = cJSON_GetObjectItem(cmd_item, "alias");
            if (alias && cJSON_IsString(alias)) {
                strncpy(cmd->alias, alias->valuestring, MAX_NAME_LEN - 1);
            }
            
            index++;
        }
        
        device_config.commands_count = index;
    }
    
    device_config.config_loaded = true;
    config_loaded_from_mqtt = true;
    
    ESP_LOGI(TAG, "Configurazione caricata da MQTT:");
    ESP_LOGI(TAG, "Device: %s v%s", device_config.device, device_config.version);
    ESP_LOGI(TAG, "Slave Address: %d", device_config.slave_address);
    ESP_LOGI(TAG, "🔧 Baud Rate: %lu", device_config.baud_rate);
    ESP_LOGI(TAG, "Holding Registers: %d", device_config.holding_count);
    ESP_LOGI(TAG, "Coils: %d", device_config.coils_count);
    ESP_LOGI(TAG, "🎮 Commands: %d", device_config.commands_count);
    ESP_LOGI(TAG, "Total Registers: %d", device_config.total_registers);
    
    ESP_LOGI(TAG, "🔄 Riconfigurando UART con nuovi parametri...");
    init_uart(device_config.baud_rate);
    update_device_id();
    xEventGroupSetBits(mqtt_event_group, CONFIG_RECEIVED_BIT);
    
    cJSON_Delete(json);
}

// Wait for MQTT Config
esp_err_t wait_for_mqtt_config() {
    if (device_config.config_loaded) {
        ESP_LOGI(TAG, "Configurazione già caricata");
        return ESP_OK;
    }
    
    ESP_LOGI(TAG, "⏳ Aspettando configurazione da MQTT...");
    ESP_LOGI(TAG, "📡 Topic: %s%s%s", MQTT_TOPIC_CONFIG_PREFIX, device_id, MQTT_TOPIC_REGISTERS_SUFFIX);
    ESP_LOGI(TAG, "💡 Invia la configurazione JSON dal PC/server al topic sopra");
    
    EventBits_t bits = xEventGroupWaitBits(mqtt_event_group,
                                           CONFIG_RECEIVED_BIT,
                                           pdFALSE, pdFALSE,
                                           pdMS_TO_TICKS(120000));
    
    if (bits & CONFIG_RECEIVED_BIT) {
        ESP_LOGI(TAG, "✅ Configurazione ricevuta da MQTT!");
        return ESP_OK;
    }
    
    ESP_LOGE(TAG, "❌ Timeout: configurazione non ricevuta da MQTT");
    ESP_LOGE(TAG, "💡 Verifica che il server stia inviando la configurazione");
    ESP_LOGE(TAG, "🔄 Riavvia ESP32 dopo aver configurato il server MQTT");
    return ESP_FAIL;
}

// NVS Functions
esp_err_t load_wifi_config(void) {
    nvs_handle_t nvs_handle;
    esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READWRITE, &nvs_handle);
    if (err != ESP_OK) {
        return err;
    }
    
    size_t required_size = sizeof(saved_config.wifi_ssid);
    nvs_get_str(nvs_handle, NVS_WIFI_SSID, saved_config.wifi_ssid, &required_size);
    
    required_size = sizeof(saved_config.wifi_pass);
    nvs_get_str(nvs_handle, NVS_WIFI_PASS, saved_config.wifi_pass, &required_size);
    
    required_size = sizeof(saved_config.mqtt_broker);
    nvs_get_str(nvs_handle, NVS_MQTT_BROKER, saved_config.mqtt_broker, &required_size);
    if (strlen(saved_config.mqtt_broker) == 0) {
        strcpy(saved_config.mqtt_broker, DEFAULT_MQTT_BROKER);
    }
    
    uint16_t mqtt_port = 0;
    nvs_get_u16(nvs_handle, NVS_MQTT_PORT, &mqtt_port);
    saved_config.mqtt_port = (mqtt_port == 0) ? DEFAULT_MQTT_PORT : mqtt_port;
    
    uint8_t config_done = 0;
    nvs_get_u8(nvs_handle, NVS_CONFIG_DONE, &config_done);
    saved_config.config_done = (config_done == 1);
    
    nvs_close(nvs_handle);
    return ESP_OK;
}

esp_err_t save_wifi_config(void) {
    nvs_handle_t nvs_handle;
    esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READWRITE, &nvs_handle);
    if (err != ESP_OK) return err;
    
    nvs_set_str(nvs_handle, NVS_WIFI_SSID, saved_config.wifi_ssid);
    nvs_set_str(nvs_handle, NVS_WIFI_PASS, saved_config.wifi_pass);
    nvs_set_str(nvs_handle, NVS_MQTT_BROKER, saved_config.mqtt_broker);
    nvs_set_u16(nvs_handle, NVS_MQTT_PORT, saved_config.mqtt_port);
    nvs_set_u8(nvs_handle, NVS_CONFIG_DONE, saved_config.config_done ? 1 : 0);
    
    err = nvs_commit(nvs_handle);
    nvs_close(nvs_handle);
    return err;
}

esp_err_t clear_wifi_config(void) {
    nvs_handle_t nvs_handle;
    esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READWRITE, &nvs_handle);
    if (err != ESP_OK) return err;
    
    nvs_erase_all(nvs_handle);
    err = nvs_commit(nvs_handle);
    nvs_close(nvs_handle);
    return err;
}

// Load device config with chunked storage fallback
esp_err_t load_device_config(void) {
    esp_err_t err = load_device_config_chunked();
    if (err == ESP_OK) {
        return ESP_OK;
    }
    
    ESP_LOGW(TAG, "Chunked storage fallito, provo metodo tradizionale");
    
    nvs_handle_t nvs_handle;
    err = nvs_open(NVS_NAMESPACE, NVS_READONLY, &nvs_handle);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "NVS non inizializzato o namespace non trovato: %s", esp_err_to_name(err));
        return err;
    }

    size_t required_size = 0;
    err = nvs_get_str(nvs_handle, NVS_DEVICE_CONFIG, NULL, &required_size);
    if (err != ESP_OK) {
        nvs_close(nvs_handle);
        ESP_LOGW(TAG, "Nessuna configurazione trovata in NVS: %s", esp_err_to_name(err));
        return err;
    }

    if (required_size > 8192) {
        nvs_close(nvs_handle);
        ESP_LOGE(TAG, "Configurazione troppo grande per metodo tradizionale: %zu bytes", required_size);
        return ESP_ERR_NO_MEM;
    }

    char* json_buf = malloc(required_size);
    if (!json_buf) {
        nvs_close(nvs_handle);
        ESP_LOGE(TAG, "Errore allocazione buffer per configurazione NVS");
        return ESP_ERR_NO_MEM;
    }

    err = nvs_get_str(nvs_handle, NVS_DEVICE_CONFIG, json_buf, &required_size);
    nvs_close(nvs_handle);
    if (err != ESP_OK) {
        free(json_buf);
        ESP_LOGE(TAG, "Errore lettura configurazione da NVS: %s", esp_err_to_name(err));
        return err;
    }

    ESP_LOGI(TAG, "Caricamento configurazione da NVS (%zu bytes)", required_size - 1);
    handle_mqtt_config(json_buf, required_size - 1);
    free(json_buf);

    if (device_config.config_loaded) {
        ESP_LOGI(TAG, "Configurazione caricata da NVS con successo");
        config_loaded_from_mqtt = false;
        update_device_id();
        return ESP_OK;
    } else {
        ESP_LOGE(TAG, "Errore parsing configurazione da NVS");
        return ESP_FAIL;
    }
}

// SPIFFS Functions
char* load_html_file(const char* filename) {
    FILE* f = fopen(filename, "r");
    if (!f) {
        ESP_LOGE(TAG, "Cannot open %s", filename);
        return NULL;
    }
    
    fseek(f, 0, SEEK_END);
    long fsize = ftell(f);
    fseek(f, 0, SEEK_SET);
    
    char* json = malloc(fsize + 1);
    if (!json) {
        ESP_LOGE(TAG, "Cannot allocate memory per %s", filename);
        fclose(f);
        return NULL;
    }
    
    fread(json, 1, fsize, f);
    fclose(f);
    json[fsize] = '\0';
    
    ESP_LOGI(TAG, "Loaded %s (%ld bytes)", filename, fsize);
    return json;
}

esp_err_t init_spiffs(void) {
    esp_vfs_spiffs_conf_t conf = {
        .base_path = "/spiffs",
        .partition_label = NULL,
        .max_files = 5,
        .format_if_mount_failed = true
    };
    
    esp_err_t ret = esp_vfs_spiffs_register(&conf);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Errore inizializzazione SPIFFS: %s", esp_err_to_name(ret));
        return ret;
    }
    
    size_t total = 0, used = 0;
    ret = esp_spiffs_info(NULL, &total, &used);
    if (ret == ESP_OK) {
        printf("SPIFFS: %d KB totale, %d KB usato\n", total / 1024, used / 1024);
    }
    return ESP_OK;
}

// Web Server Handlers
static esp_err_t config_get_handler(httpd_req_t *req) {
    char* html_content = load_html_file("/spiffs/config.html");
    if (!html_content) {
        const char* error_msg = "<html><body><h1>Errore: Impossibile caricare pagina configurazione</h1></body></html>";
        httpd_resp_set_type(req, "text/html");
        httpd_resp_send(req, error_msg, HTTPD_RESP_USE_STRLEN);
        return ESP_FAIL;
    }
    
    httpd_resp_set_type(req, "text/html");
    esp_err_t result = httpd_resp_send(req, html_content, HTTPD_RESP_USE_STRLEN);
    free(html_content);
    return result;
}

static esp_err_t save_config_handler(httpd_req_t *req) {
    char content[1024];
    size_t recv_size = req->content_len < sizeof(content) ? req->content_len : sizeof(content) - 1;
    int ret = httpd_req_recv(req, content, recv_size);
    if (ret <= 0) {
        const char* error_resp = "{\"success\":false,\"error\":\"Nessun dato ricevuto\"}";
        httpd_resp_set_type(req, "application/json");
        httpd_resp_send(req, error_resp, HTTPD_RESP_USE_STRLEN);
        return ESP_FAIL;
    }
    content[ret] = '\0';
    
    cJSON *json = cJSON_Parse(content);
    if (!json) {
        const char* error_resp = "{\"success\":false,\"error\":\"JSON non valido\"}";
        httpd_resp_set_type(req, "application/json");
        httpd_resp_send(req, error_resp, HTTPD_RESP_USE_STRLEN);
        return ESP_FAIL;
    }
    
    cJSON *ssid = cJSON_GetObjectItem(json, "ssid");
    cJSON *password = cJSON_GetObjectItem(json, "password");
    cJSON *mqtt_broker = cJSON_GetObjectItem(json, "mqtt_broker");
    cJSON *mqtt_port = cJSON_GetObjectItem(json, "mqtt_port");
    
    if (!ssid || !mqtt_broker) {
        const char* error_resp = "{\"success\":false,\"error\":\"Campi richiesti mancanti\"}";
        httpd_resp_set_type(req, "application/json");
        httpd_resp_send(req, error_resp, HTTPD_RESP_USE_STRLEN);
        cJSON_Delete(json);
        return ESP_FAIL;
    }
    
    strncpy(saved_config.wifi_ssid, ssid->valuestring, sizeof(saved_config.wifi_ssid) - 1);
    strncpy(saved_config.wifi_pass, password ? password->valuestring : "", sizeof(saved_config.wifi_pass));
    strncpy(saved_config.mqtt_broker, mqtt_broker->valuestring, sizeof(saved_config.mqtt_broker) - 1);
    saved_config.mqtt_port = mqtt_port ? mqtt_port->valueint : DEFAULT_MQTT_PORT;
    saved_config.config_done = true;
    
    esp_err_t err = save_wifi_config();
    cJSON_Delete(json);
    
    if (err == ESP_OK) {
        const char* success_resp = "{\"success\":true,\"message\":\"Configurazione salvata\"}";
        httpd_resp_set_type(req, "application/json");
        httpd_resp_send(req, success_resp, HTTPD_RESP_USE_STRLEN);
        xEventGroupSetBits(wifi_event_group, CONFIG_DONE_BIT);
        return ESP_OK;
    }
    
    const char* error_resp = "{\"success\":false,\"error\":\"Errore salvataggio\"}";
    httpd_resp_set_type(req, "application/json");
    httpd_resp_send(req, error_resp, HTTPD_RESP_USE_STRLEN);
    return err;
}

static esp_err_t reset_handler(httpd_req_t *req) {
    if (req->method == HTTP_GET) {
        char* html_content = load_html_file("/spiffs/reset.html");
        if (!html_content) {
            const char* error_msg = "<html><body><h1>Errore caricamento pagina di reset</h1></body></html>";
            httpd_resp_set_type(req, "text/html");
            httpd_resp_send(req, error_msg, HTTPD_RESP_USE_STRLEN);
            return ESP_FAIL;
        }
        
        httpd_resp_set_type(req, "text/html");
        esp_err_t result = httpd_resp_send(req, html_content, HTTPD_RESP_USE_STRLEN);
        free(html_content);
        return result;
    } else if (req->method == HTTP_POST) {
        char content[64];
        int ret = httpd_req_recv(req, content, sizeof(content) - 1);
        if (ret <= 0) return ESP_FAIL;
        content[ret] = '\0';

        char password[16];
        if (httpd_query_key_value(content, "password", password, sizeof(password)) != ESP_OK) {
            httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Password mancante");
            return ESP_FAIL;
        }

        if (strcmp(password, RESET_PASSWORD) == 0) {
            clear_wifi_config();
            const char* success_msg = "<html><body><h1>Configurazione resettata. Riavvio...</h1></body></html>";
            httpd_resp_set_type(req, "text/html");
            httpd_resp_send(req, success_msg, HTTPD_RESP_USE_STRLEN);
            vTaskDelay(pdMS_TO_TICKS(2000));
            cleanup_mqtt_config_buffer();
            esp_restart();
            return ESP_OK;
        }
        
        httpd_resp_send_err(req, HTTPD_401_UNAUTHORIZED, "Password errata");
        return ESP_FAIL;
    }
    return ESP_OK;
}

// WiFi Functions
static void wifi_event_handler(void* arg, esp_event_base_t event_base, int32_t event_id, void* event_data) {
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        wifi_connected = false;
        ESP_LOGI(TAG, "WiFi disconnesso, ritentativo...");
        esp_wifi_connect();
    } else if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t* event = (ip_event_got_ip_t*) event_data;
        ESP_LOGI(TAG, "WiFi connesso! IP: " IPSTR, IP2STR(&event->ip_info.ip));
        wifi_connected = true;
        current_state = STATE_RUNNING;
        xEventGroupSetBits(wifi_event_group, WIFI_CONNECTED_BIT);
    }
}

esp_err_t start_wifi_sta(void) {
    ESP_LOGI(TAG, "Connessione WiFi: %s", saved_config.wifi_ssid);
    current_state = STATE_CONNECTING;
    
    wifi_config_t sta_wifi_config = {0};
    strncpy((char*)sta_wifi_config.sta.ssid, saved_config.wifi_ssid, sizeof(sta_wifi_config.sta.ssid));
    strncpy((char*)sta_wifi_config.sta.password, saved_config.wifi_pass, sizeof(sta_wifi_config.sta.password));
    
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &sta_wifi_config));
    ESP_ERROR_CHECK(esp_wifi_start());
    return ESP_OK;
}

void wifi_init(void) {
    wifi_event_group = xEventGroupCreate();
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_ap();
    esp_netif_create_default_wifi_sta();
    
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    
    esp_event_handler_instance_t instance_any_id;
    esp_event_handler_instance_t instance_got_ip;
    ESP_ERROR_CHECK(esp_event_handler_instance_register(WIFI_EVENT,
                                                        ESP_EVENT_ANY_ID,
                                                        &wifi_event_handler,
                                                        NULL,
                                                        &instance_any_id));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(IP_EVENT,
                                                        IP_EVENT_STA_GOT_IP,
                                                        &wifi_event_handler,
                                                        NULL,
                                                        &instance_got_ip));
}

// Modbus Functions
uint16_t modbus_crc16(const uint8_t *data, uint16_t length) {
    uint16_t crc = 0xFFFF;
    for (uint16_t i = 0; i < length; i++) {
        crc ^= (uint16_t)data[i];
        for (uint8_t j = 0; j < 8; j++) {
            if (crc & 0x0001) {
                crc >>= 1;
                crc ^= 0xA001;
            } else {
                crc >>= 1;
            }
        }
    }
    return crc;
}

void init_uart(uint32_t baud_rate) {
    uart_config_t uart_config = {
        .baud_rate = baud_rate,          // <-- DINAMICO
        .data_bits = UART_DATA_8_BITS,
        .parity    = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE
    };
    
    // Prima di riconfigurare, ferma il driver esistente se attivo
    uart_driver_delete(UART_PORT_NUM);
    
    esp_err_t err = uart_driver_install(UART_PORT_NUM, 1024, 0, 0, NULL, 0);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Errore installazione driver UART: %s", esp_err_to_name(err));
        return;
    }
    
    err = uart_param_config(UART_PORT_NUM, &uart_config);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Errore configurazione parametri UART: %s", esp_err_to_name(err));
        return;
    }
    
    err = uart_set_pin(UART_PORT_NUM, TXD_PIN, RXD_PIN, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Errore configurazione pin UART: %s", esp_err_to_name(err));
        return;
    }
    
    ESP_LOGI(TAG, "✅ UART configurato: %lu baud, slave address: %d", 
             baud_rate, device_config.slave_address);
}

void init_gpio(void) {
    gpio_config_t io_conf = {
        .pin_bit_mask = (1ULL << DE_RE_PIN),
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = 0,
        .pull_down_en = 0,
        .intr_type = GPIO_INTR_DISABLE
    };
    gpio_config(&io_conf);
    gpio_set_level(DE_RE_PIN, 0);
}

bool read_modbus_register(uint16_t reg_addr, uint16_t *value, bool is_coil) {
    uint8_t request[8];
    request[0] = device_config.slave_address;
    request[1] = is_coil ? 0x01 : 0x03;
    request[2] = (reg_addr >> 8) & 0xFF;
    request[3] = reg_addr & 0xFF;
    request[4] = 0x00;
    request[5] = 0x01;
    
    uint16_t crc = modbus_crc16(request, 6);
    request[6] = crc & 0xFF;
    request[7] = (crc >> 8) & 0xFF;
    
    uart_flush_input(UART_PORT_NUM);
    gpio_set_level(DE_RE_PIN, 1);
    vTaskDelay(pdMS_TO_TICKS(10));
    uart_write_bytes(UART_PORT_NUM, (const char *)request, sizeof(request));
    uart_wait_tx_done(UART_PORT_NUM, pdMS_TO_TICKS(100));
    gpio_set_level(DE_RE_PIN, 0);
    vTaskDelay(pdMS_TO_TICKS(50));
    
    uint8_t response[16];
    int len = uart_read_bytes(UART_PORT_NUM, response, sizeof(response), pdMS_TO_TICKS(500));
    
    if (len >= 5) {
        if (response[0] == device_config.slave_address && response[1] == request[1]) {
            uint16_t received_crc, calculated_crc;
            if (is_coil) {
                received_crc = response[4] | (response[5] << 8);
                calculated_crc = modbus_crc16(response, 4);
                *value = response[3] & 0x01;
            } else {
                if (len >= 7) {
                    received_crc = response[5] | (response[6] << 8);
                    calculated_crc = modbus_crc16(response, 5);
                    *value = (response[3] << 8) | response[4];
                } else {
                    return false;
                }
            }
            if (received_crc == calculated_crc) {
                return true;
            }
        }
    }
    return false;
}

void print_register_value(device_register_t *reg, uint16_t raw_value, const char* actual_type) {
    printf("%s (addr=%d, type=%s) = %d\n", reg->name, reg->address, actual_type, raw_value);
    
    if (mqtt_connected && saved_config.config_done) {
        send_mqtt_register_data(reg, raw_value, actual_type);
    }
    
    reg->current_value = raw_value;
    reg->last_read_time = esp_timer_get_time() / 1000;
}

void read_all_registers(void) {
    printf("\n==== Lettura Registri (Max: %d)\n", device_config.total_registers);
    
    uint16_t read_count = 0;
    
    // ✅ FIX: Leggi TUTTI gli holding registers con tipo esplicito "Register"
    for (int i = 0; i < device_config.holding_count && read_count < device_config.total_registers; i++) {
        if(i % 10 == 0){
            send_mqtt_status_enhanced("online");
            print_memory_info("Cycle");
        }

        device_register_t *reg = &device_config.holding_registers[i]; 
        
        uint16_t value = 0;
        if (read_modbus_register(reg->address, &value, false)) {  // false = Register
            print_register_value(reg, value, "Register");  // ✅ NUOVO
            read_count++;
        } else {
            printf("Errore lettura %s (%d) Register\n", reg->name, reg->address);
        }
        vTaskDelay(pdMS_TO_TICKS(100));
        
        if (read_count >= device_config.total_registers) break;
    }
    
    // ✅ FIX: Leggi TUTTI i coils con tipo esplicito "Coil"
    for (int i = 0; i < device_config.coils_count && read_count < device_config.total_registers; i++) {
        if(i % 10 == 0){
            send_mqtt_status_enhanced("online");
            print_memory_info("Cycle");
        }
        device_register_t *coil = &device_config.coils[i];
        
        uint16_t value = 0;
        if (read_modbus_register(coil->address, &value, true)) {  // true = Coil
            print_register_value(coil, value, "Coil");  // ✅ NUOVO
            read_count++;
        } else {
            printf("Errore lettura %s (%d) Coil\n", coil->name, coil->address);
        }
        vTaskDelay(pdMS_TO_TICKS(100));
        
        if (read_count >= device_config.total_registers) break;
    }
    
    printf("Totale registri letti: %d/%d\n", read_count, device_config.total_registers);
}

// Configuration Mode
void config_task(void *pvParameters) {
    ESP_LOGI(TAG, "Task configurazione avviato - timeout 5 minuti\n");
    
    EventBits_t bits = xEventGroupWaitBits(wifi_event_group,
                                           CONFIG_DONE_BIT,
                                           pdFALSE, pdFALSE,
                                           pdMS_TO_TICKS(CONFIG_TIMEOUT_MS));
    
    if (bits & CONFIG_DONE_BIT) {
        ESP_LOGI(TAG, "Configurazione completata!");
        vTaskDelay(pdMS_TO_TICKS(3000));
        cleanup_mqtt_config_buffer();
        esp_restart();
    } else {
        ESP_LOGW(TAG, "Timeout configurazione\n");
        current_state = STATE_ERROR;
    }
    vTaskDelete(NULL);
}

void generate_dynamic_ap_ssid(char* ap_ssid, size_t buffer_size) {
    uint8_t mac[6];
    esp_err_t err = esp_read_mac(mac, ESP_MAC_WIFI_STA);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Errore lettura MAC per SSID: %s", esp_err_to_name(err));
        snprintf(ap_ssid, buffer_size, "DEVICE-CONFIG");  // Fallback
    } else {
        snprintf(ap_ssid, buffer_size, "DEVICE-%02x%02x%02x", mac[3], mac[4], mac[5]);
    }
    ESP_LOGI(TAG, "SSID AP dinamico generato: %s", ap_ssid);
}

void start_config_mode(void) {
    ESP_LOGI(TAG, "Avvio modalità configurazione...");
    config_mode = true;
    current_state = STATE_CONFIG_MODE;

    generate_dynamic_ap_ssid(dynamic_ap_ssid, sizeof(dynamic_ap_ssid));
    
    wifi_config_t ap_wifi_config = {0};
    strcpy((char*)ap_wifi_config.ap.ssid, dynamic_ap_ssid);
    ap_wifi_config.ap.ssid_len = strlen(dynamic_ap_ssid);
    ap_wifi_config.ap.channel = AP_CHANNEL;
    strcpy((char*)ap_wifi_config.ap.password, AP_PASS);
    ap_wifi_config.ap.max_connection = AP_MAX_STA_CONN;
    ap_wifi_config.ap.authmode = WIFI_AUTH_WPA_WPA2_PSK;
    
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_AP));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_AP, &ap_wifi_config));
    ESP_ERROR_CHECK(esp_wifi_start());
    
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.server_port = 80;
    
    if (httpd_start(&config_server, &config) == ESP_OK) {
        httpd_uri_t config_uri = {
            .uri = "/config",
            .method = HTTP_GET,
            .handler = config_get_handler,
            .user_ctx = NULL
        };
        httpd_register_uri_handler(config_server, &config_uri);
        
        httpd_uri_t save_uri = {
            .uri = "/save_config",
            .method = HTTP_POST,
            .handler = save_config_handler,
            .user_ctx = NULL
        };
        httpd_register_uri_handler(config_server, &save_uri);
        
        httpd_uri_t reset_get_uri = {
            .uri = "/reset",
            .method = HTTP_GET,
            .handler = reset_handler,
            .user_ctx = NULL
        };
        httpd_register_uri_handler(config_server, &reset_get_uri);
        
        httpd_uri_t reset_post_uri = {
            .uri = "/reset",
            .method = HTTP_POST,
            .handler = reset_handler,
            .user_ctx = NULL
        };
        httpd_register_uri_handler(config_server, &reset_post_uri);
        
        ESP_LOGI(TAG, "Web server avviato su http://192.168.4.1\n");
        ESP_LOGI(TAG, "🆔 SSID AP: %s (password: %s)", dynamic_ap_ssid, AP_PASS);
    }
}

void start_running_server(void) {
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.server_port = 80;
    
    if (httpd_start(&config_server, &config) == ESP_OK) {
        httpd_uri_t reset_get_uri = {
            .uri = "/reset",
            .method = HTTP_GET,
            .handler = reset_handler,
            .user_ctx = NULL
        };
        httpd_register_uri_handler(config_server, &reset_get_uri);
        
        httpd_uri_t reset_post_uri = {
            .uri = "/reset",
            .method = HTTP_POST,
            .handler = reset_handler,
            .user_ctx = NULL
        };
        httpd_register_uri_handler(config_server, &reset_post_uri);
        
        ESP_LOGI(TAG, "Web server RUNNING avviato\n");
    }
}

// Main Function
void app_main(void) {
    printf("DEVICE WiFi MQTT Bridge v5.0 - Complete Modbus Write Support\n");
    printf("==============================================================\n");
    
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_LOGW(TAG, "Errore NVS, inizializzo...");
        nvs_flash_erase();
        err = nvs_flash_init();
    }
    ESP_ERROR_CHECK(err);
    
    init_uart(19200);
    init_gpio();
    
    generate_device_id_early();
    
    if (init_spiffs() != ESP_OK) {
        printf("Errore inizializzazione SPIFFS\n");
        return;
    }
    
    wifi_event_group = xEventGroupCreate();
    mqtt_event_group = xEventGroupCreate();
    
    printf("Device ID: %s\n", device_id);
    printf("MQTT Topics:\n");
    printf("  📋 Config: %s%s%s\n", MQTT_TOPIC_CONFIG_PREFIX, device_id, MQTT_TOPIC_REGISTERS_SUFFIX);
    printf("  📊 Data: %s%s%s\n", MQTT_TOPIC_DATA_PREFIX, device_id, MQTT_TOPIC_REGISTERS_SUFFIX);
    printf("  📡 Status: %s%s%s\n", MQTT_TOPIC_DATA_PREFIX, device_id, MQTT_TOPIC_STATUS_SUFFIX);
    printf("  🎮 Write Topics:\n");
    printf("    📊 Register: %s%s%s\n", MQTT_TOPIC_WRITE_PREFIX, device_id, MQTT_TOPIC_WRITE_REGISTER_SUFFIX);
    printf("    🔘 Coil: %s%s%s\n", MQTT_TOPIC_WRITE_PREFIX, device_id, MQTT_TOPIC_WRITE_COIL_SUFFIX);
    printf("    🎮 Command: %s%s%s\n", MQTT_TOPIC_WRITE_PREFIX, device_id, MQTT_TOPIC_WRITE_COMMAND_SUFFIX);
    printf("  📨 Response: %s%s%s\n", MQTT_TOPIC_WRITE_PREFIX, device_id, MQTT_TOPIC_WRITE_RESPONSE_SUFFIX);
    printf("==============================================================\n");
    printf("Caricamento configurazione...\n");
    
    print_memory_info("Startup");
    
    wifi_init();
    
    err = load_wifi_config();
    if (err != ESP_OK || !saved_config.config_done || strlen(saved_config.wifi_ssid) == 0) {
        ESP_LOGI(TAG, "Prima configurazione o dati mancanti\n");
        printf("Modalità configurazione attivata!\n");
        printf("1. Connettiti al WiFi: %s (password: %s)\n", dynamic_ap_ssid, AP_PASS);
        printf("2. Configura browser su http://192.168.4.1\n");
        printf("3. Inserisci credenziali WiFi e broker MQTT\n");
        printf("4. Timeout: 5 minuti\n");
        
        start_config_mode();
        xTaskCreate(config_task, "config_task", 4096, NULL, 5, NULL);
        
        while (current_state == STATE_CONFIG_MODE) {
            vTaskDelay(pdMS_TO_TICKS(1000));
        }
    } else {
        ESP_LOGI(TAG, "Configurazione esistente trovata\n");
        printf("WiFi: %s\n", saved_config.wifi_ssid);
        printf("MQTT Broker: %s:%d\n", saved_config.mqtt_broker, saved_config.mqtt_port);
        
        // Carica configurazione registri da NVS (ora con chunked storage + commands)
        if (load_device_config() == ESP_OK) {
            printf("✅ Configurazione registri caricata da NVS\n");
            printf("📊 Device: %s, Slave: %d, Registri: %d, Commands: %d\n", 
                   device_config.device, device_config.slave_address, 
                   device_config.total_registers, device_config.commands_count);
        } else {
            ESP_LOGI(TAG, "⏳ Nessuna configurazione registri trovata in NVS, attesa MQTT\n");
        }
        
        ESP_LOGI(TAG, "Tentativo connessione WiFi...");
        err = start_wifi_sta();
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "Errore avvio WiFi: %s", esp_err_to_name(err));
            current_state = STATE_ERROR;
        } else {
            EventBits_t bits = xEventGroupWaitBits(wifi_event_group,
                                                   WIFI_CONNECTED_BIT,
                                                   pdFALSE, pdFALSE,
                                                   pdMS_TO_TICKS(WIFI_CONNECT_TIMEOUT_MS));
            
            if (!(bits & WIFI_CONNECTED_BIT)) {
                ESP_LOGW(TAG, "Connessione WiFi fallita - avvio modalità configurazione\n");
                printf("Impossibile connettersi a: %s\n", saved_config.wifi_ssid);
                printf("Avvio modalità riconfigurazione...\n");
                
                esp_wifi_stop();
                start_config_mode();
                xTaskCreate(config_task, "config_task", 4096, NULL, 5, NULL);
                
                while (current_state == STATE_CONFIG_MODE) {
                    vTaskDelay(pdMS_TO_TICKS(1000));
                }
            }
        }
    }
    
    if (current_state == STATE_RUNNING) {
        printf("Sistema configurato e connesso!\n");
        printf("WiFi: CONNESSO\n");
        printf("MQTT Broker: %s:%d\n", saved_config.mqtt_broker, saved_config.mqtt_port);
        
        print_memory_info("WiFi Connected");
        
        init_sntp();
        start_running_server();
        
        ESP_LOGI(TAG, "Inizializzazione client MQTT...");
        if (init_mqtt_client() != ESP_OK) {
            ESP_LOGE(TAG, "Errore inizializzazione MQTT - modalità errore\n");
            current_state = STATE_ERROR;
        } else {
            EventBits_t mqtt_bits = xEventGroupWaitBits(mqtt_event_group,
                                                        MQTT_CONNECTED_BIT,
                                                        pdFALSE, pdFALSE,
                                                        pdMS_TO_TICKS(10000));
            
            if (mqtt_bits & MQTT_CONNECTED_BIT) {
                ESP_LOGI(TAG, "MQTT connesso!\n");
                
                ESP_LOGI(TAG, "Aspettando sincronizzazione orario...\n");
                int retry = 0;
                const int retry_count = 10;
                while (sntp_get_sync_status() == SNTP_SYNC_STATUS_RESET && ++retry < retry_count) {
                    ESP_LOGI(TAG, "Aspettando sincronizzazione SNTP... (%d/%d)\n", retry, retry_count);
                    vTaskDelay(pdMS_TO_TICKS(2000));
                }
                
                if (sntp_get_sync_status() == SNTP_SYNC_STATUS_COMPLETED) {
                    ESP_LOGI(TAG, "Orario sincronizzato con SNTP\n");
                    char datetime_str[256];
                    get_current_datetime(datetime_str, sizeof(datetime_str));
                    ESP_LOGI(TAG, "Data/Ora attuale: %s\n", datetime_str);
                } else {
                    ESP_LOGW(TAG, "Timeout sincronizzazione SNTP - continuo con orario locale\n");
                }
                
                if (wait_for_mqtt_config() == ESP_OK) {
                    printf("🚀 Configurazione completa:\n");
                    printf("==============================================================\n");
                    printf("📋 Device Type: %s\n", device_config.device);
                    printf("📊 Slave Address: %d\n", device_config.slave_address);
                    printf("🔧 Baud Rate: %lu\n", device_config.baud_rate);    
                    printf("📈 Total Registers: %d\n", device_config.total_registers);
                    printf("🎮 Total Commands: %d\n", device_config.commands_count);
                    printf("🔖 Template ID: %s\n", device_config.template_id);
                    printf("📌 Holding Registers: %d\n", device_config.holding_count);
                    printf("🔢 Coils: %d\n", device_config.coils_count);
                    printf("🎮 Write Support: ENABLED\n");
                    printf("==============================================================\n");
                    
                    post_config_diagnostics();
                    
                    printf("🚀 Avvio lettura registri con supporto scrittura...\n");
                                        
                    vTaskDelay(pdMS_TO_TICKS(2000));
                    
                    int cycle = 1;
                    while (true) {
                        if (wifi_connected && mqtt_connected) {
                            char datetime_str[256];
                            get_current_datetime(datetime_str, sizeof(datetime_str));
                            
                            printf("\n=== Ciclo %d (%s) ===\n", 
                                 cycle++, datetime_str);
                            read_all_registers();
                            
                            printf("\nAttendo 10 secondi...\n");
                        } else {
                            printf("Connessione persa - tentativo riconnessione...\n");
                            vTaskDelay(pdMS_TO_TICKS(5000));
                        }
                        vTaskDelay(pdMS_TO_TICKS(10000));
                    }
                }
                
                printf("Configurazione non ricevuta da MQTT\n");
                printf("Errore: verifica che il server sia configurato\n");
                current_state = STATE_ERROR;
            }
            
            ESP_LOGE(TAG, "Timeout connessione MQTT\n");
            current_state = STATE_ERROR;
        }
    }
    
    if (current_state == STATE_ERROR) {
        printf("Modalità ERRORE - Riavvia e configura\n");
        while (true) {
            print_memory_info("Error State");
            vTaskDelay(pdMS_TO_TICKS(30000));
        }
    }
}