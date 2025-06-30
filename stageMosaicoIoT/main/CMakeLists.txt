idf_component_register(
    SRCS "master.c"
    INCLUDE_DIRS "."
    REQUIRES 
        driver 
        esp_wifi 
        esp_netif 
        esp_event 
        esp_timer
        esp_http_server 
        nvs_flash 
        freertos 
        json 
        spiffs
        lwip
        vfs
        mqtt
    EMBED_FILES "../spiffs_data/config.html" "../spiffs_data/reset.html"
)