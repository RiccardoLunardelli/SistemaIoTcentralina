#!/usr/bin/env python3
"""
CAREL XML Template to JSON Converter - VERSIONE ENHANCED WITH COMMANDS
Genera DUAL OUTPUT: configurazione essenziale + completa
- Essenziale: per ESP32 (address, name, register_type, value_command)
- Completa: per Dashboard enrichment (descriptions, gain, decimals, measurement, etc.)
+ NUOVO: Supporto sezione Commands per scrittura Modbus
"""

import xml.etree.ElementTree as ET
import json
import os
import logging
import time
import sys

# Configurazione logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

device_name = ""

def get_slave_address():
    """Chiede lo slave address all'utente"""
    while True:
        try:
            addr = int(input("Slave address (1-247): "))
            if 1 <= addr <= 247:
                return addr
            print("Errore: deve essere tra 1 e 247")
        except ValueError:
            print("Errore: inserisci un numero")

def get_baud_rate():
    """Chiede il baud_rate all'utente"""
    while True:
        try:
            baud = int(input("Baudrate: "))
            return baud
        except ValueError:
            print("Errore: inserisci un numero")
           
def get_device_name():
    """Chiede il nome del device all'utente"""
    while True:
        try:
            name = input("Device Name: ")
            if name.strip():
                return name.strip()
            print("Errore: inserisci un nome valido")
        except ValueError:
            print("Errore: inserisci una stringa")

def find_continuous_read_element(root):
    """
    Trova l'elemento ContinuousRead nel file XML completo.
    Struttura: XmlCustomSerializer > XML-Class > ContinuosRead
    """
    if root.tag == 'XmlCustomSerializer':
        xml_class = root.find('XML-Class')
        if xml_class is None:
            return None
       
        # Nota: nel file è scritto "ContinuosRead" (senza 'u')
        continuous_read = xml_class.find('ContinuosRead')
        return continuous_read
    else:
        xml_serializer = root.find('XmlCustomSerializer')
        if xml_serializer is None:
            return None
       
        xml_class = xml_serializer.find('XML-Class')
        if xml_class is None:
            return None
       
        continuous_read = xml_class.find('ContinuosRead')
        return continuous_read

def find_parameters_element(root):
    """
    Trova l'elemento Parameters nel file XML completo.
    Struttura: XmlCustomSerializer > XML-Class > Parameters
    """
    if root.tag == 'XmlCustomSerializer':
        xml_class = root.find('XML-Class')
        if xml_class is None:
            return None
       
        parameters = xml_class.find('Parameters')
        return parameters
    else:
        xml_serializer = root.find('XmlCustomSerializer')
        if xml_serializer is None:
            return None
       
        xml_class = xml_serializer.find('XML-Class')
        if xml_class is None:
            return None
       
        parameters = xml_class.find('Parameters')
        return parameters

def find_commands_element(root):
    """
    🆕 NUOVO: Trova l'elemento Commands nel file XML completo.
    Struttura: XmlCustomSerializer > XML-Class > Commands
    """
    if root.tag == 'XmlCustomSerializer':
        xml_class = root.find('XML-Class')
        if xml_class is None:
            return None
       
        commands = xml_class.find('Commands')
        return commands
    else:
        xml_serializer = root.find('XmlCustomSerializer')
        if xml_serializer is None:
            return None
       
        xml_class = xml_serializer.find('XML-Class')
        if xml_class is None:
            return None
       
        commands = xml_class.find('Commands')
        return commands

def extract_template_id(root):
    """
    Estrae l'ID del template dal file XML.
    L'ID si trova nell'attributo ID dell'elemento XML-Class principale.
    """
    if root.tag == 'XmlCustomSerializer':
        xml_class = root.find('XML-Class')
        if xml_class is not None:
            template_id = xml_class.get('ID')
            if template_id:
                return template_id
   
    # Fallback: cerca in tutta la struttura
    for elem in root.iter('XML-Class'):
        template_id = elem.get('ID')
        if template_id:
            return template_id
   
    return "unknown"

def extract_descriptions(reg_element):
    """Estrae tutte le descrizioni multilingua"""
    descriptions = {}
    descriptions_elem = reg_element.find('Descriptions')
    if descriptions_elem is not None:
        for desc in descriptions_elem.findall('XML-Class'):
            code = desc.get('Code')
            description = desc.get('Description')
            if code and description:
                descriptions[code] = description
    return descriptions

def extract_label_values(reg_element):
    """Estrae tutti i label values per campi con opzioni"""
    label_values = []
    label_values_elem = reg_element.find('LabelValues')
    if label_values_elem is not None:
        for label in label_values_elem.findall('XML-Class'):
            value = label.get('Value')
            label_text = label.get('Label')
            if value is not None and label_text is not None:
                label_values.append({
                    'value': value,
                    'label': label_text
                })
    return label_values

def extract_text_values(reg_element):
    """Estrae tutti i text values"""
    text_values = []
    text_values_elem = reg_element.find('TextValues')
    if text_values_elem is not None:
        for text in text_values_elem.findall('XML-Class'):
            # Estrai tutti gli attributi del text value
            text_data = {}
            for attr_name, attr_value in text.attrib.items():
                text_data[attr_name.lower()] = attr_value
            if text_data:
                text_values.append(text_data)
    return text_values

def extract_min_max_values(reg_element):
    """Estrae i valori min e max linkati"""
    min_max = {}
   
    min_elem = reg_element.find('XML-ClassMinValueLinked')
    if min_elem is not None:
        min_max['min_value'] = min_elem.get('Value')
        min_max['min_id'] = min_elem.get('ID')
   
    max_elem = reg_element.find('XML-ClassMaxValueLinked')
    if max_elem is not None:
        min_max['max_value'] = max_elem.get('Value')
        min_max['max_id'] = max_elem.get('ID')
   
    return min_max

def process_register_essential(reg_element):
    """Processa un singolo registro - VERSIONE ESSENZIALE (per ESP32)"""
    address = reg_element.get('Address')
    if not address:
        return None
   
    # 🎯 SOLO I CAMPI ESSENZIALI per ESP32
    data = {
        'address': int(address),
        'name': reg_element.get('Name', ''),
        'register_type': reg_element.get('RegisterType', 'Register')
    }
   
    return data

def process_register_complete(reg_element):
    """Processa un singolo registro - VERSIONE COMPLETA (per Dashboard)"""
    address = reg_element.get('Address')
    if not address:
        return None
   
    # 🎯 TUTTI I PARAMETRI DISPONIBILI per Dashboard
    data = {
        # Parametri base obbligatori
        'address': int(address),
        'name': reg_element.get('Name', ''),
        'register_type': reg_element.get('RegisterType', 'Register'),
       
        # 🔧 PARAMETRI PER DASHBOARD ENRICHMENT
        'decimals': int(reg_element.get('Decimals', '0') or '0'),
        'gain': float(reg_element.get('Gain', '1') or '1'),
        'measurement': reg_element.get('Measurement', ''),
        
        # Attributi XML principali
        'xml_type': reg_element.get('XML-Type', ''),
        'xml_assembly': reg_element.get('XML-Assembly', ''),
        'group_name': reg_element.get('GroupName', ''),
        'label': reg_element.get('Label', ''),
        'category': reg_element.get('Category', ''),
        'default': reg_element.get('Default', ''),
        'visibility': reg_element.get('Visibility', ''),
        'access_level': reg_element.get('AccessLevel', ''),
        'access_write_level': reg_element.get('AccessWriteLevel', ''),
        'enable': reg_element.get('Enable', ''),
        'alias': reg_element.get('Alias', ''),
       
        # Parametri di lettura/scrittura
        'swap_byte_read': reg_element.get('SwapByteRead', 'False'),
        'swap_byte_write': reg_element.get('SwapByteWrite', 'False'),
        'mask': reg_element.get('Mask', '4294967295'),
       
        # Parametri di persistenza e visualizzazione
        'is_persistent': reg_element.get('IsPersistent', 'False'),
        'show_index_page': reg_element.get('ShowIndexPage', 'False'),
        'show_as_image': reg_element.get('ShowAsImage', 'False'),
        'show_in_large_html': reg_element.get('ShowInLargeHTML', 'False'),
       
        # Parametri HTML
        'html_category': reg_element.get('HTMLCategory', ''),
        'html_type': reg_element.get('HTMLType', 'Text'),
        'html_view_enable': reg_element.get('HTMLViewEnable', 'Hidden'),
        'html_view_tag': reg_element.get('HTMLViewTag', ''),
        'html_view_category': reg_element.get('HTMLViewCategory', ''),
        'html_view_index_position': reg_element.get('HTMLViewIndexPosition', '0'),
        'html_view_icon': reg_element.get('HTMLViewIcon', ''),
        'html_view_status_strip': reg_element.get('HTMLViewStatusStrip', ''),
        'html_button1': reg_element.get('HTMLButton1', ''),
        'html_button2': reg_element.get('HTMLButton2', ''),
        'html_button3': reg_element.get('HTMLButton3', ''),
        'html_button_description': reg_element.get('HTMLButtonDescription', ''),
        'html_mask_value': reg_element.get('HTMLMaskValue', ''),
        'report_column': reg_element.get('ReportColumn', ''),
    }
   
    # 🔧 ESTRAI ELEMENTI COMPLESSI per Dashboard
    data['descriptions'] = extract_descriptions(reg_element)
    data['label_values'] = extract_label_values(reg_element)
    data['text_values'] = extract_text_values(reg_element)
   
    # Estrai valori min/max
    min_max = extract_min_max_values(reg_element)
    data.update(min_max)
   
    # Estrai XML-ClassBase se presente
    base_elem = reg_element.find('XML-ClassBase')
    if base_elem is not None:
        data['base_class'] = {
            'xml_type': base_elem.get('XML-Type', ''),
            'xml_assembly': base_elem.get('XML-Assembly', ''),
            'id': base_elem.get('ID', '')
        }
   
    # Estrai Children se presente
    children_elem = reg_element.find('Children')
    if children_elem is not None:
        children = []
        for child in children_elem.findall('XML-Class'):
            child_data = {}
            for attr_name, attr_value in child.attrib.items():
                child_data[attr_name.lower()] = attr_value
            if child_data:
                children.append(child_data)
        data['children'] = children
   
    return data

def process_command_essential(cmd_element):
    """🆕 NUOVO: Processa un singolo comando - VERSIONE ESSENZIALE (per ESP32)"""
    address = cmd_element.get('Address')
    if not address:
        return None
   
    # 🎯 SOLO I CAMPI ESSENZIALI per ESP32
    data = {
        'address': int(address),
        'name': cmd_element.get('Name', ''),
        'register_type': cmd_element.get('RegisterType', 'Coils'),
        'value_command': int(cmd_element.get('ValueCommand', '0') or '0')
    }
   
    return data

def process_command_complete(cmd_element):
    """🆕 NUOVO: Processa un singolo comando - VERSIONE COMPLETA (per Dashboard)"""
    address = cmd_element.get('Address')
    if not address:
        return None
   
    # 🎯 TUTTI I PARAMETRI DISPONIBILI per Dashboard (come registers)
    data = {
        # Parametri base obbligatori
        'address': int(address),
        'name': cmd_element.get('Name', ''),
        'register_type': cmd_element.get('RegisterType', 'Coils'),
        'value_command': int(cmd_element.get('ValueCommand', '0') or '0'),
        
        # 🆕 PARAMETRI SPECIFICI COMMANDS
        'access_write_level': cmd_element.get('AccessWriteLevel', ''),
        'last_value': cmd_element.get('LastValue', ''),
       
        # 🔧 PARAMETRI PER DASHBOARD ENRICHMENT (come registers)
        'decimals': int(cmd_element.get('Decimals', '0') or '0'),
        'gain': float(cmd_element.get('Gain', '1') or '1'),
        'measurement': cmd_element.get('Measurement', ''),
        
        # Attributi XML principali
        'xml_type': cmd_element.get('XML-Type', ''),
        'xml_assembly': cmd_element.get('XML-Assembly', ''),
        'group_name': cmd_element.get('GroupName', ''),
        'label': cmd_element.get('Label', ''),
        'category': cmd_element.get('Category', ''),
        'default': cmd_element.get('Default', ''),
        'visibility': cmd_element.get('Visibility', ''),
        'access_level': cmd_element.get('AccessLevel', ''),
        'enable': cmd_element.get('Enable', ''),
        'alias': cmd_element.get('Alias', ''),
       
        # Parametri di lettura/scrittura
        'swap_byte_read': cmd_element.get('SwapByteRead', 'False'),
        'swap_byte_write': cmd_element.get('SwapByteWrite', 'False'),
        'mask': cmd_element.get('Mask', '4294967295'),
       
        # Parametri di persistenza e visualizzazione
        'is_persistent': cmd_element.get('IsPersistent', 'False'),
        'show_index_page': cmd_element.get('ShowIndexPage', 'False'),
        'show_as_image': cmd_element.get('ShowAsImage', 'False'),
        'show_in_large_html': cmd_element.get('ShowInLargeHTML', 'False'),
       
        # Parametri HTML
        'html_category': cmd_element.get('HTMLCategory', ''),
        'html_type': cmd_element.get('HTMLType', 'Text'),
        'html_view_enable': cmd_element.get('HTMLViewEnable', 'Hidden'),
        'html_view_tag': cmd_element.get('HTMLViewTag', ''),
        'html_view_category': cmd_element.get('HTMLViewCategory', ''),
        'html_view_index_position': cmd_element.get('HTMLViewIndexPosition', '0'),
        'html_view_icon': cmd_element.get('HTMLViewIcon', ''),
        'html_view_status_strip': cmd_element.get('HTMLViewStatusStrip', ''),
        'html_button1': cmd_element.get('HTMLButton1', ''),
        'html_button2': cmd_element.get('HTMLButton2', ''),
        'html_button3': cmd_element.get('HTMLButton3', ''),
        'html_button_description': cmd_element.get('HTMLButtonDescription', ''),
        'html_mask_value': cmd_element.get('HTMLMaskValue', ''),
        'report_column': cmd_element.get('ReportColumn', ''),
    }
   
    # 🔧 ESTRAI ELEMENTI COMPLESSI per Dashboard (come registers)
    data['descriptions'] = extract_descriptions(cmd_element)
    data['label_values'] = extract_label_values(cmd_element)
    data['text_values'] = extract_text_values(cmd_element)
   
    # Estrai valori min/max
    min_max = extract_min_max_values(cmd_element)
    data.update(min_max)
   
    # Estrai XML-ClassBase se presente
    base_elem = cmd_element.find('XML-ClassBase')
    if base_elem is not None:
        data['base_class'] = {
            'xml_type': base_elem.get('XML-Type', ''),
            'xml_assembly': base_elem.get('XML-Assembly', ''),
            'id': base_elem.get('ID', '')
        }
   
    # Estrai Children se presente
    children_elem = cmd_element.find('Children')
    if children_elem is not None:
        children = []
        for child in children_elem.findall('XML-Class'):
            child_data = {}
            for attr_name, attr_value in child.attrib.items():
                child_data[attr_name.lower()] = attr_value
            if child_data:
                children.append(child_data)
        data['children'] = children
   
    return data

def get_all_registers(root, register_processor):
    """Raccoglie tutti i registri da ContinuousRead e Parameters"""
    all_registers = []
   
    # Processa ContinuousRead
    continuous_read = find_continuous_read_element(root)
    if continuous_read is not None:
        cr_registers = continuous_read.findall('.//XML-Class[@XML-Type="ModbusRTU.Template.TTemplateVariableModbus"]')
        logger.info(f"Trovati {len(cr_registers)} registri in ContinuousRead")
       
        for reg in cr_registers:
            processed_reg = register_processor(reg)
            if processed_reg:
                if register_processor == process_register_complete:
                    processed_reg['source'] = 'ContinuousRead'
                all_registers.append(processed_reg)
   
    # Processa Parameters
    parameters = find_parameters_element(root)
    if parameters is not None:
        param_registers = parameters.findall('XML-Class[@XML-Type="ModbusRTU.Template.TTemplateParamModbus"]')
        logger.info(f"Trovati {len(param_registers)} registri in Parameters")
       
        for reg in param_registers:
            processed_reg = register_processor(reg)
            if processed_reg:
                if register_processor == process_register_complete:
                    processed_reg['source'] = 'Parameters'
                all_registers.append(processed_reg)
   
    return all_registers

def get_all_commands(root, command_processor):
    """🆕 NUOVO: Raccoglie tutti i comandi da Commands"""
    all_commands = []
   
    # Processa Commands
    commands = find_commands_element(root)
    if commands is not None:
        cmd_elements = commands.findall('XML-Class[@XML-Type="ModbusRTU.Template.TTemplateCommandModbus"]')
        logger.info(f"Trovati {len(cmd_elements)} comandi in Commands")
       
        for cmd in cmd_elements:
            processed_cmd = command_processor(cmd)
            if processed_cmd:
                if command_processor == process_command_complete:
                    processed_cmd['source'] = 'Commands'
                all_commands.append(processed_cmd)
   
    return all_commands

def convert_xml_to_json(xml_file):
    """Converte XML in JSON - VERSIONE SEMPLIFICATA (Interattiva)"""
    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()
       
        logger.info(f"Root element: {root.tag}")
       
        # Estrae l'ID del template
        template_id = extract_template_id(root)
        logger.info(f"Template ID: {template_id}")
       
        slave_address = get_slave_address()
        baud_rate = get_baud_rate()
        global device_name
        device_name = get_device_name()
       
        # Raccoglie tutti i registri ESSENZIALI
        all_registers = get_all_registers(root, process_register_essential)
        
        # 🆕 NUOVO: Raccoglie tutti i comandi ESSENZIALI
        all_commands = get_all_commands(root, process_command_essential)
       
        # Separa holding registers e coils
        holding_registers = []
        coils = []
       
        for reg in all_registers:
            if reg['register_type'] == 'Coils':
                coils.append(reg)
            else:
                holding_registers.append(reg)
       
        # Ordina per indirizzo
        holding_registers.sort(key=lambda x: x['address'])
        coils.sort(key=lambda x: x['address'])
        all_commands.sort(key=lambda x: x['address'])
       
        # 🎯 STRUTTURA SEMPLIFICATA CON COMMANDS
        result = {
            "metadata": {
                "version": "1.0",
                "device": device_name,
                "slave_address": slave_address,
                "baud_rate": baud_rate,
                "template_id": template_id,
                "total_registers": len(holding_registers) + len(coils),
                "total_commands": len(all_commands)
            },
            "holding_registers": holding_registers,
            "coils": coils,
            "commands": all_commands
        }
       
        return result
       
    except ET.ParseError as e:
        raise ValueError(f"Errore nel parsing XML: {e}")
    except Exception as e:
        raise ValueError(f"Errore generico: {e}")

# ===================== NUOVE FUNZIONI PROGRAMMATICHE =====================

def get_available_templates():
    """
    Scansiona la cartella /app/templates e restituisce i template disponibili
    
    Returns:
        dict: {nome_template: path_file}
    """
    templates = {}
    templates_dir = '/app/templates/xml'
    
    if not os.path.exists(templates_dir):
        print(f"⚠  Directory {templates_dir} non trovata")
        return templates
    
    try:
        for filename in os.listdir(templates_dir):
            if filename.endswith('.xml'):
                # Usa il nome del file senza estensione come chiave
                template_name = filename.replace('.xml', '').lower()
                templates[template_name] = os.path.join(templates_dir, filename)
        
        print(f"📁 Template trovati: {list(templates.keys())}")
        return templates
        
    except Exception as e:
        print(f"❌ Errore scansione templates: {e}")
        return templates

def convert_xml_to_json_programmatic(xml_file, slave_address, baud_rate, device_name):
    """
    Versione programmatica della conversione XML→JSON - ESSENZIALE per ESP32
    Usata dal config_sender.py per generazione automatica
    + NUOVO: Include comandi
    
    Args:
        xml_file (str): Path al file XML template
        slave_address (int): Indirizzo slave Modbus (1-247)
        baud_rate (int): Velocità comunicazione (9600, 19200, etc.)
        device_name (str): Nome dispositivo (es: "mx", "dixell")
    
    Returns:
        dict: Configurazione JSON essenziale per ESP32
    """
    
    print(f"🔄 Conversione programmatica XML→JSON ESSENZIALE CON COMMANDS")
    print(f"   📁 File: {xml_file}")
    print(f"   🏷  Device: {device_name}")
    print(f"   📡 Slave: {slave_address}")
    print(f"   ⚡ Baud: {baud_rate}")
    
    # Verifica file esistente
    if not os.path.exists(xml_file):
        raise FileNotFoundError(f"File XML non trovato: {xml_file}")
    
    # Parsing XML usando le funzioni esistenti
    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()
        
        # Estrae l'ID del template
        template_id = extract_template_id(root)
        print(f"   🆔 Template ID: {template_id}")
        
        # Raccoglie tutti i registri ESSENZIALI usando la logica esistente
        all_registers = get_all_registers(root, process_register_essential)
        
        # 🆕 NUOVO: Raccoglie tutti i comandi ESSENZIALI
        all_commands = get_all_commands(root, process_command_essential)
        
        # Separa holding registers e coils
        holding_registers = []
        coils = []
        
        for reg in all_registers:
            if reg['register_type'] == 'Coils':
                coils.append(reg)
            else:
                holding_registers.append(reg)
        
        # Ordina per indirizzo
        holding_registers.sort(key=lambda x: x['address'])
        coils.sort(key=lambda x: x['address'])
        all_commands.sort(key=lambda x: x['address'])
        
    except ET.ParseError as e:
        raise ValueError(f"Errore parsing XML: {e}")
    except Exception as e:
        raise ValueError(f"Errore processing XML: {e}")
    
    # ✅ STRUTTURA COMPATIBILE CON ESP32 (formato essenziale + commands)
    config = {
        "metadata": {
            "version": "1.0",
            "device": device_name,
            "slave_address": slave_address,
            "baud_rate": baud_rate,
            "template_id": template_id,
            "total_registers": len(holding_registers) + len(coils),
            "total_commands": len(all_commands)
        },
        "holding_registers": holding_registers,
        "coils": coils,
        "commands": all_commands
    }
    
    # Statistiche finali
    total_registers = len(holding_registers) + len(coils)
    print(f"✅ Conversione essenziale completata:")
    print(f"   📊 Holding Registers: {len(holding_registers)}")
    print(f"   🔘 Coils: {len(coils)}")
    print(f"   🎮 Commands: {len(all_commands)}")
    print(f"   📈 Totale Registers: {total_registers}")
    
    return config

def convert_xml_to_json_complete(xml_file, slave_address, baud_rate, device_name):
    """
    🆕 NUOVA: Versione programmatica della conversione XML→JSON - COMPLETA per Dashboard
    Genera file con TUTTI i parametri per enrichment della dashboard
    + NUOVO: Include comandi completi
    
    Args:
        xml_file (str): Path al file XML template
        slave_address (int): Indirizzo slave Modbus (1-247)
        baud_rate (int): Velocità comunicazione (9600, 19200, etc.)
        device_name (str): Nome dispositivo (es: "mx", "dixell")
    
    Returns:
        dict: Configurazione JSON completa per Dashboard enrichment
    """
    
    print(f"🔄 Conversione programmatica XML→JSON COMPLETA CON COMMANDS")
    print(f"   📁 File: {xml_file}")
    print(f"   🏷  Device: {device_name}")
    print(f"   📡 Slave: {slave_address}")
    print(f"   ⚡ Baud: {baud_rate}")
    
    # Verifica file esistente
    if not os.path.exists(xml_file):
        raise FileNotFoundError(f"File XML non trovato: {xml_file}")
    
    # Parsing XML usando le funzioni complete
    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()
        
        # Estrae l'ID del template
        template_id = extract_template_id(root)
        print(f"   🆔 Template ID: {template_id}")
        
        # Raccoglie tutti i registri COMPLETI
        all_registers = get_all_registers(root, process_register_complete)
        
        # 🆕 NUOVO: Raccoglie tutti i comandi COMPLETI
        all_commands = get_all_commands(root, process_command_complete)
        
        # Separa holding registers e coils
        holding_registers = []
        coils = []
        
        for reg in all_registers:
            if reg['register_type'] == 'Coils':
                coils.append(reg)
            else:
                holding_registers.append(reg)
        
        # Ordina per indirizzo
        holding_registers.sort(key=lambda x: x['address'])
        coils.sort(key=lambda x: x['address'])
        all_commands.sort(key=lambda x: x['address'])
        
    except ET.ParseError as e:
        raise ValueError(f"Errore parsing XML: {e}")
    except Exception as e:
        raise ValueError(f"Errore processing XML: {e}")
    
    # 🆕 STRUTTURA COMPLETA per Dashboard CON COMMANDS
    config = {
        "metadata": {
            "version": "2.0-complete",
            "device": device_name,
            "slave_address": slave_address,
            "baud_rate": baud_rate,
            "template_id": template_id,
            "total_registers": len(holding_registers) + len(coils),
            "total_commands": len(all_commands),
            "holding_registers_count": len(holding_registers),
            "coils_count": len(coils),
            "commands_count": len(all_commands),
            "extraction_mode": "full_parameters"
        },
        "holding_registers": holding_registers,
        "coils": coils,
        "commands": all_commands
    }
    
    # Statistiche finali
    total_registers = len(holding_registers) + len(coils)
    print(f"✅ Conversione completa completata:")
    print(f"   📊 Holding Registers: {len(holding_registers)}")
    print(f"   🔘 Coils: {len(coils)}")
    print(f"   🎮 Commands: {len(all_commands)}")
    print(f"   📈 Totale Registers: {total_registers}")
    print(f"   🔧 Parametri per registro: decimals, gain, measurement, descriptions")
    print(f"   🎮 Parametri per comando: value_command, access_write_level, descriptions")
    
    return config

def clean_name(name):
    """Pulisce il nome per renderlo valido come variabile"""
    import re
    
    # Rimuovi caratteri speciali, mantieni solo lettere, numeri e underscore
    cleaned = re.sub(r'[^a-zA-Z0-9_]', '_', str(name))
    
    # Rimuovi underscore multipli
    cleaned = re.sub(r'_+', '_', cleaned)
    
    # Rimuovi underscore iniziali/finali
    cleaned = cleaned.strip('_')
    
    # Se vuoto o inizia con numero, aggiungi prefisso
    if not cleaned or cleaned[0].isdigit():
        cleaned = f"var_{cleaned}"
    
    return cleaned.lower()

# ===================== MAIN CONTAINER-READY =====================

def main():
    """Main function - CONTAINER READY VERSION"""
    # 🔧 CONTAINER MODE: Controlla se siamo in un ambiente interattivo
    try:
        # Test se possiamo leggere input
        if not sys.stdin.isatty():
            print("🐳 Parser in modalità container - nessun input interattivo disponibile")
            print("✅ Parser pronto per chiamate programmatiche da config-service")
            print("📋 Template disponibili:")
            
            templates = get_available_templates()
            for template_name, template_path in templates.items():
                print(f"   - {template_name}: {template_path}")
            
            print("")
            print("💡 Per usare il parser:")
            print("   1. Chiamate programmatiche ESSENZIALI: convert_xml_to_json_programmatic()")
            print("   2. Chiamate programmatiche COMPLETE: convert_xml_to_json_complete()")
            print("   3. Modalità interattiva: docker exec -it xml_parser python xml_parser.py")
            print("   🆕 NUOVO: Supporto completo Commands per scrittura Modbus")
            
            # 🔄 Loop infinito per mantenere il container attivo
            print("🔄 Parser in attesa di chiamate programmatiche...")
            while True:
                time.sleep(60)
                print("💓 Parser attivo...")
                
        else:
            # Modalità interattiva normale
            run_interactive_mode()
            
    except KeyboardInterrupt:
        print("\n👋 Parser terminato dall'utente")
    except Exception as e:
        print(f"❌ Errore nel parser: {e}")

def run_interactive_mode():
    """Esegue la modalità interattiva originale"""
    print("🔄 Parser XML Semplificato - Solo campi essenziali + Commands!")
   
    # Mostra file XML disponibili
    xml_dir = "/app/templates"
    if os.path.exists(xml_dir):
        xml_files = [f for f in os.listdir(xml_dir) if f.endswith('.xml')]
        print(f"📁 File XML disponibili in {xml_dir}:")
        for i, f in enumerate(xml_files, 1):
            print(f"   {i}. {f}")
    else:
        print(f"❌ Directory {xml_dir} non trovata!")
        return
   
    # Scelta del template
    var = int(input("1--> mx || 2--> dixell: "))
    if var == 1:
        xml_file = "/app/templates/MPXProV4.xml"
    elif var == 2:
        xml_file = "/app/templates/XR75CX_9_8_NT.xml"
    else:
        print("Opzione non valida")
        return
   
    if not os.path.exists(xml_file):
        print(f"❌ Errore: File {xml_file} non trovato.")
        print("📋 File presenti nella directory:")
        for f in xml_files:
            print(f"   - {f}")
        return
   
    print(f"📄 Usando file XML: {xml_file}")
   
    try:
        data = convert_xml_to_json(xml_file)
       
        # 💾 SALVA IN ENTRAMBE LE DIRECTORY per compatibilità
        output_dirs = ["/app/output", "/app/templates/json"]
        
        for output_dir in output_dirs:
            if os.path.exists(output_dir):
                output_file = os.path.join(output_dir, device_name + "_registers.json")
                
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                
                print(f"💾 Salvato in: {output_file}")
       
        # 📊 STATISTICHE DIMENSIONI
        main_output = os.path.join("/app/output", device_name + "_registers.json")
        if os.path.exists(main_output):
            file_size = os.path.getsize(main_output)
            
            print(f"✅ Convertiti {data['metadata']['total_registers']} registri + {data['metadata']['total_commands']} comandi")
            print(f"   📊 Holding registers: {len(data['holding_registers'])}")
            print(f"   📊 Coils: {len(data['coils'])}")
            print(f"   🎮 Commands: {len(data['commands'])}")
            print(f"   📦 Dimensione file: {file_size:,} bytes ({file_size//1024:.1f} KB)")
            
            # Verifica dimensione per ESP32
            if file_size < 30000:  # 30KB
                print(f"   ✅ Dimensione ottimale per ESP32!")
            elif file_size < 50000:  # 50KB
                print(f"   ⚠  Dimensione accettabile per ESP32")
            else:
                print(f"   ❌ Dimensione troppo grande per ESP32")
       
    except Exception as e:
        print(f"❌ Errore: {e}")

if __name__ == "__main__":
    main()
