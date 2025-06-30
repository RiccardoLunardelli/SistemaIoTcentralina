#!/usr/bin/env python3
"""
Kafka-MQTT Bridge Personalizzato - VERSIONE ENHANCED CON SCRITTURA MODBUS CORRETTA
Kafka → MQTT: Configurazioni (con compressione JSON) + Comandi Scrittura
MQTT → Kafka: Dati ESP32 + Feedback Scrittura
+ 🆕 CORRETTO: Supporto completo scrittura Modbus (write_register, write_coil, send_command)
+ 🔧 CORRETTO: Topic mapping Config Service → ESP32
"""

import json
import logging
import time
import signal
import sys
from kafka import KafkaConsumer, KafkaProducer
import paho.mqtt.client as mqtt

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class KafkaMQTTBridge:
    def __init__(self):
        # Componenti
        self.mqtt_client = None
        self.kafka_consumer = None
        self.kafka_producer = None
        self.running = True
        
        # Stats
        self.stats = {
            'kafka_to_mqtt': 0,
            'mqtt_to_kafka': 0,
            'write_commands_sent': 0,  # 🆕 NUOVO: Contatore comandi scrittura
            'write_responses_received': 0,  # 🆕 NUOVO: Contatore risposte scrittura
            'errors': 0,
            'start_time': time.time()
        }
        
        # Gestione segnali
        signal.signal(signal.SIGTERM, self.signal_handler)
        signal.signal(signal.SIGINT, self.signal_handler)
        
    def signal_handler(self, signum, frame):
        logger.info(f"🛑 Ricevuto segnale {signum}, arresto...")
        self.running = False
    
    def connect_mqtt(self, host="mosquitto", port=1883):
        """Connetti a MQTT"""
        try:
            self.mqtt_client = mqtt.Client(client_id="kafka_mqtt_bridge_enhanced")
            self.mqtt_client.on_connect = self.on_mqtt_connect
            self.mqtt_client.on_message = self.on_mqtt_message
            
            logger.info(f"🔗 Connessione a MQTT: {host}:{port}")
            self.mqtt_client.connect(host, port, 60)
            self.mqtt_client.loop_start()
            
            # Aspetta connessione
            time.sleep(2)
            return True
        except Exception as e:
            logger.error(f"❌ Errore connessione MQTT: {e}")
            return False
    
    def connect_kafka(self, bootstrap_servers=['kafka:29092']):
        """Connetti a Kafka"""
        try:
            logger.info(f"🔗 Connessione a Kafka: {bootstrap_servers}")
            
            # 🔧 CORREZIONE FINALE: Topic corretti dal Config Service
            kafka_topics = [
                'device.config',           # Configurazioni esistenti
                'device.write.command',    # 🆕 CORRETTO: Tutti i comandi (register, coil, command)
            ]
            
            self.kafka_consumer = KafkaConsumer(
                *kafka_topics,
                bootstrap_servers=bootstrap_servers,
                value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                key_deserializer=lambda m: m.decode('utf-8') if m else None,
                group_id='mqtt-bridge-enhanced',
                auto_offset_reset='latest',
                consumer_timeout_ms=1000
            )
            
            # Producer per dati ESP32 + feedback scrittura
            self.kafka_producer = KafkaProducer(
                bootstrap_servers=bootstrap_servers,
                value_serializer=lambda v: json.dumps(v, separators=(',', ':')).encode('utf-8'),
                key_serializer=lambda k: k.encode('utf-8') if k else None,
                acks='all',
                retries=3
            )
            
            logger.info("✅ Connesso a Kafka")
            logger.info(f"📡 Kafka Topics monitored: {kafka_topics}")
            return True
        except Exception as e:
            logger.error(f"❌ Errore connessione Kafka: {e}")
            return False
    
    def on_mqtt_connect(self, client, userdata, flags, rc):
        """Callback connessione MQTT"""
        if rc == 0:
            logger.info("✅ Connesso a MQTT broker")
            
            # Sottoscrivi ai dati ESP32 (esistenti)
            client.subscribe("device/data/+/registers")
            client.subscribe("device/data/+/status")
            client.subscribe("device/data/+/errors")
            
            # 🆕 NUOVO: Sottoscrivi ai feedback di scrittura
            client.subscribe("device/write/+/response")
            client.subscribe("device/write/+/error")
            
            logger.info("📡 Sottoscritto ai topic dati ESP32 + feedback scrittura")
        else:
            logger.error(f"❌ Errore connessione MQTT: {rc}")
    
    def on_mqtt_message(self, client, userdata, msg):
        """MQTT → Kafka: Dati ESP32 + Feedback Scrittura"""
        try:
            topic = msg.topic
            payload = msg.payload.decode('utf-8')
            
            # Parse topic: device/data/{device_id}/{type} O device/write/{device_id}/{type}
            topic_parts = topic.split('/')
            if len(topic_parts) < 4:
                return
                
            topic_category = topic_parts[1]  # 'data' o 'write'
            device_id = topic_parts[2]
            message_type = topic_parts[3]
            
            # Parse JSON
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                logger.error(f"❌ JSON non valido da {device_id}")
                return
            
            if topic_category == 'data':
                # 📊 ESISTENTE: Dati normali ESP32
                # Mappa a topic Kafka
                kafka_topic_map = {
                    'registers': 'device.data.registers',
                    'status': 'device.data.status',
                    'errors': 'device.data.errors'
                }
                
                kafka_topic = kafka_topic_map.get(message_type, 'device.data.unknown')
                
                # Invia a Kafka
                future = self.kafka_producer.send(
                    kafka_topic,
                    key=device_id,
                    value=data
                )
                
                future.get(timeout=5)  # Attendi conferma
                
                self.stats['mqtt_to_kafka'] += 1
                logger.info(f"📤 MQTT→Kafka: {device_id}/{message_type} → {kafka_topic}")
                
            elif topic_category == 'write':
                # 🆕 NUOVO: Feedback scrittura Modbus
                # Mappa a topic Kafka feedback
                kafka_feedback_topic_map = {
                    'response': 'device.write.feedback.success',
                    'error': 'device.write.feedback.error'
                }
                
                kafka_topic = kafka_feedback_topic_map.get(message_type, 'device.write.feedback.unknown')
                
                # Arricchisci dati feedback
                feedback_data = {
                    'device_id': device_id,
                    'feedback_type': message_type,
                    'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                    'timestamp_ms': int(time.time() * 1000),
                    **data
                }
                
                # Invia feedback a Kafka
                future = self.kafka_producer.send(
                    kafka_topic,
                    key=device_id,
                    value=feedback_data
                )
                
                future.get(timeout=5)
                
                self.stats['write_responses_received'] += 1
                logger.info(f"📥 Feedback scrittura: {device_id}/{message_type} → {kafka_topic}")
                
                # Log dettagli feedback
                if message_type == 'response':
                    logger.info(f"✅ Scrittura completata: {device_id} - {data.get('message', 'N/A')}")
                elif message_type == 'error':
                    logger.error(f"❌ Errore scrittura: {device_id} - {data.get('error', 'N/A')}")
            
        except Exception as e:
            logger.error(f"❌ Errore MQTT→Kafka: {e}")
            self.stats['errors'] += 1
    
    def process_kafka_config(self, message):
        """Kafka → MQTT: Configurazioni (ESISTENTE)"""
        try:
            device_id = message.key if message.key else 'unknown'
            config_data = message.value
            
            logger.info(f"📦 Config ricevuta per: {device_id}")
            
            # Topic MQTT che ESP32 ascolta
            mqtt_topic = f"device/config/{device_id}/registers"
            
            # JSON compatto (già compresso dal Config Service)
            mqtt_payload = json.dumps(config_data, separators=(',', ':'), ensure_ascii=False)
            
            # Dimensione finale
            payload_size = len(mqtt_payload.encode('utf-8'))
            logger.info(f"📦 Dimensione payload: {payload_size:,} bytes ({payload_size//1024:.1f} KB)")
            
            if payload_size > 50000:  # 50KB limit
                logger.error(f"❌ Payload troppo grande: {payload_size} bytes")
                return
            
            # Pubblica su MQTT
            result = self.mqtt_client.publish(mqtt_topic, mqtt_payload, qos=1)
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                self.stats['kafka_to_mqtt'] += 1
                logger.info(f"✅ Config inviata: {mqtt_topic}")
                logger.info(f"   📊 Registri: {config_data.get('metadata', {}).get('total_registers', 'N/A')}")
                logger.info(f"   🎮 Commands: {config_data.get('metadata', {}).get('total_commands', 'N/A')}")
            else:
                logger.error(f"❌ Errore invio MQTT: {result.rc}")
                self.stats['errors'] += 1
                
        except Exception as e:
            logger.error(f"❌ Errore Kafka→MQTT config: {e}")
            self.stats['errors'] += 1
    
    def process_kafka_write_command(self, message):
        """
        🆕 CORRETTO: Kafka → MQTT: Comandi Scrittura Modbus (Config Service Format)
        """
        try:
            device_id = message.key if message.key else 'unknown'
            command_data = message.value
            
            # 🔧 CORREZIONE: Estrai command_type dal payload del Config Service
            command_type = command_data.get('command_type', 'unknown')
            
            logger.info(f"🎮 Comando {command_type} ricevuto per: {device_id}")
            logger.info(f"📦 Payload completo: {json.dumps(command_data, indent=2)}")
            
            # Estrai device_id dal payload se non presente nella key
            if device_id == 'unknown' and 'device_id' in command_data:
                device_id = command_data['device_id']
            
            # 🔧 CORREZIONE: Mapping corretto Config Service → ESP32
            if command_type == 'write_register':
                mqtt_topic = f'device/write/{device_id}/register'
            elif command_type == 'write_coil':
                mqtt_topic = f'device/write/{device_id}/coil'
            elif command_type == 'send_command':
                mqtt_topic = f'device/write/{device_id}/command'
            else:
                logger.error(f"❌ Tipo comando sconosciuto: {command_type}")
                logger.error(f"📦 Payload era: {command_data}")
                return
            
            # 🔧 CORREZIONE: Usa payload direttamente come inviato dal Config Service
            mqtt_payload = json.dumps(command_data, separators=(',', ':'), ensure_ascii=False)
            
            logger.info(f"📡 Topic MQTT: {mqtt_topic}")
            logger.info(f"📦 Payload MQTT: {mqtt_payload}")
            
            # Pubblica su MQTT
            result = self.mqtt_client.publish(mqtt_topic, mqtt_payload, qos=1)
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                self.stats['write_commands_sent'] += 1
                logger.info(f"✅ Comando {command_type} inviato: {mqtt_topic}")
                
                # Log dettagli specifici
                if command_type == 'write_register':
                    logger.info(f"   📊 Write Register: addr={command_data.get('address')}, val={command_data.get('value')}")
                elif command_type == 'write_coil':
                    logger.info(f"   🔘 Write Coil: addr={command_data.get('address')}, val={command_data.get('value')}")
                elif command_type == 'send_command':
                    logger.info(f"   🎮 Command: {command_data.get('command_name')} (addr={command_data.get('address')}, val={command_data.get('value_command')})")
                
            else:
                logger.error(f"❌ Errore invio comando MQTT: {result.rc}")
                self.stats['errors'] += 1
                
        except Exception as e:
            logger.error(f"❌ Errore Kafka→MQTT comando: {e}")
            self.stats['errors'] += 1
    
    def print_stats(self):
        """Stampa statistiche estese"""
        uptime = time.time() - self.stats['start_time']
        logger.info(f"📊 Bridge Enhanced Stats (uptime: {uptime:.0f}s):")
        logger.info(f"   📥 Kafka→MQTT (config): {self.stats['kafka_to_mqtt']}")
        logger.info(f"   📤 MQTT→Kafka (data): {self.stats['mqtt_to_kafka']}")
        logger.info(f"   🎮 Write Commands Sent: {self.stats['write_commands_sent']}")
        logger.info(f"   📨 Write Responses Received: {self.stats['write_responses_received']}")
        logger.info(f"   ❌ Errori: {self.stats['errors']}")
        
        # Calcola rate
        if uptime > 0:
            config_rate = self.stats['kafka_to_mqtt'] / uptime * 60
            data_rate = self.stats['mqtt_to_kafka'] / uptime * 60
            command_rate = self.stats['write_commands_sent'] / uptime * 60
            
            logger.info(f"   📈 Rate (per minuto): config={config_rate:.1f}, data={data_rate:.1f}, commands={command_rate:.1f}")
    
    def run(self):
        """Avvia il bridge enhanced"""
        logger.info("🚀 Avvio Kafka-MQTT Bridge Enhanced con Supporto Scrittura Modbus...")
        
        # Connetti componenti
        if not self.connect_mqtt():
            logger.error("💥 Impossibile connettersi a MQTT")
            return
        
        if not self.connect_kafka():
            logger.error("💥 Impossibile connettersi a Kafka")
            return
        
        logger.info("✅ Bridge Enhanced avviato con successo!")
        logger.info("📋 Flusso Esteso:")
        logger.info("   📥 Config: Config-Service → Kafka → Bridge → MQTT → ESP32")
        logger.info("   📤 Data: ESP32 → MQTT → Bridge → Kafka")
        logger.info("   🎮 Write: Dashboard → Config-Service → Kafka[device.write.command] → Bridge → MQTT → ESP32")
        logger.info("   📨 Feedback: ESP32 → MQTT → Bridge → Kafka")
        
        # Stats periodiche
        last_stats = time.time()
        
        try:
            while self.running:
                try:
                    # Processa messaggi Kafka
                    for message in self.kafka_consumer:
                        if not self.running:
                            break
                        
                        # Determina tipo di messaggio dal topic
                        topic = message.topic
                        
                        logger.info(f"📥 Messaggio Kafka ricevuto: topic={topic}, key={message.key}")
                        
                        if topic == 'device.config':
                            # Configurazione normale
                            self.process_kafka_config(message)
                            
                        elif topic == 'device.write.command':
                            # 🆕 CORRETTO: Tutti i comandi di scrittura dal Config Service
                            self.process_kafka_write_command(message)
                            
                        else:
                            logger.warning(f"⚠ Topic Kafka sconosciuto: {topic}")
                    
                    # Stats ogni 60 secondi
                    if time.time() - last_stats > 60:
                        self.print_stats()
                        last_stats = time.time()
                        
                except Exception as e:
                    if self.running:
                        logger.error(f"❌ Errore nel loop: {e}")
                        time.sleep(5)
                    
        except KeyboardInterrupt:
            logger.info("🛑 Interruzione da tastiera")
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Cleanup risorse"""
        logger.info("🧹 Cleanup Enhanced Bridge...")
        
        if self.mqtt_client:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
        
        if self.kafka_consumer:
            self.kafka_consumer.close()
        
        if self.kafka_producer:
            self.kafka_producer.close()
        
        # Stats finali
        self.print_stats()
        logger.info("✅ Bridge Enhanced terminato")

if __name__ == "__main__":
    logger.info("🎮 Kafka-MQTT Bridge Enhanced - Supporto Scrittura Modbus v2.0 CORRETTO")
    logger.info("🆕 Funzionalità: write_register, write_coil, send_command + feedback")
    logger.info("🔧 CORRETTO: Topic mapping Config Service → ESP32")
    
    bridge = KafkaMQTTBridge()
    bridge.run()
