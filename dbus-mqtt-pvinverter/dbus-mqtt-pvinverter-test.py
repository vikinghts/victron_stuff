#!/usr/bin/env python3
import logging
import time
import os
import sys
import configparser
import platform
from gi.repository import GLib as gobject
import paho.mqtt.client as mqtt

# If you want to re-enable Victron D-Bus later:
# from vedbus import VeDbusService

class DbusMqttService:
    def __init__(self, servicename, paths, productname='MQTT', connection='MQTT service'):
        self._paths = paths
        self._lastUpdate = 0
        self.mqtt_data = {"power": 0.0, "energy": 0.0, "voltage": 230.0}  # defaults

        config = self._getConfig()
        self.broker = config['MQTT']['Host']
        self.port = int(config['MQTT'].get('Port', 1883))
        self.username = config['MQTT'].get('Username', '')
        self.password = config['MQTT'].get('Password', '')

        # Initialize MQTT
        self._init_mqtt()

        # Schedule periodic tasks
        gobject.timeout_add(10000, self._log_values)  # log every 10s

    def _getConfig(self):
        config = configparser.ConfigParser(interpolation=None)
        config.read(os.path.join(os.path.dirname(os.path.realpath(__file__)), "config.ini"))
        return config

    def _init_mqtt(self):
        """Connect to MQTT broker and subscribe to Shelly topics."""
        self.client = mqtt.Client()
        if self.username:
            self.client.username_pw_set(self.username, self.password)

        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

        logging.info(f"Connecting to MQTT broker at {self.broker}:{self.port} ...")
        self.client.connect_async(self.broker, self.port, 60)
        self.client.loop_start()

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logging.info("Connected to MQTT broker successfully")
            client.subscribe("shellytest/sensor/power/state")
            client.subscribe("shellytest/sensor/energy/state")
            client.subscribe("shellytest/sensor/voltage/state")
        else:
            logging.error(f"Failed to connect to MQTT broker: {rc}")

    def _on_message(self, client, userdata, msg):
        topic = msg.topic
        payload = msg.payload.decode("utf-8").strip()

        try:
            value = float(payload)
        except ValueError:
            logging.warning(f"Ignoring non-numeric MQTT payload on {topic}: {payload}")
            return

        if topic.endswith("/power/state"):
            self.mqtt_data["power"] = value
        elif topic.endswith("/energy/state"):
            self.mqtt_data["energy"] = value
        elif topic.endswith("/voltage/state"):
            self.mqtt_data["voltage"] = value

        # compute current
        if self.mqtt_data["voltage"] > 0:
            self.mqtt_data["current"] = self.mqtt_data["power"] / self.mqtt_data["voltage"]
        else:
            self.mqtt_data["current"] = 0

        self._lastUpdate = time.time()

        logging.debug(f"MQTT updated: {self.mqtt_data}")

        # Example: If you have D-Bus re-enabled
        # self._dbusservice['/Ac/L1/Power'] = self.mqtt_data["power"]
        # self._dbusservice['/Ac/L1/Voltage'] = self.mqtt_data["voltage"]
        # self._dbusservice['/Ac/L1/Current'] = self.mqtt_data["current"]
        # self._dbusservice['/Ac/L1/Energy/Forward'] = self.mqtt_data["energy"]

    def _log_values(self):
        """Print data periodically for debugging."""
        logging.info(f"Power={self.mqtt_data['power']}W | "
                     f"Voltage={self.mqtt_data['voltage']}V | "
                     f"Current={self.mqtt_data['current']:.2f}A | "
                     f"Energy={self.mqtt_data['energy']}kWh")
        return True  # keep repeating

def main():
    logging.basicConfig(
        format='%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        level=logging.INFO,
        handlers=[
            logging.FileHandler(os.path.join(os.path.dirname(__file__), "current.log")),
            logging.StreamHandler()
        ]
    )

    logging.info("Starting MQTT-based inverter reader")

    paths = {
        '/Ac/L1/Voltage': {'initial': 0, 'textformat': lambda p, v: f"{v:.1f}V"},
        '/Ac/L1/Current': {'initial': 0, 'textformat': lambda p, v: f"{v:.1f}A"},
        '/Ac/L1/Power': {'initial': 0, 'textformat': lambda p, v: f"{v:.1f}W"},
        '/Ac/L1/Energy/Forward': {'initial': 0, 'textformat': lambda p, v: f"{v:.2f}kWh"},
    }

    DbusMqttService("com.victronenergy.pvinverter", paths)

    mainloop = gobject.MainLoop()
    mainloop.run()

if __name__ == "__main__":
    main()
