#!/usr/bin/env python3
"""
Script per aspettare che Kafka sia pronto
"""
import time
import sys
from kafka import KafkaProducer
from kafka.errors import KafkaError

def wait_for_kafka(bootstrap_servers, max_retries=30):
    """Aspetta che Kafka sia disponibile"""
    for i in range(max_retries):
        try:
            producer = KafkaProducer(
                bootstrap_servers=bootstrap_servers,
                value_serializer=lambda v: str(v).encode('utf-8'),
                api_version_auto_timeout_ms=10000
            )
            producer.close()
            print(f"✅ Kafka è pronto! (tentativo {i+1})")
            return True
        except Exception as e:
            print(f"⏳ Aspettando Kafka... tentativo {i+1}/{max_retries} ({e})")
            time.sleep(2)
    
    print("❌ Timeout: Kafka non disponibile")
    return False

if __name__ == "__main__":
    bootstrap_servers = sys.argv[1] if len(sys.argv) > 1 else 'kafka:29092'
    success = wait_for_kafka([bootstrap_servers])
    sys.exit(0 if success else 1)
