cmake_minimum_required(VERSION 3.16)

# Configurazione partizioni
set(PARTITION_TABLE_CSV_PATH ${CMAKE_CURRENT_SOURCE_DIR}/partitions.csv)

# Include ESP-IDF build system
include($ENV{IDF_PATH}/tools/cmake/project.cmake)

# Definisce il progetto
project(device_bridge)

# Prepara directory SPIFFS combinata
file(MAKE_DIRECTORY ${CMAKE_BINARY_DIR}/spiffs_combined)

# Copia SOLO file da spiffs_data (spiffs_image rimossa)
file(COPY ${CMAKE_SOURCE_DIR}/spiffs_data/ DESTINATION ${CMAKE_BINARY_DIR}/spiffs_combined/)

# Crea immagine SPIFFS con i file rimanenti
spiffs_create_partition_image(spiffs ${CMAKE_BINARY_DIR}/spiffs_combined FLASH_IN_PROJECT)