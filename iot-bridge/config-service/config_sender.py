"""
Config Service Esteso - Con Dashboard MQTT e Configurazione Dinamica
Versione aggiornata con supporto per dispositivi temporanei e configurazione automatica
+ NUOVO: Endpoint per lettura registri dispositivi da Kafka
+ FIX: Salvataggio configurazioni generate in /app/templates/json
+ NUOVO: PERSISTENT STORAGE in templates/json
+ FIX: Gestione directory migliorata per Docker
+ NUOVO: DUAL CONFIGURATION SYSTEM (Essential + Complete)
+ 🆕 NUOVO: API SCRITTURA MODBUS (Commands + Parameters)
"""

import json
import os
import time
import logging
import subprocess
from flask import Flask, request, jsonify, render_template_string, send_from_directory
from kafka import KafkaProducer, KafkaConsumer
from kafka.errors import KafkaError
import threading
from collections import defaultdict, deque
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

class ExtendedConfigService:
    def __init__(self):
        self.producer = None
        self.broker_running = False
        self.connected_devices = {}
        self.pending_devices = {}  # ✅ NUOVO: Dispositivi da configurare
        self.device_registers = defaultdict(lambda: {})  # ✅ NUOVO: Cache registri (ultimo valore)
        self.message_count = 0
        self.start_time = time.time()
        
        # 📁 PERSISTENT STORAGE - DIRECTORY STRUCTURE MIGLIORATA
        self.base_templates_dir = '/app/templates'
        self.json_configs_dir = os.path.join(self.base_templates_dir, 'json')
        self.xml_templates_dir = os.path.join(self.base_templates_dir, 'xml')
        
        # ✅ MIGLIORE GESTIONE CREAZIONE DIRECTORY
        self.ensure_directories_exist()
        
        self.config_cache = {}  # Cache in memoria delle configurazioni persistenti
        self.complete_config_cache = {}  # 🆕 Cache configurazioni complete per enrichment
        self.load_configs_from_disk()  # Carica configurazioni all'avvio
        
        self.connect_to_kafka()
        self.start_device_monitor()
        self.start_registers_monitor()  # ✅ NUOVO: Monitor registri
    
    def ensure_directories_exist(self):
        """Assicura che tutte le directory necessarie esistano con permessi corretti"""
        directories = [
            self.base_templates_dir,
            self.json_configs_dir, 
            self.xml_templates_dir
        ]
        
        for directory in directories:
            try:
                os.makedirs(directory, mode=0o755, exist_ok=True)
                
                # Verifica permessi di scrittura
                test_file = os.path.join(directory, '.write_test')
                try:
                    with open(test_file, 'w') as f:
                        f.write('test')
                    os.remove(test_file)
                    logger.info(f"✅ Directory OK: {directory}")
                except Exception as e:
                    logger.warning(f"⚠ Directory non scrivibile: {directory} - {e}")
                    
            except Exception as e:
                logger.error(f"❌ Errore creazione directory {directory}: {e}")
                # Prova directory alternative
                if directory == self.json_configs_dir:
                    self.json_configs_dir = '/tmp/json_configs'
                    os.makedirs(self.json_configs_dir, mode=0o755, exist_ok=True)
                    logger.info(f"🔄 Usata directory alternativa: {self.json_configs_dir}")
        
        logger.info(f"📁 Configurazione directory:")
        logger.info(f"   Base: {self.base_templates_dir}")
        logger.info(f"   JSON: {self.json_configs_dir}")
        logger.info(f"   XML: {self.xml_templates_dir}")
    
    # 📁 PERSISTENT STORAGE - NUOVE FUNZIONI
    def load_configs_from_disk(self):
        """Carica configurazioni esistenti da disco nella cache"""
        try:
            if not os.path.exists(self.json_configs_dir):
                logger.info(f"📂 Directory {self.json_configs_dir} non esiste ancora, sarà creata al primo salvataggio")
                return 0
                
            json_files = Path(self.json_configs_dir).glob("*.json")
            loaded_count = 0
            
            for json_file in json_files:
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        config_data = json.load(f)
                        
                    # Estrae device_id dal filename o config
                    device_id = json_file.stem  # filename senza estensione
                    
                    # 🆕 DUAL SYSTEM: Distingui tra essential e complete
                    if device_id.endswith('_complete'):
                        # Configurazione completa per enrichment
                        actual_device_id = device_id.replace('_complete', '')
                        self.complete_config_cache[actual_device_id] = config_data
                        logger.info(f"✅ Caricata config COMPLETA per device: {actual_device_id}")
                    else:
                        # Configurazione essenziale
                        if 'metadata' in config_data and 'device_id' in config_data['metadata']:
                            device_id = config_data['metadata']['device_id']
                        self.config_cache[device_id] = config_data
                        logger.info(f"✅ Caricata config ESSENZIALE per device: {device_id}")
                    
                    loaded_count += 1
                    
                except Exception as e:
                    logger.error(f"❌ Errore caricamento {json_file}: {e}")
            
            logger.info(f"📂 Caricate {loaded_count} configurazioni da disco")
            logger.info(f"   📊 Essential: {len(self.config_cache)}")
            logger.info(f"   🔧 Complete: {len(self.complete_config_cache)}")
            return loaded_count
            
        except Exception as e:
            logger.error(f"❌ Errore caricamento configs da disco: {e}")
            return 0

    def save_config_to_disk(self, device_id, config_data):
        """Salva configurazione su file JSON persistente"""
        try:
            # Assicura che la directory esista
            os.makedirs(self.json_configs_dir, mode=0o755, exist_ok=True)
            
            # Crea nome file
            filename = f"{device_id}.json"
            filepath = os.path.join(self.json_configs_dir, filename)
            
            # Aggiungi metadata se non presente
            if 'metadata' not in config_data:
                config_data['metadata'] = {}
            
            config_data['metadata']['device_id'] = device_id
            config_data['metadata']['saved_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
            config_data['metadata']['file_version'] = "1.0"
            
            # Salva su disco
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
            
            # Aggiorna cache
            self.config_cache[device_id] = config_data
            
            logger.info(f"💾 Configurazione salvata: {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Errore salvataggio config per {device_id}: {e}")
            return False

    # 🆕 NUOVO: Funzione per salvare configurazione completa
    def save_complete_config_to_disk(self, device_id, config_data):
        """Salva configurazione COMPLETA su file JSON persistente"""
        try:
            # Assicura che la directory esista
            os.makedirs(self.json_configs_dir, mode=0o755, exist_ok=True)
            
            # Crea nome file con suffisso _complete
            filename = f"{device_id}_complete.json"
            filepath = os.path.join(self.json_configs_dir, filename)
            
            # Aggiungi metadata se non presente
            if 'metadata' not in config_data:
                config_data['metadata'] = {}
            
            config_data['metadata']['device_id'] = device_id
            config_data['metadata']['saved_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
            config_data['metadata']['file_version'] = "2.0-complete"
            config_data['metadata']['config_type'] = "complete"
            
            # Salva su disco
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
            
            # Aggiorna cache completa
            self.complete_config_cache[device_id] = config_data
            
            logger.info(f"💾 Configurazione COMPLETA salvata: {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Errore salvataggio config completa per {device_id}: {e}")
            return False

    def delete_config_from_disk(self, device_id):
        """Elimina configurazione da disco"""
        try:
            # Elimina file essential
            filename = f"{device_id}.json"
            filepath = os.path.join(self.json_configs_dir, filename)
            
            if os.path.exists(filepath):
                os.remove(filepath)
                logger.info(f"🗑 Eliminato file config: {filepath}")
            
            # Elimina file complete
            complete_filename = f"{device_id}_complete.json"
            complete_filepath = os.path.join(self.json_configs_dir, complete_filename)
            
            if os.path.exists(complete_filepath):
                os.remove(complete_filepath)
                logger.info(f"🗑 Eliminato file config completo: {complete_filepath}")
            
            # Rimuovi dalla cache
            if device_id in self.config_cache:
                del self.config_cache[device_id]
            
            if device_id in self.complete_config_cache:
                del self.complete_config_cache[device_id]
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Errore eliminazione config per {device_id}: {e}")
            return False
    
    def connect_to_kafka(self):
        """Connetti a Kafka - compatibile con tutte le versioni"""
        try:
            self.producer = KafkaProducer(
                bootstrap_servers=[os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'kafka:29092')],
                value_serializer=lambda v: json.dumps(v, separators=(',', ':')).encode('utf-8'),
                key_serializer=lambda k: k.encode('utf-8') if k else None,
                acks='all',
                retries=3
            )
            logger.info("✅ Connesso a Kafka")
        except Exception as e:
            logger.error(f"❌ Errore connessione Kafka: {e}")
            self.producer = None
    
    def start_device_monitor(self):
        """Avvia monitoraggio dispositivi da Kafka"""
        def monitor():
            try:
                consumer = KafkaConsumer(
                    'device.data.status',
                    bootstrap_servers=[os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'kafka:29092')],
                    value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                    key_deserializer=lambda m: m.decode('utf-8') if m else None,
                    group_id='dashboard-monitor' + str(int(time.time())),
                    auto_offset_reset='earliest'
                )
                
                logger.info("📡 Monitoraggio dispositivi avviato (Kafka Consumer)")
                logger.info(f"📡 Group ID: dashboard-monitor-{int(time.time())}")
               
                for message in consumer:
                    try:
                        device_id = message.key
                        status_data = message.value
                        
                        if device_id and status_data:
                            self.update_device_status(device_id, status_data)
                            self.message_count += 1
                            
                    except Exception as e:
                        logger.error(f"Errore processing device status: {e}")
                        
            except Exception as e:
                logger.error(f"Errore device monitor: {e}")
        
        # Avvia monitor in thread separato
        monitor_thread = threading.Thread(target=monitor, daemon=True)
        monitor_thread.start()
    
    def start_registers_monitor(self):
        def monitor_registers():
            try:
                consumer = KafkaConsumer(
                    'device.data.registers',
                    bootstrap_servers=[os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'kafka:29092')],
                    value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                    key_deserializer=lambda m: m.decode('utf-8') if m else None,
                    group_id='registers-monitor' + str(int(time.time())),
                    auto_offset_reset='latest'  # Solo nuovi messaggi
                )
                
                logger.info("📊 Monitoraggio registri avviato (Kafka Consumer)")
                logger.info(f"📊 Group ID: registers-monitor-{int(time.time())}")
            
                for message in consumer:
                    try:
                        device_id = message.key
                        registers_data = message.value
                        
                        if device_id and registers_data:
                            # ✅ FIX: Aggiorna ogni registro individualmente
                            registers = registers_data.get('registers', [])
                            for register in registers:
                                address = register.get('address')
                                if address is not None:
                                    # Salva ultimo valore per ogni indirizzo
                                    self.device_registers[device_id][address] = {
                                        'value': register.get('value'),
                                        'name': register.get('name', f'Reg{address}'),
                                        'type': register.get('type', 'Register'),
                                        'timestamp': registers_data.get('datetime', time.strftime('%Y-%m-%d %H:%M:%S')),
                                        'timestamp_ms': registers_data.get('timestamp_ms', int(time.time() * 1000)),
                                        'last_update': time.time()
                                    }
                            
                            if registers:
                                logger.debug(f"📊 Aggiornati {len(registers)} registri per {device_id}")
                            
                    except Exception as e:
                        logger.error(f"Errore processing registers: {e}")
                        
            except Exception as e:
                logger.error(f"Errore registers monitor: {e}")
        
        # Avvia monitor registri in thread separato
        registers_thread = threading.Thread(target=monitor_registers, daemon=True)
        registers_thread.start()
    
    def get_device_registers(self, device_id):
        """✅ FIX: Ottieni tutti i registri con ultimo valore per dispositivo"""
        if device_id not in self.device_registers:
            return None
        
        registers_dict = self.device_registers[device_id]
        if not registers_dict:
            return None
            
        # Converte il dict in formato lista per compatibilità API
        registers_list = []
        for address, reg_data in registers_dict.items():
            registers_list.append({
                'address': address,
                'name': reg_data.get('name', f'Reg{address}'),
                'value': reg_data.get('value'),
                'type': reg_data.get('type', 'Register'),
                'timestamp': reg_data.get('timestamp'),
                'last_update': reg_data.get('last_update', 0)
            })
        
        # Ordina per indirizzo
        registers_list.sort(key=lambda x: x['address'])
        
        # Trova il timestamp più recente
        latest_timestamp = None
        if registers_list:
            latest_timestamps = [r.get('timestamp') for r in registers_list if r.get('timestamp')]
            if latest_timestamps:
                latest_timestamp = max(latest_timestamps)
        
        return {
            'timestamp': latest_timestamp,
            'timestamp_ms': max([r.get('last_update', 0) for r in registers_dict.values()]) if registers_dict else 0,
            'device_id': device_id,
            'slave_address': 0,  # Non abbiamo questo dato qui
            'registers': registers_list
        }

    
    def update_device_status(self, device_id, status_data):
        """Aggiorna stato dispositivo - VERSIONE AGGIORNATA"""
        status = status_data.get('status', 'unknown')
        
        # ✅ NUOVO: Gestisci dispositivi in attesa di configurazione
        if status == 'awaiting_config' and device_id.startswith('device_'):
            self.pending_devices[device_id] = {
                'device_id': device_id,
                'status': 'awaiting_config',
                'detected_at': time.time(),
                'last_seen': time.time(),
                'device_type': status_data.get('device_type', 'unknown'),
                'free_heap_bytes': status_data.get('free_heap_bytes', 0),
                'wifi_rssi': status_data.get('wifi_rssi', -99),
                'uptime_seconds': status_data.get('uptime_seconds', 0)
            }
            logger.info(f"📱 Nuovo dispositivo da configurare: {device_id}")
            return
        
        # ✅ ESISTENTE: Dispositivi configurati (non iniziano con 'device_')
        if not device_id.startswith('device_'):
            self.connected_devices[device_id] = {
                'device_id': device_id,
                'device_type': status_data.get('device_type', 'unknown'),
                'slave_address': status_data.get('slave_address', 0),
                'total_registers': status_data.get('total_registers', 0),
                'wifi_rssi': status_data.get('wifi_rssi', -99),
                'status': status,
                'last_seen': time.time(),
                'uptime_seconds': status_data.get('uptime_seconds', 0),
                'free_heap_bytes': status_data.get('free_heap_bytes', 0),
                'config_loaded': status_data.get('config_loaded', False)
            }
            
            # ✅ NUOVO: Rimuovi da pending se era lì (dopo configurazione)
            old_device = None
            for pid in list(self.pending_devices.keys()):
                # Cerca corrispondenze: device_abc123 → mx_197
                if pid in device_id or device_id.split('_')[0] in pid:
                    old_device = pid
                    break
            if old_device:
                del self.pending_devices[old_device]
                logger.info(f"✅ Device {old_device} configurato → {device_id}")
            
            logger.info(f"📱 Device aggiornato: {device_id} ({status})")
    
    # 🆕 NUOVE FUNZIONI PER SCRITTURA MODBUS
    def send_write_command_to_kafka(self, device_id, command_type, command_data):
        """
        🆕 NUOVO: Invia comando di scrittura Modbus via Kafka
        
        Args:
            device_id (str): ID del dispositivo target
            command_type (str): 'write_register' | 'write_coil' | 'send_command'
            command_data (dict): Dati del comando
        
        Returns:
            bool: True se inviato con successo
        """
        if not self.producer:
            logger.error("❌ Kafka producer non disponibile per scrittura")
            return False
        
        try:
            # Mapping topic Kafka per comandi di scrittura
            topic_mapping = {
                'write_register': 'device.write.command',
                'write_coil': 'device.write.command', 
                'send_command': 'device.write.command'
            }
            
            kafka_topic = topic_mapping.get(command_type)
            if not kafka_topic:
                logger.error(f"❌ Tipo comando sconosciuto: {command_type}")
                return False
            
            # Prepara payload con metadata
            payload = {
                'device_id': device_id,
                'command_type': command_type,
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                'timestamp_ms': int(time.time() * 1000),
                **command_data
            }
            
            # Invia a Kafka
            future = self.producer.send(
                kafka_topic,
                key=device_id,
                value=payload
            )
            
            # Attendi conferma
            record_metadata = future.get(timeout=10)
            
            logger.info(f"✅ Comando {command_type} inviato a Kafka:")
            logger.info(f"   📍 Topic: {record_metadata.topic}")
            logger.info(f"   📍 Device: {device_id}")
            logger.info(f"   📊 Comando: {command_data}")
            
            return True
            
        except KafkaError as e:
            logger.error(f"❌ Errore Kafka scrittura: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Errore generico scrittura: {e}")
            return False

    def validate_write_register_payload(self, payload):
        """
        🆕 NUOVO: Valida payload per scrittura registro
        
        Args:
            payload (dict): Dati da validare
            
        Returns:
            tuple: (is_valid, error_message)
        """
        required_fields = ['address', 'value']
        
        for field in required_fields:
            if field not in payload:
                return False, f"Campo richiesto mancante: {field}"
        
        # Valida indirizzo
        try:
            address = int(payload['address'])
            if not (0 <= address <= 65535):
                return False, "Indirizzo deve essere tra 0 e 65535"
        except (ValueError, TypeError):
            return False, "Indirizzo deve essere un numero intero"
        
        # Valida valore
        try:
            value = int(payload['value'])
            if not (0 <= value <= 65535):
                return False, "Valore deve essere tra 0 e 65535"
        except (ValueError, TypeError):
            return False, "Valore deve essere un numero intero"
        
        return True, None

    def validate_write_coil_payload(self, payload):
        """
        🆕 NUOVO: Valida payload per scrittura coil
        
        Args:
            payload (dict): Dati da validare
            
        Returns:
            tuple: (is_valid, error_message)
        """
        required_fields = ['address', 'value']
        
        for field in required_fields:
            if field not in payload:
                return False, f"Campo richiesto mancante: {field}"
        
        # Valida indirizzo
        try:
            address = int(payload['address'])
            if not (0 <= address <= 65535):
                return False, "Indirizzo deve essere tra 0 e 65535"
        except (ValueError, TypeError):
            return False, "Indirizzo deve essere un numero intero"
        
        # Valida valore (coil: 0 o 1)
        try:
            value = int(payload['value'])
            if value not in [0, 1]:
                return False, "Valore coil deve essere 0 o 1"
        except (ValueError, TypeError):
            return False, "Valore coil deve essere un numero intero (0 o 1)"
        
        return True, None

    def validate_send_command_payload(self, payload):
        """
        🆕 NUOVO: Valida payload per invio comando
        
        Args:
            payload (dict): Dati da validare
            
        Returns:
            tuple: (is_valid, error_message)
        """
        required_fields = ['command_name', 'address', 'value_command']
        
        for field in required_fields:
            if field not in payload:
                return False, f"Campo richiesto mancante: {field}"
        
        # Valida indirizzo
        try:
            address = int(payload['address'])
            if not (0 <= address <= 65535):
                return False, "Indirizzo deve essere tra 0 e 65535"
        except (ValueError, TypeError):
            return False, "Indirizzo deve essere un numero intero"
        
        # Valida value_command (solitamente 0 o 1)
        try:
            value_command = int(payload['value_command'])
            if value_command not in [0, 1]:
                return False, "value_command deve essere 0 o 1"
        except (ValueError, TypeError):
            return False, "value_command deve essere un numero intero (0 o 1)"
        
        # Valida nome comando
        command_name = payload['command_name'].strip()
        if not command_name:
            return False, "Nome comando non può essere vuoto"
        
        return True, None
    
    def start_mqtt_broker(self):
        """Avvia broker MQTT (docker container)"""
        try:
            # Verifica se il container mosquitto è già running
            result = subprocess.run(['docker', 'ps', '--filter', 'name=mosquitto', '--format', '{{.Names}}'], 
                                   capture_output=True, text=True)
            
            if 'mosquitto' in result.stdout:
                logger.info("🟢 Broker MQTT già in esecuzione")
                self.broker_running = True
                return True
            
            # Avvia il container mosquitto
            subprocess.run(['docker', 'start', 'mosquitto'], check=True)
            self.broker_running = True
            logger.info("✅ Broker MQTT avviato")
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"❌ Errore avvio broker MQTT: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Errore generico avvio broker: {e}")
            return False
    
    def stop_mqtt_broker(self):
        """Ferma broker MQTT (docker container)"""
        try:
            subprocess.run(['docker', 'stop', 'mosquitto'], check=True)
            self.broker_running = False
            self.connected_devices.clear()
            logger.info("🛑 Broker MQTT fermato")
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"❌ Errore stop broker MQTT: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Errore generico stop broker: {e}")
            return False
    
    def get_broker_status(self):
        """Ottieni stato attuale del broker"""
        try:
            result = subprocess.run(['docker', 'ps', '--filter', 'name=mosquitto', '--format', '{{.Names}}'], 
                                   capture_output=True, text=True)
            self.broker_running = 'mosquitto' in result.stdout
            return self.broker_running
        except:
            self.broker_running = False
            return False
    
    def send_to_kafka(self, device_id, config_data):
        """Invia configurazione compressa a Kafka"""
        if not self.producer:
            logger.error("❌ Kafka producer non disponibile")
            return False
        
        try:
            # Comprimi configurazione (rimuovi spazi e indentazioni)
            logger.info(f"📦 Processando configurazione per {device_id}...")
            
            original_size = len(json.dumps(config_data))
            compressed_size = len(json.dumps(config_data, separators=(',', ':')))
            reduction = ((original_size - compressed_size) / original_size) * 100
            
            logger.info(f"📦 Configurazione pronta:")
            logger.info(f"   📄 Dimensione: {compressed_size:,} bytes ({compressed_size//1024:.1f} KB)")
            logger.info(f"   📉 JSON compattato: {reduction:.1f}% di riduzione")
            logger.info(f"   📊 Holding registers: {len(config_data.get('holding_registers', []))}")
            logger.info(f"   🔘 Coils: {len(config_data.get('coils', []))}")
            logger.info(f"   🎮 Commands: {len(config_data.get('commands', []))}")
            
            if compressed_size < 30000:
                logger.info(f"   ✅ Dimensione ottimale per ESP32!")
            elif compressed_size < 50000:
                logger.info(f"   ⚠  Dimensione accettabile per ESP32")
            else:
                logger.warning(f"   ❌ Dimensione grande per ESP32 ({compressed_size//1024}KB)")
            
            # Invia a Kafka per il bridge
            future = self.producer.send(
                'device.config',
                key=device_id,
                value=config_data
            )
            
            # Attendi conferma
            record_metadata = future.get(timeout=10)
            
            logger.info(f"✅ Configurazione inviata a Kafka:")
            logger.info(f"   📍 Topic: {record_metadata.topic}")
            logger.info(f"   📍 Key: {device_id}")
            logger.info(f"   📊 Registri: {config_data['metadata']['total_registers']}")
            logger.info(f"   🎮 Commands: {config_data['metadata'].get('total_commands', 0)}")
            
            return True
            
        except KafkaError as e:
            logger.error(f"❌ Errore Kafka: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Errore generico: {e}")
            return False

    def cleanup_old_devices(self, timeout_seconds=60):
        """Rimuovi dispositivi non visti da tempo - VERSIONE ESTESA"""
        current_time = time.time()
        
        # Cleanup dispositivi configurati
        to_remove = []
        for device_id, device_data in self.connected_devices.items():
            if current_time - device_data['last_seen'] > timeout_seconds:
                to_remove.append(device_id)
        
        for device_id in to_remove:
            del self.connected_devices[device_id]
            logger.info(f"🗑 Rimosso device inattivo: {device_id}")
        
        # ✅ NUOVO: Cleanup dispositivi pending (timeout più lungo - 10 minuti)
        to_remove_pending = []
        for device_id, device_data in self.pending_devices.items():
            if current_time - device_data['last_seen'] > 600:  # 10 minuti
                to_remove_pending.append(device_id)
        
        for device_id in to_remove_pending:
            del self.pending_devices[device_id]
            logger.info(f"🗑 Rimosso device pending scaduto: {device_id}")

# Istanza globale
config_service = ExtendedConfigService()

# ===================== FUNZIONI HELPER =====================

def generate_config_dynamic(template, device_name, slave_address, baud_rate):
    """Genera configurazione ESSENZIALE usando xml_parser modificato"""
    
    try:
        import sys
        sys.path.append('/app/parser')
        import xml_parser
        
        # Ottieni template disponibili dinamicamente
        available_templates = xml_parser.get_available_templates()
        
        if not available_templates:
            raise ValueError("Nessun template XML trovato in /app/templates/")
        
        if template not in available_templates:
            raise ValueError(f"Template '{template}' non trovato. Disponibili: {list(available_templates.keys())}")
        
        xml_file = available_templates[template]
        
        # Genera configurazione ESSENZIALE usando la versione programmatica
        config = xml_parser.convert_xml_to_json_programmatic(
            xml_file=xml_file,
            slave_address=slave_address,
            baud_rate=baud_rate,
            device_name=device_name
        )
        
        return config
        
    except ImportError as e:
        raise ValueError(f"xml_parser.py non trovato: {e}")
    except Exception as e:
        raise ValueError(f"Errore generazione config: {e}")

# 🆕 NUOVO: Funzione per generare configurazione completa
def generate_config_complete(template, device_name, slave_address, baud_rate):
    """Genera configurazione COMPLETA usando xml_parser modificato"""
    
    try:
        import sys
        sys.path.append('/app/parser')
        import xml_parser
        
        # Ottieni template disponibili dinamicamente
        available_templates = xml_parser.get_available_templates()
        
        if not available_templates:
            raise ValueError("Nessun template XML trovato in /app/templates/")
        
        if template not in available_templates:
            raise ValueError(f"Template '{template}' non trovato. Disponibili: {list(available_templates.keys())}")
        
        xml_file = available_templates[template]
        
        # Genera configurazione COMPLETA usando la versione programmatica
        config = xml_parser.convert_xml_to_json_complete(
            xml_file=xml_file,
            slave_address=slave_address,
            baud_rate=baud_rate,
            device_name=device_name
        )
        
        return config
        
    except ImportError as e:
        raise ValueError(f"xml_parser.py non trovato: {e}")
    except Exception as e:
        raise ValueError(f"Errore generazione config completa: {e}")

# ✅ AGGIORNATO: Funzioni per gestione configurazioni salvate in PERSISTENT STORAGE
def save_config_to_templates(config, device_name, slave_address):
    """
    Salva la configurazione ESSENZIALE generata nella directory PERSISTENTE templates/json
    """
    try:
        # 💾 CAMBIO: Directory persistente (mount esterno)
        json_dir = config_service.json_configs_dir
        os.makedirs(json_dir, exist_ok=True)
        
        # Nome file: device_slaveid.json (es: mx_197.json)
        filename = f"{device_name}_{slave_address}.json"
        filepath = os.path.join(json_dir, filename)
        
        # Salva il JSON con indentazione per leggibilità
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        # 💾 NUOVO: Salva anche in cache
        device_id = f"{device_name}_{slave_address}"
        config_service.config_cache[device_id] = config
        
        # Log dettagliato
        file_size = os.path.getsize(filepath)
        logger.info(f"💾 Configurazione ESSENZIALE salvata in {filepath}")
        logger.info(f"   📁 File: {filename}")
        logger.info(f"   📦 Size: {file_size:,} bytes ({file_size//1024:.1f} KB)")
        logger.info(f"   📊 Registri: {config['metadata']['total_registers']}")
        logger.info(f"   🎮 Commands: {config['metadata'].get('total_commands', 0)}")
        logger.info(f"   🏷  Device: {device_name} (slave {slave_address})")
        logger.info(f"   💾 Storage: PERSISTENTE (templates/json)")
        
        return filepath
        
    except Exception as e:
        logger.error(f"❌ Errore salvataggio config persistente: {e}")
        return None

# 🆕 NUOVO: Funzione per salvare configurazione completa
def save_complete_config_to_templates(config, device_name, slave_address):
    """
    Salva la configurazione COMPLETA generata nella directory PERSISTENTE templates/json
    """
    try:
        # 💾 Directory persistente (mount esterno)
        json_dir = config_service.json_configs_dir
        os.makedirs(json_dir, exist_ok=True)
        
        # Nome file: device_slaveid_complete.json (es: mx_197_complete.json)
        filename = f"{device_name}_{slave_address}_complete.json"
        filepath = os.path.join(json_dir, filename)
        
        # Salva il JSON con indentazione per leggibilità
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        # 💾 NUOVO: Salva anche in cache completa
        device_id = f"{device_name}_{slave_address}"
        config_service.complete_config_cache[device_id] = config
        
        # Log dettagliato
        file_size = os.path.getsize(filepath)
        logger.info(f"💾 Configurazione COMPLETA salvata in {filepath}")
        logger.info(f"   📁 File: {filename}")
        logger.info(f"   📦 Size: {file_size:,} bytes ({file_size//1024:.1f} KB)")
        logger.info(f"   📊 Registri: {config['metadata']['total_registers']}")
        logger.info(f"   🎮 Commands: {config['metadata'].get('total_commands', 0)}")
        logger.info(f"   🔧 Enrichment: descriptions, gain, decimals, measurement")
        logger.info(f"   🏷  Device: {device_name} (slave {slave_address})")
        logger.info(f"   💾 Storage: PERSISTENTE (templates/json)")
        
        return filepath
        
    except Exception as e:
        logger.error(f"❌ Errore salvataggio config completa persistente: {e}")
        return None

# 🆕 NUOVO: Funzione per salvare entrambe le configurazioni
def save_dual_configs_to_templates(essential_config, complete_config, device_name, slave_address):
    """
    Salva ENTRAMBE le configurazioni (essential + complete) nella directory PERSISTENTE
    """
    try:
        results = {}
        
        # Salva configurazione essenziale
        essential_path = save_config_to_templates(essential_config, device_name, slave_address)
        results['essential_saved'] = essential_path is not None
        results['essential_file'] = os.path.basename(essential_path) if essential_path else None
        
        # Salva configurazione completa
        complete_path = save_complete_config_to_templates(complete_config, device_name, slave_address)
        results['complete_saved'] = complete_path is not None
        results['complete_file'] = os.path.basename(complete_path) if complete_path else None
        
        logger.info(f"💾 DUAL CONFIG salvate per {device_name}_{slave_address}:")
        logger.info(f"   📊 Essential: {'✅' if results['essential_saved'] else '❌'}")
        logger.info(f"   🔧 Complete: {'✅' if results['complete_saved'] else '❌'}")
        
        return results
        
    except Exception as e:
        logger.error(f"❌ Errore salvataggio dual configs: {e}")
        return {
            'essential_saved': False,
            'complete_saved': False,
            'essential_file': None,
            'complete_file': None
        }

def get_config_filename_for_device(device_id):
    """
    Mappa un device_id al nome del file di configurazione corretto
    
    Args:
        device_id (str): ID dispositivo (es: "mx_197", "dixell_045")
    
    Returns:
        str: Nome file configurazione (es: "mx_197.json")
    """
    # Se il device_id ha il formato corretto, usa quello
    if '_' in device_id and not device_id.startswith('device_'):
        return f"{device_id}.json"
    
    # Fallback: cerca nei dispositivi connessi
    for connected_device_id, device_data in config_service.connected_devices.items():
        if connected_device_id == device_id:
            device_name = device_data.get('device_type', 'unknown')
            slave_address = device_data.get('slave_address', 0)
            return f"{device_name}_{slave_address}.json"
    
    # Ultimo fallback
    return f"{device_id}.json"

def get_complete_config_filename_for_device(device_id):
    """
    Mappa un device_id al nome del file di configurazione COMPLETA
    
    Args:
        device_id (str): ID dispositivo (es: "mx_197", "dixell_045")
    
    Returns:
        str: Nome file configurazione completa (es: "mx_197_complete.json")
    """
    # Se il device_id ha il formato corretto, usa quello
    if '_' in device_id and not device_id.startswith('device_'):
        return f"{device_id}_complete.json"
    
    # Fallback: cerca nei dispositivi connessi
    for connected_device_id, device_data in config_service.connected_devices.items():
        if connected_device_id == device_id:
            device_name = device_data.get('device_type', 'unknown')
            slave_address = device_data.get('slave_address', 0)
            return f"{device_name}_{slave_address}_complete.json"
    
    # Ultimo fallback
    return f"{device_id}_complete.json"

# ===================== ROUTES ESISTENTI =====================

@app.route('/send_config', methods=['POST'])
def send_config_endpoint():
    """API per inviare configurazione - AGGIORNATA PER USARE templates/json"""
    try:
        data = request.get_json()
        device_id = data.get('device_id')
        config_file = data.get('config_file')
        
        if not device_id or not config_file:
            return jsonify({'error': 'device_id and config_file required'}), 400
        
        # ✅ CORREZIONE: Usa directory corretta
        config_path = os.path.join(config_service.json_configs_dir, config_file)
        if not os.path.exists(config_path):
            return jsonify({'error': f'Config file {config_file} not found in templates/json'}), 404
        
        with open(config_path, 'r') as f:
            config_data = json.load(f)
        
        # Invia a Kafka (compressione automatica)
        success = config_service.send_to_kafka(device_id, config_data)
        
        if success:
            return jsonify({
                'message': f'Config sent for device {device_id}',
                'total_registers': config_data['metadata']['total_registers'],
                'total_commands': config_data['metadata'].get('total_commands', 0),
                'flow': 'Config-Service → Kafka → Bridge → MQTT → ESP32'
            }), 200
        else:
            return jsonify({'error': 'Failed to send config'}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@app.route('/api/available_templates', methods=['GET'])
def get_available_templates_endpoint():
    """API per ottenere template disponibili"""
    try:
        import sys
        sys.path.append('/app/parser')
        import xml_parser
        
        templates = xml_parser.get_available_templates()
        
        return jsonify({
            'success': True,
            'templates': list(templates.keys()),
            'count': len(templates)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'templates': [],
            'count': 0
        }), 500

@app.route('/configs', methods=['GET'])
def list_configs():
    """Lista configurazioni disponibili - AGGIORNATA PER templates/json"""
    try:
        # ✅ CORREZIONE: Usa directory corretta
        configs_dir = config_service.json_configs_dir
        if os.path.exists(configs_dir):
            files = [f for f in os.listdir(configs_dir) if f.endswith('.json')]
            configs_info = []
            
            for f in files:
                try:
                    with open(os.path.join(configs_dir, f), 'r') as file:
                        data = json.load(file)
                        info = {
                            'filename': f,
                            'device': data['metadata'].get('device', 'unknown'),
                            'total_registers': data['metadata'].get('total_registers', 0),
                            'total_commands': data['metadata'].get('total_commands', 0),
                            'slave_address': data['metadata'].get('slave_address', 0),
                            'config_type': 'complete' if f.endswith('_complete.json') else 'essential'
                        }
                        configs_info.append(info)
                except:
                    configs_info.append({'filename': f, 'error': 'Cannot read file'})
            
            return jsonify({'configs': configs_info}), 200
        else:
            return jsonify({'configs': []}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ===================== 🆕 NUOVE API ROUTES PER SCRITTURA MODBUS =====================

@app.route('/api/device/<device_id>/write_register', methods=['POST'])
def write_register_endpoint(device_id):
    """🆕 NUOVO: API per scrivere un registro Modbus"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Payload JSON richiesto'
            }), 400
        
        # Valida payload
        is_valid, error_msg = config_service.validate_write_register_payload(data)
        if not is_valid:
            return jsonify({
                'success': False,
                'error': f'Validazione fallita: {error_msg}'
            }), 400
        
        # Prepara comando
        command_data = {
            'address': int(data['address']),
            'value': int(data['value']),
            'register_name': data.get('register_name', f"Reg{data['address']}"),
            'source': 'dashboard_api'
        }
        
        # Invia comando via Kafka
        success = config_service.send_write_command_to_kafka(
            device_id, 'write_register', command_data
        )
        
        if success:
            logger.info(f"✅ Comando write_register inviato per {device_id}: addr={command_data['address']}, val={command_data['value']}")
            return jsonify({
                'success': True,
                'message': f'Comando scrittura registro inviato',
                'device_id': device_id,
                'command': command_data,
                'flow': 'Dashboard → Config-Service → Kafka → Bridge → MQTT → ESP32'
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': 'Errore invio comando a Kafka'
            }), 500
            
    except Exception as e:
        logger.error(f"❌ Errore write_register per {device_id}: {e}")
        return jsonify({
            'success': False,
            'error': f'Errore interno: {str(e)}'
        }), 500

@app.route('/api/device/<device_id>/write_coil', methods=['POST'])
def write_coil_endpoint(device_id):
    """🆕 NUOVO: API per scrivere un coil Modbus"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Payload JSON richiesto'
            }), 400
        
        # Valida payload
        is_valid, error_msg = config_service.validate_write_coil_payload(data)
        if not is_valid:
            return jsonify({
                'success': False,
                'error': f'Validazione fallita: {error_msg}'
            }), 400
        
        # Prepara comando
        command_data = {
            'address': int(data['address']),
            'value': int(data['value']),
            'coil_name': data.get('coil_name', f"Coil{data['address']}"),
            'source': 'dashboard_api'
        }
        
        # Invia comando via Kafka
        success = config_service.send_write_command_to_kafka(
            device_id, 'write_coil', command_data
        )
        
        if success:
            logger.info(f"✅ Comando write_coil inviato per {device_id}: addr={command_data['address']}, val={command_data['value']}")
            return jsonify({
                'success': True,
                'message': f'Comando scrittura coil inviato',
                'device_id': device_id,
                'command': command_data,
                'flow': 'Dashboard → Config-Service → Kafka → Bridge → MQTT → ESP32'
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': 'Errore invio comando a Kafka'
            }), 500
            
    except Exception as e:
        logger.error(f"❌ Errore write_coil per {device_id}: {e}")
        return jsonify({
            'success': False,
            'error': f'Errore interno: {str(e)}'
        }), 500

@app.route('/api/device/<device_id>/send_command', methods=['POST'])
def send_command_endpoint(device_id):
    """🆕 NUOVO: API per inviare comando predefinito"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Payload JSON richiesto'
            }), 400
        
        # Valida payload
        is_valid, error_msg = config_service.validate_send_command_payload(data)
        if not is_valid:
            return jsonify({
                'success': False,
                'error': f'Validazione fallita: {error_msg}'
            }), 400
        
        # Prepara comando
        command_data = {
            'command_name': data['command_name'].strip(),
            'address': int(data['address']),
            'value_command': int(data['value_command']),
            'alias': data.get('alias', ''),
            'description': data.get('description', ''),
            'source': 'dashboard_api'
        }
        
        # Invia comando via Kafka
        success = config_service.send_write_command_to_kafka(
            device_id, 'send_command', command_data
        )
        
        if success:
            logger.info(f"✅ Comando predefinito inviato per {device_id}: {command_data['command_name']} (addr={command_data['address']}, val={command_data['value_command']})")
            return jsonify({
                'success': True,
                'message': f'Comando {command_data["command_name"]} inviato',
                'device_id': device_id,
                'command': command_data,
                'flow': 'Dashboard → Config-Service → Kafka → Bridge → MQTT → ESP32'
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': 'Errore invio comando a Kafka'
            }), 500
            
    except Exception as e:
        logger.error(f"❌ Errore send_command per {device_id}: {e}")
        return jsonify({
            'success': False,
            'error': f'Errore interno: {str(e)}'
        }), 500

# ===================== ROUTES DASHBOARD ESISTENTI =====================

@app.route('/')
def dashboard():
    """Dashboard principale"""
    try:
        with open('/app/static/dashboard.html', 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return '''
        <h1>Dashboard Non Trovata</h1>
        <p>File dashboard.html non trovato in /app/static/</p>
        <p>Assicurati di aver copiato il file nella cartella static/</p>
        ''', 404

@app.route('/api/broker/start', methods=['POST'])
def start_broker():
    """API per avviare il broker MQTT"""
    try:
        success = config_service.start_mqtt_broker()
        if success:
            return jsonify({
                'success': True,
                'message': 'Broker MQTT avviato con successo',
                'status': 'online'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Impossibile avviare il broker MQTT'
            }), 500
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Errore avvio broker: {str(e)}'
        }), 500

@app.route('/api/broker/stop', methods=['POST'])
def stop_broker():
    """API per fermare il broker MQTT"""
    try:
        success = config_service.stop_mqtt_broker()
        if success:
            return jsonify({
                'success': True,
                'message': 'Broker MQTT fermato',
                'status': 'offline'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Impossibile fermare il broker MQTT'
            }), 500
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Errore stop broker: {str(e)}'
        }), 500

@app.route('/api/broker/status', methods=['GET'])
def broker_status():
    """API per ottenere stato del broker"""
    try:
        is_running = config_service.get_broker_status()
        return jsonify({
            'running': is_running,
            'status': 'online' if is_running else 'offline',
            'uptime': time.time() - config_service.start_time if is_running else 0
        })
    except Exception as e:
        return jsonify({
            'running': False,
            'status': 'error',
            'error': str(e)
        }), 500

@app.route('/api/devices', methods=['GET'])
def get_devices():
    """API per ottenere lista dispositivi connessi - VERSIONE AGGIORNATA"""
    try:
        # Cleanup dispositivi vecchi
        config_service.cleanup_old_devices()
        
        devices_list = []
        for device_id, device_data in config_service.connected_devices.items():
            # Calcola tempo dall'ultimo messaggio
            last_seen_seconds = time.time() - device_data['last_seen']
            
            devices_list.append({
                'device_id': device_id,
                'device_type': device_data['device_type'],
                'slave_address': device_data['slave_address'],
                'total_registers': device_data['total_registers'],
                'wifi_rssi': device_data['wifi_rssi'],
                'status': 'online' if last_seen_seconds < 60 else 'offline',
                'last_seen': device_data['last_seen'],
                'last_seen_seconds': int(last_seen_seconds),
                'uptime_seconds': device_data['uptime_seconds'],
                'free_heap_bytes': device_data['free_heap_bytes'],
                'config_loaded': device_data['config_loaded']
            })
        
        return jsonify({
            'devices': devices_list,
            'total_count': len(devices_list),
            'online_count': len([d for d in devices_list if d['status'] == 'online']),
            'message_count': config_service.message_count,
            'pending_devices': len(config_service.pending_devices)  # ✅ NUOVO
        })
    except Exception as e:
        return jsonify({
            'devices': [],
            'total_count': 0,
            'online_count': 0,
            'message_count': 0,
            'pending_devices': 0,
            'error': str(e)
        }), 500

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """API per statistiche generali"""
    try:
        return jsonify({
            'broker_running': config_service.broker_running,
            'total_devices': len(config_service.connected_devices),
            'online_devices': len([d for d in config_service.connected_devices.values() 
                                 if time.time() - d['last_seen'] < 60]),
            'total_messages': config_service.message_count,
            'uptime_seconds': time.time() - config_service.start_time,
            'pending_devices': len(config_service.pending_devices)  # ✅ NUOVO
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ===================== NUOVE API ROUTES =====================

@app.route('/api/pending_devices', methods=['GET'])
def get_pending_devices():
    """API per ottenere dispositivi in attesa di configurazione"""
    try:
        # Cleanup dispositivi vecchi
        config_service.cleanup_old_devices()
        
        devices_list = []
        for device_id, device_data in config_service.pending_devices.items():
            last_seen_seconds = time.time() - device_data['last_seen']
            
            devices_list.append({
                'device_id': device_id,
                'status': device_data['status'],
                'detected_at': device_data['detected_at'],
                'last_seen': device_data['last_seen'],
                'minutes_ago': int(last_seen_seconds / 60),
                'device_type': device_data.get('device_type', 'unknown'),
                'free_heap_bytes': device_data.get('free_heap_bytes', 0),
                'wifi_rssi': device_data.get('wifi_rssi', -99),
                'uptime_seconds': device_data.get('uptime_seconds', 0)
            })
        
        return jsonify({
            'success': True,
            'devices': devices_list,
            'count': len(devices_list)
        })
        
    except Exception as e:
        logger.error(f"Errore get_pending_devices: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/configured_devices', methods=['GET'])
def get_configured_devices():
    """API per ottenere dispositivi configurati (alias per /api/devices)"""
    try:
        # Cleanup dispositivi vecchi
        config_service.cleanup_old_devices()
        
        devices_list = []
        for device_id, device_data in config_service.connected_devices.items():
            last_seen_seconds = time.time() - device_data['last_seen']
            
            devices_list.append({
                'device_id': device_id,
                'device_type': device_data['device_type'],
                'slave_address': device_data['slave_address'],
                'total_registers': device_data['total_registers'],
                'wifi_rssi': device_data['wifi_rssi'],
                'status': 'online' if last_seen_seconds < 60 else 'offline',
                'last_seen': device_data['last_seen'],
                'minutes_ago': int(last_seen_seconds / 60),
                'uptime_seconds': device_data['uptime_seconds'],
                'free_heap_bytes': device_data['free_heap_bytes'],
                'config_loaded': device_data['config_loaded']
            })
        
        return jsonify({
            'success': True,
            'devices': devices_list,
            'count': len(devices_list)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/dashboard_stats', methods=['GET'])
def get_dashboard_stats():
    """API per statistiche dashboard"""
    try:
        uptime_seconds = time.time() - config_service.start_time
        
        return jsonify({
            'success': True,
            'stats': {
                'pending_count': len(config_service.pending_devices),
                'configured_count': len(config_service.connected_devices),
                'total_messages': config_service.message_count,
                'uptime_seconds': int(uptime_seconds),
                'broker_running': config_service.broker_running,
                'broker_start_time': config_service.start_time
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# 🆕 AGGIORNATO: Endpoint principale con DUAL CONFIG GENERATION
@app.route('/api/generate_and_send_config', methods=['POST'])
def generate_and_send_config():
    """Genera configurazioni DUAL dinamiche e le salva + invia essential via Kafka"""
    try:
        data = request.get_json()
        device_id = data['device_id']
        template = data['template']  # 'mx' o 'dixell'
        device_name = data['device_name']
        slave_address = int(data['slave_address'])
        baud_rate = int(data['baud_rate'])
        
        logger.info(f"🔄 Generando configurazioni DUAL per {device_id}")
        logger.info(f"   Template: {template}")
        logger.info(f"   Nome: {device_name}")
        logger.info(f"   Slave: {slave_address}")
        logger.info(f"   Baud: {baud_rate}")
        
        # 1. Genera ENTRAMBE le configurazioni
        logger.info("📊 Generando configurazione ESSENZIALE...")
        essential_config = generate_config_dynamic(
            template=template,
            device_name=device_name,
            slave_address=slave_address,
            baud_rate=baud_rate
        )
        
        logger.info("🔧 Generando configurazione COMPLETA...")
        complete_config = generate_config_complete(
            template=template,
            device_name=device_name,
            slave_address=slave_address,
            baud_rate=baud_rate
        )
        
        logger.info(f"✅ Configurazioni DUAL generate:")
        logger.info(f"   📊 Essential: {essential_config['metadata']['total_registers']} registri, {essential_config['metadata'].get('total_commands', 0)} comandi")
        logger.info(f"   🔧 Complete: {complete_config['metadata']['total_registers']} registri, {complete_config['metadata'].get('total_commands', 0)} comandi")
        
        # 2. 💾 NUOVO: Salva ENTRAMBE le configurazioni in /app/templates/json PERSISTENTE
        dual_save_results = save_dual_configs_to_templates(
            essential_config, complete_config, device_name, slave_address
        )
        
        # 3. Invia SOLO la configurazione essenziale all'ESP32 via Kafka
        success = config_service.send_to_kafka(device_id, essential_config)
        
        if success:
            # 4. Rimuovi da pending devices
            if device_id in config_service.pending_devices:
                del config_service.pending_devices[device_id]
                logger.info(f"🗑  Rimosso {device_id} da dispositivi pending")
            
            response_data = {
                "success": True,
                "message": f"Configurazioni DUAL generate e salvate per {device_id}",
                "essential_config": {
                    "size": len(json.dumps(essential_config, separators=(',', ':'))),
                    "registers_count": essential_config['metadata']['total_registers'],
                    "commands_count": essential_config['metadata'].get('total_commands', 0),
                    "saved_file": dual_save_results['essential_file'],
                    "saved": dual_save_results['essential_saved'],
                    "sent_to_esp32": True
                },
                "complete_config": {
                    "size": len(json.dumps(complete_config, separators=(',', ':'))),
                    "registers_count": complete_config['metadata']['total_registers'],
                    "commands_count": complete_config['metadata'].get('total_commands', 0),
                    "saved_file": dual_save_results['complete_file'],
                    "saved": dual_save_results['complete_saved'],
                    "for_dashboard": True
                },
                "expected_new_id": f"{device_name}_{slave_address}",
                "flow": "Dashboard → Config-Service → [Essential→ESP32 via MQTT] + [Complete→Disk for Enrichment]"
            }
            
            logger.info(f"💾 Configurazioni DUAL salvate:")
            logger.info(f"   📊 Essential: {dual_save_results['essential_file'] or 'ERRORE'}")
            logger.info(f"   🔧 Complete: {dual_save_results['complete_file'] or 'ERRORE'}")
            
            return jsonify(response_data)
        else:
            return jsonify({"success": False, "error": "Errore invio configurazione essenziale a Kafka"}), 500
        
    except Exception as e:
        logger.error(f"❌ Errore generazione configurazioni DUAL: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

# ✅ NUOVO: Endpoint per lettura registri dispositivi
@app.route('/api/device/<device_id>/registers', methods=['GET'])
def get_device_registers_endpoint(device_id):
    """API per ottenere ultima lettura registri di un dispositivo"""
    try:
        logger.info(f"📊 Richiesta registri per dispositivo: {device_id}")
        
        # Ottieni ultima lettura registri dalla cache
        registers_data = config_service.get_device_registers(device_id)
        
        if registers_data is None:
            logger.warning(f"⚠ Nessun registro trovato per {device_id}")
            return jsonify({
                'success': False,
                'error': f'Nessuna lettura disponibile per il dispositivo {device_id}',
                'device_id': device_id,
                'registers': None
            }), 404
        
        logger.info(f"✅ Registri trovati per {device_id}: {len(registers_data.get('registers', []))} registri")
        
        return jsonify({
            'success': True,
            'device_id': device_id,
            'timestamp': registers_data.get('timestamp'),
            'timestamp_ms': registers_data.get('timestamp_ms'),
            'registers': {
                'device_id': registers_data.get('device_id'),
                'slave_address': registers_data.get('slave_address'),
                'registers': registers_data.get('registers', [])
            }
        })
        
    except Exception as e:
        logger.error(f"❌ Errore get_device_registers per {device_id}: {e}")
        return jsonify({
            'success': False,
            'error': f'Errore interno: {str(e)}',
            'device_id': device_id,
            'registers': None
        }), 500

# ✅ NUOVO: Endpoint per ottenere configurazione dispositivo - VERSIONE DUAL PERSISTENTE
@app.route('/api/device/<device_id>/configuration', methods=['GET'])
def get_device_configuration(device_id):
    """API per ottenere configurazione registri di un dispositivo - DA PERSISTENT STORAGE DUAL"""
    try:
        # Parametro per specificare il tipo di configurazione
        config_type = request.args.get('type', 'essential')  # essential o complete
        
        logger.info(f"⚙ Richiesta configurazione {config_type.upper()} per dispositivo: {device_id}")
        
        if config_type == 'complete':
            # Configurazione COMPLETA per enrichment dashboard
            
            # 1. Cerca prima nella cache completa in memoria
            if device_id in config_service.complete_config_cache:
                config_data = config_service.complete_config_cache[device_id]
                logger.info(f"✅ Configurazione COMPLETA trovata in cache per {device_id}")
                
                return jsonify({
                    'success': True,
                    'device_id': device_id,
                    'configuration': {
                        'metadata': config_data.get('metadata', {}),
                        'holding_registers': config_data.get('holding_registers', []),
                        'coils': config_data.get('coils', []),
                        'commands': config_data.get('commands', [])  # 🆕 COMMANDS
                    },
                    'source': 'memory_cache',
                    'storage_type': 'persistent',
                    'config_type': 'complete'
                })
            
            # 2. Cerca direttamente su disco (file completo)
            complete_config_filename = get_complete_config_filename_for_device(device_id)
            complete_config_filepath = os.path.join(config_service.json_configs_dir, complete_config_filename)
            
            if os.path.exists(complete_config_filepath):
                try:
                    with open(complete_config_filepath, 'r', encoding='utf-8') as f:
                        config_data = json.load(f)
                    
                    # Aggiorna cache completa
                    config_service.complete_config_cache[device_id] = config_data
                    
                    logger.info(f"✅ Configurazione COMPLETA caricata da disco per {device_id}")
                    
                    return jsonify({
                        'success': True,
                        'device_id': device_id,
                        'configuration': {
                            'metadata': config_data.get('metadata', {}),
                            'holding_registers': config_data.get('holding_registers', []),
                            'coils': config_data.get('coils', []),
                            'commands': config_data.get('commands', [])  # 🆕 COMMANDS
                        },
                        'source': complete_config_filename,
                        'storage_type': 'persistent_disk',
                        'config_type': 'complete'
                    })
                    
                except Exception as e:
                    logger.error(f"❌ Errore lettura config completa {complete_config_filename}: {e}")
            
        else:
            # Configurazione ESSENZIALE (comportamento originale)
            
            # 1. Cerca prima nella cache essenziale in memoria
            if device_id in config_service.config_cache:
                config_data = config_service.config_cache[device_id]
                logger.info(f"✅ Configurazione ESSENZIALE trovata in cache per {device_id}")
                
                return jsonify({
                    'success': True,
                    'device_id': device_id,
                    'configuration': {
                        'metadata': config_data.get('metadata', {}),
                        'holding_registers': config_data.get('holding_registers', []),
                        'coils': config_data.get('coils', []),
                        'commands': config_data.get('commands', [])  # 🆕 COMMANDS
                    },
                    'source': 'memory_cache',
                    'storage_type': 'persistent',
                    'config_type': 'essential'
                })
            
            # 2. Cerca direttamente su disco (file essenziale)
            config_filename = get_config_filename_for_device(device_id)
            config_filepath = os.path.join(config_service.json_configs_dir, config_filename)
            
            if os.path.exists(config_filepath):
                try:
                    with open(config_filepath, 'r', encoding='utf-8') as f:
                        config_data = json.load(f)
                    
                    # Aggiorna cache essenziale
                    config_service.config_cache[device_id] = config_data
                    
                    logger.info(f"✅ Configurazione ESSENZIALE caricata da disco per {device_id}")
                    
                    return jsonify({
                        'success': True,
                        'device_id': device_id,
                        'configuration': {
                            'metadata': config_data.get('metadata', {}),
                            'holding_registers': config_data.get('holding_registers', []),
                            'coils': config_data.get('coils', []),
                            'commands': config_data.get('commands', [])  # 🆕 COMMANDS
                        },
                        'source': config_filename,
                        'storage_type': 'persistent_disk',
                        'config_type': 'essential'
                    })
                    
                except Exception as e:
                    logger.error(f"❌ Errore lettura config essenziale {config_filename}: {e}")
        
        # 3. Fallback: scansiona tutti i file nella directory persistente
        if os.path.exists(config_service.json_configs_dir):
            logger.info(f"🔍 Fallback: scanning directory persistente {config_service.json_configs_dir}")
            
            # Cerca il tipo di file appropriato
            target_suffix = '_complete.json' if config_type == 'complete' else '.json'
            exclude_suffix = '.json' if config_type == 'complete' else '_complete.json'
            
            for filename in os.listdir(config_service.json_configs_dir):
                if filename.endswith(target_suffix) and not filename.endswith(exclude_suffix):
                    try:
                        filepath = os.path.join(config_service.json_configs_dir, filename)
                        with open(filepath, 'r', encoding='utf-8') as f:
                            config_data = json.load(f)
                        
                        # Controlla se questa configurazione corrisponde al dispositivo
                        metadata = config_data.get('metadata', {})
                        config_device_name = metadata.get('device', '')
                        config_slave_address = metadata.get('slave_address', 0)
                        
                        # Controlla corrispondenza: mx_197 → device=mx, slave=197
                        expected_device_id = f"{config_device_name}_{config_slave_address}"
                        
                        if device_id == expected_device_id or device_id.endswith(f"_{config_slave_address}"):
                            logger.info(f"✅ Configurazione {config_type.upper()} match trovata per {device_id} in {filename}")
                            
                            # Aggiorna cache appropriata
                            if config_type == 'complete':
                                config_service.complete_config_cache[device_id] = config_data
                            else:
                                config_service.config_cache[device_id] = config_data
                            
                            return jsonify({
                                'success': True,
                                'device_id': device_id,
                                'configuration': {
                                    'metadata': metadata,
                                    'holding_registers': config_data.get('holding_registers', []),
                                    'coils': config_data.get('coils', []),
                                    'commands': config_data.get('commands', [])  # 🆕 COMMANDS
                                },
                                'source': filename,
                                'match_method': 'directory_scan',
                                'storage_type': 'persistent_disk',
                                'config_type': config_type
                            })
                            
                    except Exception as e:
                        logger.error(f"❌ Errore lettura config {filename}: {e}")
                        continue
        
        logger.warning(f"⚠ Nessuna configurazione {config_type.upper()} PERSISTENTE trovata per {device_id}")
        return jsonify({
            'success': False,
            'error': f'Configurazione {config_type} non trovata per il dispositivo {device_id}',
            'device_id': device_id,
            'searched_file': complete_config_filename if config_type == 'complete' else config_filename,
            'searched_directory': config_service.json_configs_dir,
            'storage_type': 'persistent',
            'config_type': config_type,
            'suggestion': 'Riapplica la configurazione dalla dashboard'
        }), 404
        
    except Exception as e:
        logger.error(f"❌ Errore get_device_configuration per {device_id}: {e}")
        return jsonify({
            'success': False,
            'error': f'Errore interno: {str(e)}',
            'device_id': device_id,
            'configuration': None
        }), 500

# 💾 NUOVO: API per gestione configurazioni persistenti DUAL
@app.route('/api/persistent_configs', methods=['GET'])
def get_persistent_configs():
    """API per ottenere lista configurazioni PERSISTENTI DUAL"""
    try:
        configs_list = []
        essential_configs = []
        complete_configs = []
        
        # Scansiona directory persistente
        if os.path.exists(config_service.json_configs_dir):
            for filename in os.listdir(config_service.json_configs_dir):
                if filename.endswith('.json'):
                    try:
                        filepath = os.path.join(config_service.json_configs_dir, filename)
                        with open(filepath, 'r', encoding='utf-8') as f:
                            config_data = json.load(f)
                        
                        metadata = config_data.get('metadata', {})
                        config_info = {
                            'filename': filename,
                            'device': metadata.get('device', 'unknown'),
                            'slave_address': metadata.get('slave_address', 0),
                            'total_registers': metadata.get('total_registers', 0),
                            'total_commands': metadata.get('total_commands', 0),  # 🆕 COMMANDS
                            'template_id': metadata.get('template_id', ''),
                            'baud_rate': metadata.get('baud_rate', 0),
                            'saved_at': metadata.get('saved_at', ''),
                            'file_size': os.path.getsize(filepath),
                            'version': metadata.get('version', '1.0')
                        }
                        
                        # Classifica per tipo
                        if filename.endswith('_complete.json'):
                            config_info['config_type'] = 'complete'
                            complete_configs.append(config_info)
                        else:
                            config_info['config_type'] = 'essential'
                            essential_configs.append(config_info)
                        
                        configs_list.append(config_info)
                        
                    except Exception as e:
                        logger.error(f"Errore lettura {filename}: {e}")
                        configs_list.append({
                            'filename': filename,
                            'error': f'Errore lettura: {str(e)}'
                        })
        
        return jsonify({
            'success': True,
            'configs': configs_list,
            'count': len(configs_list),
            'essential_configs': essential_configs,
            'complete_configs': complete_configs,
            'essential_count': len(essential_configs),
            'complete_count': len(complete_configs),
            'directory': config_service.json_configs_dir,
            'storage_type': 'persistent',
            'note': 'Configurazioni DUAL persistenti: Essential (ESP32) + Complete (Dashboard Enrichment + Commands)'
        })
        
    except Exception as e:
        logger.error(f"Errore get_persistent_configs: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'configs': [],
            'count': 0
        }), 500

# ✅ NUOVO: Alias per compatibilità
@app.route('/api/available_configs', methods=['GET'])
def get_available_configs():
    """API alias per get_persistent_configs"""
    return get_persistent_configs()

@app.route('/api/reload_configs', methods=['POST'])
def reload_configs():
    """Ricarica tutte le configurazioni da disco"""
    try:
        loaded_count = config_service.load_configs_from_disk()
        return jsonify({
            'success': True,
            'message': f'Ricaricate {loaded_count} configurazioni da disco',
            'configs_loaded': loaded_count,
            'essential_cached': len(config_service.config_cache),
            'complete_cached': len(config_service.complete_config_cache)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Errore ricaricamento configs: {str(e)}'
        }), 500

# 💾 NUOVO: Download configurazioni
@app.route('/download/<path:filename>')
def download_file(filename):
    """Download file di configurazione JSON"""
    try:
        return send_from_directory(config_service.json_configs_dir, filename, as_attachment=True)
    except FileNotFoundError:
        return "File not found", 404

# ===================== HEALTH CHECK =====================

@app.route('/health', methods=['GET'])
def health():
    kafka_status = "connected" if config_service.producer else "disconnected"
    broker_status = "running" if config_service.broker_running else "stopped"
    
    # 💾 Verifica directory persistente
    persistent_exists = os.path.exists(config_service.json_configs_dir)
    persistent_writable = os.access(config_service.json_configs_dir, os.W_OK) if persistent_exists else False
    
    return jsonify({
        'status': 'OK', 
        'service': 'config-service-dual-persistent-storage-with-commands',
        'kafka': kafka_status,
        'mqtt_broker': broker_status,
        'connected_devices': len(config_service.connected_devices),
        'pending_devices': len(config_service.pending_devices),
        'cached_registers': len(config_service.device_registers),
        'persistent_storage': {
            'exists': persistent_exists,
            'writable': persistent_writable,
            'path': config_service.json_configs_dir,
            'essential_configs_cached': len(config_service.config_cache),
            'complete_configs_cached': len(config_service.complete_config_cache),
            'note': 'DUAL Persistent storage: Essential (ESP32) + Complete (Dashboard Enrichment + Commands)'
        },
        'features': [
            'dashboard', 'broker_control', 'device_monitoring', 'dynamic_config', 
            'registers_cache', 'dual_persistent_config_storage', 'dashboard_enrichment',
            'modbus_write_commands', 'write_registers', 'write_coils', 'send_commands'  # 🆕 COMMANDS
        ]
    }), 200

# ===================== MAIN =====================

if __name__ == '__main__':
    logger.info("🚀 Config Service con DUAL PERSISTENT STORAGE + COMMANDS COMPLETO")
    logger.info("✅ Funzionalità disponibili:")
    logger.info("   📊 Dashboard dispositivi")
    logger.info("   🔧 Controllo broker MQTT")
    logger.info("   📱 Monitoraggio dispositivi pending")
    logger.info("   ⚙  Configurazione dinamica DUAL")
    logger.info("   📊 Cache registri dispositivi")
    logger.info("   💾 DUAL PERSISTENT STORAGE in templates/json")
    logger.info("   📥 Download configurazioni JSON")
    logger.info("   🔄 Auto-reload configurazioni da disco")
    logger.info("   🚀 Integrazione Kafka/MQTT Bridge")
    logger.info("   🆕 DASHBOARD ENRICHMENT con configurazioni complete")
    logger.info("   🎮 SCRITTURA MODBUS: write_register, write_coil, send_command")
    logger.info("   📡 COMANDI VIA KAFKA: device.write.register, device.write.coil, device.write.command")
    
    logger.info(f"💾 Directory persistente: {config_service.json_configs_dir}")
    logger.info(f"📊 Configurazioni ESSENZIALI caricate: {len(config_service.config_cache)}")
    logger.info(f"🔧 Configurazioni COMPLETE caricate: {len(config_service.complete_config_cache)}")
    
    app.run(host='0.0.0.0', port=8080, debug=True)
