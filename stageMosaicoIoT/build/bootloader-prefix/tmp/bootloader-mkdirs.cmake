# Distributed under the OSI-approved BSD 3-Clause License.  See accompanying
# file Copyright.txt or https://cmake.org/licensing for details.

cmake_minimum_required(VERSION 3.5)

file(MAKE_DIRECTORY
  "/home/riccardo/esp/esp-idf/components/bootloader/subproject"
  "/home/riccardo/Scrivania/Progetti/SistemaIoTcentralina/esp32c6_mosaico/stageMosaicoIoT/build/bootloader"
  "/home/riccardo/Scrivania/Progetti/SistemaIoTcentralina/esp32c6_mosaico/stageMosaicoIoT/build/bootloader-prefix"
  "/home/riccardo/Scrivania/Progetti/SistemaIoTcentralina/esp32c6_mosaico/stageMosaicoIoT/build/bootloader-prefix/tmp"
  "/home/riccardo/Scrivania/Progetti/SistemaIoTcentralina/esp32c6_mosaico/stageMosaicoIoT/build/bootloader-prefix/src/bootloader-stamp"
  "/home/riccardo/Scrivania/Progetti/SistemaIoTcentralina/esp32c6_mosaico/stageMosaicoIoT/build/bootloader-prefix/src"
  "/home/riccardo/Scrivania/Progetti/SistemaIoTcentralina/esp32c6_mosaico/stageMosaicoIoT/build/bootloader-prefix/src/bootloader-stamp"
)

set(configSubDirs )
foreach(subDir IN LISTS configSubDirs)
    file(MAKE_DIRECTORY "/home/riccardo/Scrivania/Progetti/SistemaIoTcentralina/esp32c6_mosaico/stageMosaicoIoT/build/bootloader-prefix/src/bootloader-stamp/${subDir}")
endforeach()
if(cfgdir)
  file(MAKE_DIRECTORY "/home/riccardo/Scrivania/Progetti/SistemaIoTcentralina/esp32c6_mosaico/stageMosaicoIoT/build/bootloader-prefix/src/bootloader-stamp${cfgdir}") # cfgdir has leading slash
endif()
