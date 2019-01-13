import signal
import time
import os
import paho.mqtt.client as paho
from time import sleep
from phue import Bridge
from dotenv import load_dotenv
import logging
import json
load_dotenv()

log = logging.getLogger('electricity-mood-lighting')
log.setLevel(logging.DEBUG)

handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
log.addHandler(handler)

bridge = Bridge(os.environ['HUE_BRIDGE_IP'], os.environ['HUE_API_KEY'])
bridge.connect()
group = bridge.groups[0]

HUE_MIN = 1000
HUE_MAX = 7500
SATURATION_MIN = 150
SATURATION_MAX = 254

TRANSITION_MIN = 2
TRANSITION_MAX = 8

high = 120000
low = 70000

watt_values = {}
last_update = time.time()


def on_subscribe(client, userdata, mid, granted_qos):
    log.info("Subscribed: " + str(mid) + " " + str(granted_qos))


def on_message(client, userdata, msg):
    payload = json.loads(msg.payload.decode("utf-8"))
    if payload['topic'] == "p":
        watt_values[payload['device_id']] = payload['value']


def on_disconnect(client, userdata, rc):
    log.info("Disconnect")


def on_connect(client, userdata, flags, rc):
    client.subscribe("the_plant/readings/electricity/#", qos=0)


def on_log(client, userdata, level, buf):
    if level in [paho.MQTT_LOG_ERR, paho.MQTT_LOG_WARNING, paho.MQTT_LOG_NOTICE]:
        log.info(level, buf)


def scale(value, input_min, input_max, output_min, output_max):
    return int(
        (value - input_min) * (output_max - output_min) / (input_max - input_min) + output_min)


def set_mood(actual):
    saturation = scale(actual, low, high, SATURATION_MIN, SATURATION_MAX)
    hue = scale(actual, low, high, HUE_MAX, HUE_MIN)
    transition_time = scale(actual, low, high, TRANSITION_MAX, TRANSITION_MIN)

    if hue < HUE_MIN:
        hue = HUE_MIN
        saturation = SATURATION_MAX
        transition_time = TRANSITION_MIN
    if hue > HUE_MAX:
        hue = HUE_MAX
        saturation = SATURATION_MIN
        transition_time = TRANSITION_MAX

    log.debug('Actual {}, Hue {}, Saturation {}, Transition {}s: '.format(actual, hue, saturation, transition_time))

    group.saturation = saturation
    group.hue = hue
    group.transitiontime = transition_time * 10
    group.brightness = 75
    time.sleep(transition_time)
    group.transitiontime = (transition_time * 10) / 2
    group.brightness = 254
    time.sleep(transition_time / 2)


def cleanup(signum, frame):
    global run
    run = False


if __name__ == '__main__':
    log.info("Starting...")
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    # Paho MQTT setup
    client = paho.Client(clean_session=True)
    client.username_pw_set(os.environ['MQTT_USERNAME'], os.environ["MQTT_PASSWORD"])
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_subscribe = on_subscribe
    client.on_disconnect = on_disconnect
    client.on_log = on_log
    client.reconnect_delay_set(min_delay=1, max_delay=120)

    client.connect(os.getenv("MQTT_HOST"), port=int(os.getenv("MQTT_PORT")))
    log.info("Connecting to broker {}:{}".format(os.getenv("MQTT_HOST"), os.getenv("MQTT_PORT")))
    client.loop_start()

    run = True
    while run:
        sum_vals = sum([w for w in watt_values.values()])
        set_mood(sum_vals)
        last_update = time.time()

    client.loop_stop()
    log.info("Exiting...")
