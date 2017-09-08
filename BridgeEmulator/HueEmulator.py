#!/usr/bin/python2.7
from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
from time import strftime, sleep
from datetime import datetime, timedelta
from pprint import pprint
from subprocess import check_output
import json, socket, hashlib, urllib2, struct, random, sys
from threading import Thread
from collections import defaultdict
from uuid import getnode as get_mac
from urlparse import urlparse, parse_qs

mac = '%012x' % get_mac()

run_service = True

bridge_config = defaultdict(lambda:defaultdict(str))
new_lights = {}
sensors_state = {}

def sendEmail(triggered_sensor):
    import smtplib

    TEXT = "Sensor " + triggered_sensor + " was triggered while the alarm is active"
    # Prepare actual message
    message = """From: %s\nTo: %s\nSubject: %s\n\n%s
    """ % (bridge_config["alarm_config"]["mail_from"], ", ".join(bridge_config["alarm_config"]["mail_recipients"]), bridge_config["alarm_config"]["mail_subject"], TEXT)
    try:
        server_ssl = smtplib.SMTP_SSL(bridge_config["alarm_config"]["smtp_server"], bridge_config["alarm_config"]["smtp_port"])
        server_ssl.ehlo() # optional, called by login()
        server_ssl.login(bridge_config["alarm_config"]["mail_username"], bridge_config["alarm_config"]["mail_password"])
        server_ssl.sendmail(bridge_config["alarm_config"]["mail_from"], bridge_config["alarm_config"]["mail_recipients"], message)
        server_ssl.close()
        print("successfully sent the mail")
        return True
    except:
        print("failed to send mail")
        return False

#load config files
try:
    with open('config.json', 'r') as fp:
        bridge_config = json.load(fp)
        print("Config loaded")
except Exception:
    print("CRITICAL! Config file was not loaded")
    sys.exit(1)


#load and configure alarm virtual light
if bridge_config["alarm_config"]["mail_username"] != "":
    print("E-mail account configured")
    if "virtual_light" not in bridge_config["alarm_config"]:
        print("Send test email")
        if sendEmail("dummy test"):
            print("Mail succesfully sent\nCreate alarm virtual light")
            new_light_id = nextFreeId("lights")
            bridge_config["lights"][new_light_id] = {"state": {"on": False, "bri": 200, "hue": 0, "sat": 0, "xy": [0.690456, 0.295907], "ct": 461, "alert": "none", "effect": "none", "colormode": "xy", "reachable": True}, "type": "Extended color light", "name": "Alarm", "uniqueid": "1234567ffffff", "modelid": "LLC012", "swversion": "66009461"}
            bridge_config["alarm_config"]["virtual_light"] = new_light_id
        else:
            print("Mail test failed")


def generateSensorsState():
    for sensor in bridge_config["sensors"]:
        if sensor not in sensors_state and "state" in bridge_config["sensors"][sensor]:
            sensors_state[sensor] = {"state": {}}
            for key in bridge_config["sensors"][sensor]["state"].iterkeys():
                if key in ["lastupdated", "presence", "flag", "dark", "status"]:
                    sensors_state[sensor]["state"].update({key: "2017-01-01T00:00:00"})

def nextFreeId(element):
    i = 1
    while (str(i)) in bridge_config[element]:
        i += 1
    return str(i)

generateSensorsState() #comment this line if you don't want to restore last known state to all lights on startup

def getIpAddress():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    return s.getsockname()[0]


bridge_config["config"]["ipaddress"] = getIpAddress()
bridge_config["config"]["gateway"] = getIpAddress()
bridge_config["config"]["mac"] = mac[0] + mac[1] + ":" + mac[2] + mac[3] + ":" + mac[4] + mac[5] + ":" + mac[6] + mac[7] + ":" + mac[8] + mac[9] + ":" + mac[10] + mac[11]
bridge_config["config"]["bridgeid"] = (mac[:6] + 'FFFE' + mac[6:]).upper()

def saveConfig():
    with open('config.json', 'w') as fp:
        json.dump(bridge_config, fp, sort_keys=True, indent=4, separators=(',', ': '))

def ssdpSearch():
    SSDP_ADDR = '239.255.255.250'
    SSDP_PORT = 1900
    MSEARCH_Interval = 2
    multicast_group_c = SSDP_ADDR
    multicast_group_s = (SSDP_ADDR, SSDP_PORT)
    server_address = ('', SSDP_PORT)
    Response_message = 'HTTP/1.1 200 OK\r\nHOST: 239.255.255.250:1900\r\nEXT:\r\nCACHE-CONTROL: max-age=100\r\nLOCATION: http://' + getIpAddress() + ':80/description.xml\r\nSERVER: Linux/3.14.0 UPnP/1.0 IpBridge/1.20.0\r\nhue-bridgeid: ' + (mac[:6] + 'FFFE' + mac[6:]).upper() + '\r\n'
    custom_response_message = {0: {"st": "upnp:rootdevice", "usn": "uuid:2f402f80-da50-11e1-9b23-" + mac + "::upnp:rootdevice"}, 1: {"st": "uuid:2f402f80-da50-11e1-9b23-" + mac, "usn": "uuid:2f402f80-da50-11e1-9b23-" + mac}, 2: {"st": "urn:schemas-upnp-org:device:basic:1", "usn": "uuid:2f402f80-da50-11e1-9b23-" + mac}}
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(server_address)

    group = socket.inet_aton(multicast_group_c)
    mreq = struct.pack('4sL', group, socket.INADDR_ANY)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

    print("starting ssdp...")

    while run_service:
              data, address = sock.recvfrom(1024)
              if data[0:19]== 'M-SEARCH * HTTP/1.1':
                   if data.find("ssdp:all") != -1:
                       sleep(random.randrange(0, 3))
                       print("Sending M Search response")
                       for x in xrange(3):
                          sock.sendto(Response_message + "ST: " + custom_response_message[x]["st"] + "\r\nUSN: " + custom_response_message[x]["usn"] + "\r\n\r\n", address)
                          print(Response_message + "ST: " + custom_response_message[x]["st"] + "\r\nUSN: " + custom_response_message[x]["usn"] + "\r\n\r\n")
              sleep(1)

def ssdpBroadcast():
    print("start ssdp broadcast")
    SSDP_ADDR = '239.255.255.250'
    SSDP_PORT = 1900
    MSEARCH_Interval = 2
    multicast_group_s = (SSDP_ADDR, SSDP_PORT)
    message = 'NOTIFY * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nCACHE-CONTROL: max-age=100\r\nLOCATION: http://' + getIpAddress() + ':80/description.xml\r\nSERVER: Linux/3.14.0 UPnP/1.0 IpBridge/1.20.0\r\nNTS: ssdp:alive\r\nhue-bridgeid: ' + (mac[:6] + 'FFFE' + mac[6:]).upper() + '\r\n'
    custom_message = {0: {"nt": "upnp:rootdevice", "usn": "uuid:2f402f80-da50-11e1-9b23-" + mac + "::upnp:rootdevice"}, 1: {"nt": "uuid:2f402f80-da50-11e1-9b23-" + mac, "usn": "uuid:2f402f80-da50-11e1-9b23-" + mac}, 2: {"nt": "urn:schemas-upnp-org:device:basic:1", "usn": "uuid:2f402f80-da50-11e1-9b23-" + mac}}
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(MSEARCH_Interval+0.5)
    ttl = struct.pack('b', 1)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)
    while True:
        for x in xrange(3):
            sent = sock.sendto(message + "NT: " + custom_message[x]["nt"] + "\r\nUSN: " + custom_message[x]["usn"] + "\r\n\r\n",multicast_group_s)
            sent = sock.sendto(message + "NT: " + custom_message[x]["nt"] + "\r\nUSN: " + custom_message[x]["usn"] + "\r\n\r\n",multicast_group_s)
            #print (message + "NT: " + custom_message[x]["nt"] + "\r\nUSN: " + custom_message[x]["usn"] + "\r\n\r\n")
        sleep(60)

def schedulerProcessor():
    while run_service:
        for schedule in bridge_config["schedules"].iterkeys():
            delay = 0
            if bridge_config["schedules"][schedule]["status"] == "enabled":
                if bridge_config["schedules"][schedule]["localtime"][-9:-8] == "A":
                    delay = random.randrange(0, int(bridge_config["schedules"][schedule]["localtime"][-8:-6]) * 3600 + int(bridge_config["schedules"][schedule]["localtime"][-5:-3]) * 60 + int(bridge_config["schedules"][schedule]["localtime"][-2:]))
                    schedule_time = bridge_config["schedules"][schedule]["localtime"][:-9]
                else:
                    schedule_time = bridge_config["schedules"][schedule]["localtime"]
                if schedule_time.startswith("W"):
                    pices = schedule_time.split('/T')
                    if int(pices[0][1:]) & (1 << 6 - datetime.today().weekday()):
                        if pices[1] == datetime.now().strftime("%H:%M:%S"):
                            print("execute schedule: " + schedule + " withe delay " + str(delay))
                            sendRequest(bridge_config["schedules"][schedule]["command"]["address"], bridge_config["schedules"][schedule]["command"]["method"], json.dumps(bridge_config["schedules"][schedule]["command"]["body"]), 1, delay)
                elif schedule_time.startswith("PT"):
                    timmer = schedule_time[2:]
                    (h, m, s) = timmer.split(':')
                    d = timedelta(hours=int(h), minutes=int(m), seconds=int(s))
                    if bridge_config["schedules"][schedule]["starttime"] == (datetime.utcnow() - d).strftime("%Y-%m-%dT%H:%M:%S"):
                        print("execute timmer: " + schedule + " withe delay " + str(delay))
                        sendRequest(bridge_config["schedules"][schedule]["command"]["address"], bridge_config["schedules"][schedule]["command"]["method"], json.dumps(bridge_config["schedules"][schedule]["command"]["body"]), 1, delay)
                        bridge_config["schedules"][schedule]["status"] = "disabled"
                else:
                    if schedule_time == datetime.now().strftime("%Y-%m-%dT%H:%M:%S"):
                        print("execute schedule: " + schedule + " withe delay " + str(delay))
                        sendRequest(bridge_config["schedules"][schedule]["command"]["address"], bridge_config["schedules"][schedule]["command"]["method"], json.dumps(bridge_config["schedules"][schedule]["command"]["body"]), 1, delay)
                        if bridge_config["schedules"][schedule]["autodelete"]:
                            del bridge_config["schedules"][schedule]
        if (datetime.now().strftime("%M:%S") == "00:00"): #auto save configuration every hour
            saveConfig()
        sleep(1)

def addTradfriRemote(sensor_id, group_id):
    rules = [{"actions": [{"address": "/groups/" + group_id + "/action","body": {"on": True},"method": "PUT"}],"conditions": [{"address": "/sensors/" + sensor_id + "/state/lastupdated","operator": "dx"},{"address": "/sensors/" + sensor_id + "/state/buttonevent","operator": "eq","value": "1002"},{"address": "/groups/" + group_id + "/action/on","operator": "eq","value": "false"}],"name": "Remote " + sensor_id + " button on"}, {"actions": [{"address": "/groups/" + group_id + "/action","body": {"on": False},"method": "PUT"}],"conditions": [{"address": "/sensors/" + sensor_id + "/state/lastupdated","operator": "dx"},{"address": "/sensors/" + sensor_id + "/state/buttonevent","operator": "eq","value": "1002"},{"address": "/groups/" + group_id + "/action/on","operator": "eq","value": "true"}],"name": "Remote " + sensor_id + " button off"},{ "actions": [ { "address": "/groups/" + group_id + "/action", "body": { "bri_inc": 30, "transitiontime": 9 }, "method": "PUT" } ], "conditions": [ { "address": "/sensors/" + sensor_id + "/state/buttonevent", "operator": "eq", "value": "2002" }, { "address": "/sensors/" + sensor_id + "/state/lastupdated", "operator": "dx" } ], "name": "Dimmer Switch " + sensor_id + " up-press" }, { "actions": [ { "address": "/groups/" + group_id + "/action", "body": { "bri_inc": 56, "transitiontime": 9 }, "method": "PUT" } ], "conditions": [ { "address": "/sensors/" + sensor_id + "/state/buttonevent", "operator": "eq", "value": "2001" }, { "address": "/sensors/" + sensor_id + "/state/lastupdated", "operator": "dx" } ], "name": "Dimmer Switch " + sensor_id + " up-long" }, { "actions": [ { "address": "/groups/" + group_id + "/action", "body": { "bri_inc": -30, "transitiontime": 9 }, "method": "PUT" } ], "conditions": [ { "address": "/sensors/" + sensor_id + "/state/buttonevent", "operator": "eq", "value": "3002" }, { "address": "/sensors/" + sensor_id + "/state/lastupdated", "operator": "dx" } ], "name": "Dimmer Switch " + sensor_id + " dn-press" }, { "actions": [ { "address": "/groups/" + group_id + "/action", "body": { "bri_inc": -56, "transitiontime": 9 }, "method": "PUT" } ], "conditions": [ { "address": "/sensors/" + sensor_id + "/state/buttonevent", "operator": "eq", "value": "3001" }, { "address": "/sensors/" + sensor_id + "/state/lastupdated", "operator": "dx" } ], "name": "Dimmer Switch " + sensor_id + " dn-long" }, { "actions": [ { "address": "/groups/" + group_id + "/action", "body": { "ct_inc": 50, "transitiontime": 9 }, "method": "PUT" } ], "conditions": [ { "address": "/sensors/" + sensor_id + "/state/buttonevent", "operator": "eq", "value": "4002" }, { "address": "/sensors/" + sensor_id + "/state/lastupdated", "operator": "dx" } ], "name": "Dimmer Switch " + sensor_id + " ctl-press" }, { "actions": [ { "address": "/groups/" + group_id + "/action", "body": { "ct_inc": 100, "transitiontime": 9 }, "method": "PUT" } ], "conditions": [ { "address": "/sensors/" + sensor_id + "/state/buttonevent", "operator": "eq", "value": "4001" }, { "address": "/sensors/" + sensor_id + "/state/lastupdated", "operator": "dx" } ], "name": "Dimmer Switch " + sensor_id + " ctl-long" }, { "actions": [ { "address": "/groups/" + group_id + "/action", "body": { "ct_inc": -50, "transitiontime": 9 }, "method": "PUT" } ], "conditions": [ { "address": "/sensors/" + sensor_id + "/state/buttonevent", "operator": "eq", "value": "5002" }, { "address": "/sensors/" + sensor_id + "/state/lastupdated", "operator": "dx" } ], "name": "Dimmer Switch " + sensor_id + " ct-press" }, { "actions": [ { "address": "/groups/" + group_id + "/action", "body": { "ct_inc": -100, "transitiontime": 9 }, "method": "PUT" } ], "conditions": [ { "address": "/sensors/" + sensor_id + "/state/buttonevent", "operator": "eq", "value": "5001" }, { "address": "/sensors/" + sensor_id + "/state/lastupdated", "operator": "dx" } ], "name": "Dimmer Switch " + sensor_id + " ct-long" }]
    resourcelinkId = nextFreeId("resourcelinks")
    bridge_config["resourcelinks"][resourcelinkId] = {"classid": 15555,"description": "Rules for sensor " + sensor_id, "links": ["/sensors/3"],"name": "Emulator rules " + sensor_id,"owner": bridge_config["config"]["whitelist"].keys()[0]}
    for rule in rules:
        ruleId = nextFreeId("rules")
        bridge_config["rules"][ruleId] = rule
        bridge_config["rules"][ruleId].update({"creationtime": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"), "lasttriggered": None, "owner": bridge_config["config"]["whitelist"].keys()[0], "recycle": True, "status": "enabled", "timestriggered": 0})
        bridge_config["resourcelinks"][resourcelinkId]["links"].append("/rules/" + ruleId);

def addHueMotionSensor():
    new_sensor_id = nextFreeId("sensors")
    bridge_config["sensors"][new_sensor_id] = {"name": "Hue temperature sensor 1", "uniqueid": new_sensor_id + "0f:12:23:34:45:56:d0:5b-02-0402", "type": "ZLLTemperature", "swversion": "6.1.0.18912", "state": {"temperature": None, "lastupdated": "none"}, "manufacturername": "Philips", "config": {"on": False, "battery": 100, "reachable": True, "alert":"none", "ledindication": False, "usertest": False, "pending": []}, "modelid": "SML001"}
    bridge_config["sensors"][str(int(new_sensor_id) + 1)] = {"name": "Entrance Lights sensor", "uniqueid": new_sensor_id + "0f:12:23:34:45:56:d0:5b-02-0406", "type": "ZLLPresence", "swversion": "6.1.0.18912", "state": {"lastupdated": "none", "presence": None}, "manufacturername": "Philips", "config": {"on": False,"battery": 100,"reachable": True, "alert": "lselect", "ledindication": False, "usertest": False, "sensitivity": 2, "sensitivitymax": 2,"pending": []}, "modelid": "SML001"}
    bridge_config["sensors"][str(int(new_sensor_id) + 2)] = {"name": "Hue ambient light sensor 1", "uniqueid": new_sensor_id + "0f:12:23:34:45:56:d0:5b-02-0400", "type": "ZLLLightLevel", "swversion": "6.1.0.18912", "state": {"dark": True, "daylight": False, "lightlevel": 6000, "lastupdated": "none"}, "manufacturername": "Philips", "config": {"on": False,"battery": 100, "reachable": True, "alert": "none", "tholddark": 21597, "tholdoffset": 7000, "ledindication": False, "usertest": False, "pending": []}, "modelid": "SML001"}
    return(str(int(new_sensor_id) + 1))


def checkRuleConditions(rule, sensor, ignore_ddx=False):
    ddx = 0
    sensor_found = False
    for condition in bridge_config["rules"][rule]["conditions"]:
        url_pices = condition["address"].split('/')
        if url_pices[1] == "sensors" and sensor == url_pices[2]:
            sensor_found = True
        if condition["operator"] == "eq":
            if condition["value"] == "true":
                if not bridge_config[url_pices[1]][url_pices[2]][url_pices[3]][url_pices[4]]:
                    return [False, 0]
            elif condition["value"] == "false":
                if bridge_config[url_pices[1]][url_pices[2]][url_pices[3]][url_pices[4]]:
                    return [False, 0]
            else:
                if not int(bridge_config[url_pices[1]][url_pices[2]][url_pices[3]][url_pices[4]]) == int(condition["value"]):
                    return [False, 0]
        elif condition["operator"] == "gt":
            if not int(bridge_config[url_pices[1]][url_pices[2]][url_pices[3]][url_pices[4]]) > int(condition["value"]):
                return [False, 0]
        elif condition["operator"] == "lt":
            if int(not bridge_config[url_pices[1]][url_pices[2]][url_pices[3]][url_pices[4]]) < int(condition["value"]):
                return [False, 0]
        elif condition["operator"] == "dx":
            if not sensors_state[url_pices[2]][url_pices[3]][url_pices[4]] == datetime.now().strftime("%Y-%m-%dT%H:%M:%S"):
                return [False, 0]
        elif condition["operator"] == "in":
            periods = condition["value"].split('/')
            if condition["value"][0] == "T":
                timeStart = datetime.strptime(periods[0], "T%H:%M:%S").time()
                timeEnd = datetime.strptime(periods[1], "T%H:%M:%S").time()
                now_time = datetime.now().time()
                if timeStart < timeEnd:
                    if not timeStart <= now_time <= timeEnd:
                        return [False, 0]
                else:
                    if not (timeStart <= now_time or now_time <= timeEnd):
                        return [False, 0]
        elif condition["operator"] == "ddx" and ignore_ddx is False:
            if not sensors_state[url_pices[2]][url_pices[3]][url_pices[4]] == datetime.now().strftime("%Y-%m-%dT%H:%M:%S"):
                    return [False, 0]
            else:
                ddx = int(condition["value"][2:4]) * 3600 + int(condition["value"][5:7]) * 60 + int(condition["value"][-2:])
    if sensor_found:
        return [True, ddx]
    else:
        return [False, ddx]

def ddxRecheck(rule, sensor, ddx_delay):
    sleep(ddx_delay)
    rule_state = checkRuleConditions(rule, sensor, True)
    if rule_state[0]: #if all conditions are meet again
        print("delayed rule " + rule + " is triggered")
        bridge_config["rules"][rule]["lasttriggered"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        bridge_config["rules"][rule]["timestriggered"] += 1
        for action in bridge_config["rules"][rule]["actions"]:
            Thread(target=sendRequest, args=["/api/" + bridge_config["rules"][rule]["owner"] + action["address"], action["method"], json.dumps(action["body"])]).start()

def rulesProcessor(sensor):
    bridge_config["config"]["localtime"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S") #required for operator dx to address /config/localtime
    for rule in bridge_config["rules"].iterkeys():
        if bridge_config["rules"][rule]["status"] == "enabled":
            rule_result = checkRuleConditions(rule, sensor)
            if rule_result[0] and bridge_config["rules"][rule]["lasttriggered"] != datetime.now().strftime("%Y-%m-%dT%H:%M:%S"): #if all condition are meet + anti loopback
                if rule_result[1] == 0: #if not ddx rule
                    print("rule " + rule + " is triggered")
                    bridge_config["rules"][rule]["lasttriggered"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
                    bridge_config["rules"][rule]["timestriggered"] += 1
                    for action in bridge_config["rules"][rule]["actions"]:
                        Thread(target=sendRequest, args=["/api/" + bridge_config["rules"][rule]["owner"] + action["address"], action["method"], json.dumps(action["body"])]).start()
                else: #if ddx rule
                    print("ddx rule " + rule + " will be re validated after " + str(rule_result[1]) + " seconds")
                    Thread(target=ddxRecheck, args=[rule, sensor, rule_result[1]]).start()

def sendRequest(url, method, data, time_out=3, delay=0):
    if delay != 0:
        sleep(delay)
    if not url.startswith( 'http://' ):
        url = "http://127.0.0.1" + url
    opener = urllib2.build_opener(urllib2.HTTPHandler)
    request = urllib2.Request(url, data=data)
    request.add_header("Content-Type",'application/json')
    request.get_method = lambda: method
    response = opener.open(request, timeout=time_out).read()
    return response

def convert_xy(x, y, bri): #needed for milight hub that don't work with xy values
    Y = bri / 250.0
    z = 1.0 - x - y

    X = (Y / y) * x
    Z = (Y / y) * z

  # sRGB D65 conversion
    r =  X * 1.656492 - Y * 0.354851 - Z * 0.255038
    g = -X * 0.707196 + Y * 1.655397 + Z * 0.036152
    b =  X * 0.051713 - Y * 0.121364 + Z * 1.011530

    if r > b and r > g and r > 1:
    # red is too big
        g = g / r
        b = b / r
        r = 1

    elif g > b and g > r and g > 1:
    #green is too big
        r = r / g
        b = b / g
        g = 1

    elif b > r and b > g and b > 1:
    # blue is too big
        r = r / b
        g = g / b
        b = 1

    r = 12.92 * r if r <= 0.0031308 else (1.0 + 0.055) * pow(r, (1.0 / 2.4)) - 0.055
    g = 12.92 * g if g <= 0.0031308 else (1.0 + 0.055) * pow(g, (1.0 / 2.4)) - 0.055
    b = 12.92 * b if b <= 0.0031308 else (1.0 + 0.055) * pow(b, (1.0 / 2.4)) - 0.055

    if r > b and r > g:
    # red is biggest
        if r > 1:
            g = g / r
            b = b / r
            r = 1
        elif g > b and g > r:
        # green is biggest
            if g > 1:
                r = r / g
                b = b / g
                g = 1

        elif b > r and b > g:
        # blue is biggest
            if b > 1:
                r = r / b
                g = g / b
                b = 1

    r = 0 if r < 0 else r
    g = 0 if g < 0 else g
    b = 0 if b < 0 else b

    return [int(r * 255), int(g * 255), int(b * 255)]

def sendLightRequest(light, data):
    payload = {}
    if light in bridge_config["lights_address"]:
        if bridge_config["lights_address"][light]["protocol"] == "native": #ESP8266 light or strip
            url = "http://" + bridge_config["lights_address"][light]["ip"] + "/set?light=" + str(bridge_config["lights_address"][light]["light_nr"]);
            method = 'GET'
            for key, value in data.iteritems():
                if key == "xy":
                    url += "&x=" + str(value[0]) + "&y=" + str(value[1])
                else:
                    url += "&" + key + "=" + str(value)
        elif bridge_config["lights_address"][light]["protocol"] == "hue" or bridge_config["lights_address"][light]["protocol"] == "deconz": #Original Hue light or Deconz light
            url = "http://" + bridge_config["lights_address"][light]["ip"] + "/api/" + bridge_config["lights_address"][light]["username"] + "/lights/" + bridge_config["lights_address"][light]["light_id"] + "/state"
            method = 'PUT'
            payload = data
        elif bridge_config["lights_address"][light]["protocol"] == "milight": #MiLight bulb
            url = "http://" + bridge_config["lights_address"][light]["ip"] + "/gateways/" + bridge_config["lights_address"][light]["device_id"] + "/" + bridge_config["lights_address"][light]["mode"] + "/" + str(bridge_config["lights_address"][light]["group"]);
            method = 'PUT'
            for key, value in data.iteritems():
                if key == "on":
                    payload["status"] = value
                elif key == "bri":
                    payload["brightness"] = value
                elif key == "ct":
                    payload["color_temp"] = int((500 - value) / 1.6 + 153)
                elif key == "hue":
                    payload["hue"] = value / 180
                elif key == "sat":
                    payload["saturation"] = value * 100 / 255
                elif key == "xy":
                    payload["color"] = {}
                    (payload["color"]["r"], payload["color"]["g"], payload["color"]["b"]) = convert_xy(value[0], value[1], bridge_config["lights"][light]["state"]["bri"])
            print(json.dumps(payload))
        elif bridge_config["lights_address"][light]["protocol"] == "ikea_tradfri": #IKEA Tradfri bulb
            url = "coaps://" + bridge_config["lights_address"][light]["ip"] + ":5684/15001/" + str(bridge_config["lights_address"][light]["device_id"])
            for key, value in data.iteritems():
                if key == "on":
                    payload["5850"] = int(value)
                elif key == "transitiontime":
                    payload["transitiontime"] = value
                elif key == "bri":
                    payload["5851"] = value
                elif key == "ct":
                    if value < 270:
                        payload["5706"] = "f5faf6"
                    elif value < 385:
                        payload["5706"] = "f1e0b5"
                    else:
                        payload["5706"] = "efd275"
                elif key == "xy":
                    payload["5709"] = int(value[0] * 65535)
                    payload["5710"] = int(value[1] * 65535)
            if "5850" in payload and payload["5850"] == 0:
                payload.clear() #setting brightnes will turn on the ligh even if there was a request to power off
                payload["5850"] = 0
            elif "5850" in payload and "5851" in payload: #when setting brightness don't send also power on command
                del payload["5850"]
                pprint(payload)

        try:
            if bridge_config["lights_address"][light]["protocol"] == "ikea_tradfri":
                if "transitiontime" in payload:
                    transitiontime = payload["transitiontime"]
                else:
                    transitiontime = 4
                    for key, value in payload.iteritems(): #ikea bulbs don't accept all arguments at once
                        print(check_output("./coap-client-linux -m put -u \"Client_identity\" -k \"" + bridge_config["lights_address"][light]["security_code"] + "\" -e '{ \"3311\": [" + json.dumps({key : value, "5712": transitiontime}) + "] }' \"" + url + "\"", shell=True).split("\n")[3])
                        sleep(0.5)
            else:
                sendRequest(url, method, json.dumps(payload))
        except:
            bridge_config["lights"][light]["state"]["reachable"] = False
            print("request error")
        else:
            bridge_config["lights"][light]["state"]["reachable"] = True
            print("LightRequest: " + url)

def updateGroupStats(light): #set group stats based on lights status in that group
    for group in bridge_config["groups"]:
        if light in bridge_config["groups"][group]["lights"]:
            for key, value in bridge_config["lights"][light]["state"].iteritems():
                if key not in ["on", "reachable"]:
                    bridge_config["groups"][group]["action"][key] = value
            any_on = False
            all_on = True
            bri = 0
            for group_light in bridge_config["groups"][group]["lights"]:
                if bridge_config["lights"][light]["state"]["on"] == True:
                    any_on = True
                else:
                    all_on = False
                bri += bridge_config["lights"][light]["state"]["bri"]
            avg_bri = bri / len(bridge_config["groups"][group]["lights"])
            bridge_config["groups"][group]["state"] = {"any_on": any_on, "all_on": all_on, "bri": avg_bri, "lastupdated": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")}


def scanForLights(): #scan for ESP8266 lights and strips
    print(json.dumps([{"success": {"/lights": "Searching for new devices"}}], sort_keys=True, indent=4, separators=(',', ': ')))
    #return all host that listen on port 80
    device_ips = check_output("nmap  " + getIpAddress() + "/24 -p80 --open -n | grep report | cut -d ' ' -f5", shell=True).split("\n")
    del device_ips[-1] #delete last empty element in list
    for ip in device_ips:
        if ip != getIpAddress():
            try:
                f = urllib2.urlopen("http://" + ip + "/detect")
                device_data = json.loads(f.read())
                if device_data.keys()[0] == "hue":
                    print(ip + " is a hue " + device_data['hue'])
                    device_exist = False
                    for light in bridge_config["lights"].iterkeys():
                        if bridge_config["lights"][light]["uniqueid"].startswith( device_data["mac"] ):
                            device_exist = True
                            bridge_config["lights_address"][light]["ip"] = ip
                    if not device_exist:
                        print("is a new device")
                        for x in xrange(1, int(device_data["lights"]) + 1):
                            new_light_id = nextFreeId("lights")
                            modelid = "LCT001"
                            if device_data["type"] == "strip":
                                modelid = "LST001"
                            elif device_data["type"] == "generic":
                                modelid = "LCT003"
                            bridge_config["lights"][new_light_id] = {"state": {"on": False, "bri": 200, "hue": 0, "sat": 0, "xy": [0.0, 0.0], "ct": 461, "alert": "none", "effect": "none", "colormode": "ct", "reachable": True}, "type": "Extended color light", "name": "Hue " + device_data["type"] + " " + device_data["hue"] + " " + str(x), "uniqueid": device_data["mac"] + "-" + str(x), "modelid": modelid, "swversion": "66009461"}
                            new_lights.update({new_light_id: {"name": "Hue " + device_data["type"] + " " + device_data["hue"] + " " + str(x)}})
                            bridge_config["lights_address"][new_light_id] = {"ip": ip, "light_nr": x, "protocol": "native"}
            except Exception as e:
                print(ip + " is unknow device " + str(e))
    scanDeconz()

def syncWithLights(): #update Hue Bridge lights states
    for light in bridge_config["lights_address"]:
        if bridge_config["lights_address"][light]["protocol"] == "native":
            try:
                light_data = json.loads(sendRequest("http://" + bridge_config["lights_address"][light]["ip"] + "/get?light=" + str(bridge_config["lights_address"][light]["light_nr"]), "GET", "{}", 0.5))
            except:
                bridge_config["lights"][light]["state"]["reachable"] = False
                bridge_config["lights"][light]["state"]["on"] = False
                print("request error")
            else:
                bridge_config["lights"][light]["state"]["reachable"] = True
                bridge_config["lights"][light]["state"].update(light_data)
        elif bridge_config["lights_address"][light]["protocol"] == "hue":
            light_data = json.loads(sendRequest("http://" + bridge_config["lights_address"][light]["ip"] + "/api/" + bridge_config["lights_address"][light]["username"] + "/lights/" + bridge_config["lights_address"][light]["light_id"] + "/state"), "GET", "{}", 1)
            bridge_config["lights"][light]["state"].update(light_data)
        elif bridge_config["lights_address"][light]["protocol"] == "ikea_tradfri":
            light_stats = json.loads(check_output("./coap-client-linux -m get -u \"Client_identity\" -k \"" + bridge_config["lights_address"][light]["security_code"] + "\" \"coaps://" + bridge_config["lights_address"][light]["ip"] + ":5684/15001/" + str(bridge_config["lights_address"][light]["device_id"]) +"\"", shell=True).split("\n")[3])
            bridge_config["lights"][light]["state"]["on"] = bool(light_stats["3311"][0]["5850"])
            bridge_config["lights"][light]["state"]["bri"] = light_stats["3311"][0]["5851"]
            if "5706" in light_stats["3311"][0]:
                if light_stats["3311"][0]["5706"] == "f5faf6":
                    bridge_config["lights"][light]["state"]["ct"] = 170
                elif light_stats["3311"][0]["5706"] == "f1e0b5":
                    bridge_config["lights"][light]["state"]["ct"] = 320
                elif light_stats["3311"][0]["5706"] == "efd275":
                    bridge_config["lights"][light]["state"]["ct"] = 470
            else:
                bridge_config["lights"][light]["state"]["ct"] = 470

def longPressButton(sensor, buttonevent):
    print("long press detected")
    sleep(1)
    while bridge_config["sensors"][sensor]["state"]["buttonevent"] == buttonevent:
        print("still pressed")
        sensors_state[sensor]["state"]["lastupdated"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
        rulesProcessor(sensor)
        sleep(0.9)
    return


def websocketClient():
    from ws4py.client.threadedclient import WebSocketClient
    class EchoClient(WebSocketClient):
        def opened(self):
            self.send("hello")

        def closed(self, code, reason=None):
            print(("deconz websocket disconnected", code, reason))

        def received_message(self, m):
            print(m)
            message = json.loads(str(m))
            try:
                if message["r"] == "sensors":
                    bridge_sensor_id = bridge_config["deconz"]["sensors"][message["id"]]["bridgeid"]
                    if "state" in message:
                        bridge_config["sensors"][bridge_sensor_id]["state"].update(message["state"])
                        for key in message["state"].iterkeys():
                            sensors_state[bridge_sensor_id]["state"][key] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
                        rulesProcessor(bridge_sensor_id)
                        if "buttonevent" in message["state"]:
                            if message["state"]["buttonevent"] in [2001, 3001, 4001, 5001]:
                                Thread(target=longPressButton, args=[bridge_sensor_id, message["state"]["buttonevent"]]).start()
                    elif "config" in message:
                        bridge_config["sensors"][bridge_sensor_id]["config"].update(message["config"])

            except:
                print("unable to process the request" + m)

    try:
        ws = EchoClient('ws://127.0.0.1:' + str(bridge_config["deconz"]["websocketport"]))
        ws.connect()
        ws.run_forever()
    except KeyboardInterrupt:
        ws.close()

def scanDeconz():
    if bridge_config["deconz"]["enabled"]:
        if "port" in bridge_config["deconz"]:
            port = bridge_config["deconz"]["port"]
        else:
            port = 8080

        if "username" not in bridge_config["deconz"]:
            try:
                registration = json.loads(sendRequest("http://127.0.0.1:" + str(port) + "/api", "POST", "{\"username\": \"283145a4e198cc6535\", \"devicetype\":\"Hue Emulator\"}"))
            except:
                print("registration fail, is the link button pressed?")
                return
            if "success" in registration[0]:
                bridge_config["deconz"]["username"] = registration[0]["success"]["username"]
        deconz_config = json.loads(sendRequest("http://127.0.0.1:" + str(port) + "/api/" + bridge_config["deconz"]["username"] + "/config", "GET", "{}"))
        bridge_config["deconz"]["websocketport"] = deconz_config["websocketport"]
        registered_deconz_lights = []
        for light in bridge_config["lights_address"]:
            if bridge_config["lights_address"][light]["protocol"] == "deconz":
                registered_deconz_lights.append( bridge_config["lights_address"][light]["light_id"] )
        deconz_lights = json.loads(sendRequest("http://127.0.0.1:" + str(port) + "/api/" + bridge_config["deconz"]["username"] + "/lights", "GET", "{}"))
        for light in deconz_lights:
            if light not in registered_deconz_lights:
                new_light_id = nextFreeId("lights")
                print("register new light " + new_light_id)
                bridge_config["lights"][new_light_id] = deconz_lights[light]
                bridge_config["lights_address"][new_light_id] = {"username": bridge_config["deconz"]["username"], "light_id": light, "ip": "127.0.0.1:" + str(port), "protocol": "deconz"}
        deconz_sensors = json.loads(sendRequest("http://127.0.0.1:" + str(port) + "/api/" + bridge_config["deconz"]["username"] + "/sensors", "GET", "{}"))
        for sensor in deconz_sensors:
            if sensor not in bridge_config["deconz"]["sensors"]:
                new_sensor_id = nextFreeId("sensors")
                if deconz_sensors[sensor]["modelid"] == "TRADFRI remote control":
                    print("register TRADFRI remote control")
                    bridge_config["sensors"][new_sensor_id] = {"config": deconz_sensors[sensor]["config"], "manufacturername": deconz_sensors[sensor]["manufacturername"], "modelid": deconz_sensors[sensor]["modelid"], "name": deconz_sensors[sensor]["name"], "state": deconz_sensors[sensor]["state"], "swversion": deconz_sensors[sensor]["swversion"], "type": deconz_sensors[sensor]["type"], "uniqueid": deconz_sensors[sensor]["uniqueid"]}
                    bridge_config["deconz"]["sensors"][sensor] = {"bridgeid": new_sensor_id}
                elif deconz_sensors[sensor]["modelid"] == "TRADFRI motion sensor":
                    print("register TRADFRI remote control as Philips Motion Sensor")
                    newMotionSensorId = addHueMotionSensor()
                    bridge_config["deconz"]["sensors"][sensor] = {"bridgeid": newMotionSensorId}





def description():
    return """<root xmlns=\"urn:schemas-upnp-org:device-1-0\">
<specVersion>
<major>1</major>
<minor>0</minor>
</specVersion>
<URLBase>http://""" + getIpAddress() + """:80/</URLBase>
<device>
<deviceType>urn:schemas-upnp-org:device:Basic:1</deviceType>
<friendlyName>Philips hue</friendlyName>
<manufacturer>Royal Philips Electronics</manufacturer>
<manufacturerURL>http://www.philips.com</manufacturerURL>
<modelDescription>Philips hue Personal Wireless Lighting</modelDescription>
<modelName>Philips hue bridge 2015</modelName>
<modelNumber>BSB002</modelNumber>
<modelURL>http://www.meethue.com</modelURL>
<serialNumber>""" + mac.upper() + """</serialNumber>
<UDN>MYUUID</UDN>
<presentationURL>index.html</presentationURL>
<iconList>
<icon>
<mimetype>image/png</mimetype>
<height>48</height>
<width>48</width>
<depth>24</depth>
<url>hue_logo_0.png</url>
</icon>
<icon>
<mimetype>image/png</mimetype>
<height>120</height>
<width>120</width>
<depth>24</depth>
<url>hue_logo_3.png</url>
</icon>
</iconList>
</device>
</root>"""

def webformTradfri():
    return """<!doctype html>
<html>
<head>
<meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
<title>Tradfri Setup</title>
<link rel=\"stylesheet\" href=\"https://unpkg.com/purecss@0.6.2/build/pure-min.css\">
</head>
<body>
<form class=\"pure-form pure-form-aligned\" action=\"\" method=\"get\">
<fieldset>
<legend>Tradfri Setup</legend>
<div class=\"pure-control-group\"><label for=\"ip\">Bridge IP</label><input id=\"ip\" name=\"ip\" type=\"text\" placeholder=\"168.168.xxx.xxx\"></div>
<div class=\"pure-control-group\"><label for=\"code\">Security Code</label><input id=\"code\" name=\"code\" type=\"text\" placeholder=\"1a2b3c4d5e6f7g8h\"></div>
<div class=\"pure-controls\"><label for=\"cb\" class=\"pure-checkbox\"></label><button type=\"submit\" class=\"pure-button pure-button-primary\">Save</button></div>
</fieldset>
</form>
</body>
</html>"""

def webformIndex():
    content = """<!doctype html>
<html>
<head>
<meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
<title>Deconz Setup</title>
<link rel=\"stylesheet\" href=\"https://unpkg.com/purecss@0.6.2/build/pure-min.css\">
</head>
<body>
<form class=\"pure-form pure-form-aligned\" action=\"\" method=\"get\">
<fieldset>
<legend>Deconz Switches Setup</legend>\n"""
    for deconzSensor in bridge_config["deconz"]["sensors"].iterkeys():
        if bridge_config["sensors"][bridge_config["deconz"]["sensors"][deconzSensor]["bridgeid"]]["modelid"] == "TRADFRI remote control":
            content += "<div class=\"pure-control-group\">\n"
            content += "<label for=\"" + deconzSensor + "\">" + bridge_config["sensors"][bridge_config["deconz"]["sensors"][deconzSensor]["bridgeid"]]["name"] + "</label>\n"
            content += "<select id=\"" + deconzSensor + "\" name=\"" + bridge_config["deconz"]["sensors"][deconzSensor]["bridgeid"] + "\">\n"
            for group in bridge_config["groups"].iterkeys():
                content += "<option value=\"" + group + "\">" + bridge_config["groups"][group]["name"] + "</option>\n"
            content += "</select>\n"
            content += "</div>\n"
    content += """<div class="pure-controls">
<button type=\"submit\" class=\"pure-button pure-button-primary\">Save</button></div>
</div>
</fieldset>
</form>
</body>
</html>"""
    return content


def webform_milight():
    return """<!doctype html>
<html>
<head>
<meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
<title>Milight Setup</title>
<link rel=\"stylesheet\" href=\"https://unpkg.com/purecss@0.6.2/build/pure-min.css\">
</head>
<body>
<form class=\"pure-form pure-form-aligned\" action=\"\" method=\"get\">
<fieldset>
<legend>Milight Setup</legend>
<div class=\"pure-control-group\"><label for=\"ip\">Hub ip</label><input id=\"ip\" name=\"ip\" type=\"text\" placeholder=\"168.168.xxx.xxx\"></div>
<div class=\"pure-control-group\"><label for=\"device_id\">Device id</label><input id=\"device_id\" name=\"device_id\" type=\"text\" placeholder=\"0x1234\"></div>
<div class=\"pure-control-group\">
<label for=\"mode\">Mode</label>
<select id=\"mode\" name=\"mode\">
<option value=\"rgbw\">RGBW</option>
<option value=\"cct\">CCT</option>
<option value=\"rgb_cct\">RGB+CCT</option>
<option value=\"rgb\">RGB</option>
</select>
</div>
<div class=\"pure-control-group\">
<label for=\"group\">Group</label>
<select id=\"group\" name=\"group\">
<option value=\"1\">1</option>
<option value=\"2\">2</option>
<option value=\"3\">3</option>
<option value=\"4\">4</option>
</select>
</div>
<div class=\"pure-controls\"><button type=\"submit\" class=\"pure-button pure-button-primary\">Save</button></div>
</fieldset>
</form>
</body>
</html>"""

def webform_hue():
    return """<!doctype html>
<html>
<head>
<meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
<title>Hue Bridge Setup</title>
<link rel=\"stylesheet\" href=\"https://unpkg.com/purecss@0.6.2/build/pure-min.css\">
</head>
<body>
<form class=\"pure-form pure-form-aligned\" action=\"\" method=\"get\">
<fieldset>
<legend>Hue Bridge Setup</legend>
<div class=\"pure-control-group\"><label for=\"ip\">Hub ip</label><input id=\"ip\" name=\"ip\" type=\"text\" placeholder=\"168.168.xxx.xxx\"></div>
<div class=\"pure-controls\">
<label class="pure-checkbox">
First press the link button on Hue Bridge
</label>
<button type=\"submit\" class=\"pure-button pure-button-primary\">Save</button></div>
</fieldset>
</form>
</body>
</html>"""


def updateAllLights():
    ## apply last state on startup to all bulbs, usefull if there was a power outage
    for light in bridge_config["lights_address"]:
        payload = {}
        payload["on"] = bridge_config["lights"][light]["state"]["on"]
        payload["bri"] = bridge_config["lights"][light]["state"]["bri"]
        if "colormode" in bridge_config["lights"][light]["state"]:
            if bridge_config["lights"][light]["state"]["colormode"] in ["xy", "ct"]:
                payload[bridge_config["lights"][light]["state"]["colormode"]] = bridge_config["lights"][light]["state"][bridge_config["lights"][light]["state"]["colormode"]]
            elif bridge_config["lights"][light]["state"]["colormode"] == "" and "hue" in bridge_config["lights"][light]["state"]:
                payload["hue"] = bridge_config["lights"][light]["state"]["hue"]
                payload["sat"] = bridge_config["lights"][light]["state"]["sat"]

        Thread(target=sendLightRequest, args=[light, payload]).start()
        sleep(0.5)
        print("update status for light " + light)

class S(BaseHTTPRequestHandler):
    def _set_headers(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()

    def do_GET(self):
        self._set_headers()
        if self.path == '/description.xml':
            self.wfile.write(description())
        elif self.path == '/favicon.ico':
            self.wfile.write("file not found")
        elif self.path.startswith("/tradfri"): #setup Tradfri gateway
            get_parameters = parse_qs(urlparse(self.path).query)
            if "code" in get_parameters:
                tradri_devices = json.loads(check_output("./coap-client-linux -m get -u \"Client_identity\" -k \"" + get_parameters["code"][0] + "\" \"coaps://" + get_parameters["ip"][0] + ":5684/15001\"", shell=True).split("\n")[3])
                pprint(tradri_devices)
                lights_found = 0
                for device in tradri_devices:
                    device_parameters = json.loads(check_output("./coap-client-linux -m get -u \"Client_identity\" -k \"" + get_parameters["code"][0] + "\" \"coaps://" + get_parameters["ip"][0] + ":5684/15001/" + str(device) +"\"", shell=True).split("\n")[3])
                    if "3311" in device_parameters:
                        lights_found += 1
                        #register new tradfri light
                        print("register tradfi light " + device_parameters["9001"])
                        new_light_id = nextFreeId("lights")
                        bridge_config["lights"][new_light_id] = {"state": {"on": False, "bri": 200, "hue": 0, "sat": 0, "xy": [0.0, 0.0], "ct": 461, "alert": "none", "effect": "none", "colormode": "ct", "reachable": True}, "type": "Extended color light", "name": device_parameters["9001"], "uniqueid": "1234567" + str(device), "modelid": "LLM010", "swversion": "66009461"}
                        new_lights.update({new_light_id: {"name": device_parameters["9001"]}})
                        bridge_config["lights_address"][new_light_id] = {"device_id": device, "security_code": get_parameters["code"][0], "ip": get_parameters["ip"][0], "protocol": "ikea_tradfri"}
                if lights_found == 0:
                    self.wfile.write(webformTradfri() + "<br> No lights where found")
                else:
                    self.wfile.write(webformTradfri() + "<br> " + str(lights_found) + " lights where found")
            else:
                self.wfile.write(webformTradfri())
        elif self.path.startswith("/milight"): #setup milight bulb
            get_parameters = parse_qs(urlparse(self.path).query)
            if "device_id" in get_parameters:
                #register new mi-light
                new_light_id = nextFreeId("lights")
                bridge_config["lights"][new_light_id] = {"state": {"on": False, "bri": 200, "hue": 0, "sat": 0, "xy": [0.0, 0.0], "ct": 461, "alert": "none", "effect": "none", "colormode": "ct", "reachable": True}, "type": "Extended color light", "name": "MiLight " + get_parameters["mode"][0] + " " + get_parameters["device_id"][0], "uniqueid": "1a2b3c4" + str(random.randrange(0, 99)), "modelid": "LCT001", "swversion": "66009461"}
                new_lights.update({new_light_id: {"name": "MiLight " + get_parameters["mode"][0] + " " + get_parameters["device_id"][0]}})
                bridge_config["lights_address"][new_light_id] = {"device_id": get_parameters["device_id"][0], "mode": get_parameters["mode"][0], "group": int(get_parameters["group"][0]), "ip": get_parameters["ip"][0], "protocol": "milight"}
                self.wfile.write(webform_milight() + "<br> Light added")
            else:
                self.wfile.write(webform_milight())
        elif self.path.startswith("/hue"): #setup hue bridge
            get_parameters = parse_qs(urlparse(self.path).query)
            if "ip" in get_parameters:
                response = json.loads(sendRequest("http://" + get_parameters["ip"][0] + "/api/", "POST", "{\"devicetype\":\"Hue Emulator\"}"))
                if "success" in response[0]:
                    hue_lights = json.loads(sendRequest("http://" + get_parameters["ip"][0] + "/api/" + response[0]["success"]["username"] + "/lights", "GET", "{}"))
                    lights_found = 0
                    for hue_light in hue_lights:
                        new_light_id = nextFreeId("lights")
                        bridge_config["lights"][new_light_id] = hue_lights[hue_light]
                        bridge_config["lights_address"][new_light_id] = {"username": response[0]["success"]["username"], "light_id": hue_light, "ip": get_parameters["ip"][0], "protocol": "hue"}
                        lights_found += 1
                    if lights_found == 0:
                        self.wfile.write(webform_hue() + "<br> No lights where found")
                    else:
                        self.wfile.write(webform_hue() + "<br> " + str(lights_found) + " lights where found")
                else:
                    self.wfile.write(webform_hue() + "<br> unable to connect to hue bridge")
            else:
                self.wfile.write(webform_hue())
        elif self.path.startswith("/deconz"): #setup imported deconz sensors
            get_parameters = parse_qs(urlparse(self.path).query)
            pprint(get_parameters)
            #clean all rules related to deconz Switches
            sensorsResourcelinks = []
            if get_parameters:
                for resourcelink in bridge_config["resourcelinks"].iterkeys():
                    if bridge_config["resourcelinks"][resourcelink]["classid"] == 15555:
                        sensorsResourcelinks.append(resourcelink)
                        for link in bridge_config["resourcelinks"][resourcelink]["links"]:
                            pices = link.split('/')
                            if pices[1] == "rules":
                                try:
                                    del bridge_config["rules"][pices[2]]
                                except:
                                    print("unable to delete the rule " + pices[2])
                for resourcelink in sensorsResourcelinks:
                    del bridge_config["resourcelinks"][resourcelink]
                for key in get_parameters.iterkeys():
                    addTradfriRemote(key, get_parameters[key][0])
            else:
                scanDeconz()
            self.wfile.write(webformIndex())
        elif self.path.startswith("/switch"): #request from an ESP8266 switch or sensor
            get_parameters = parse_qs(urlparse(self.path).query)
            pprint(get_parameters)
            if "devicetype" in get_parameters: #register device request
                sensor_is_new = True
                for sensor in bridge_config["sensors"]:
                    if bridge_config["sensors"][sensor]["uniqueid"].startswith(get_parameters["mac"][0]): # if sensor is already present
                        sensor_is_new = False
                if sensor_is_new:
                    print("registering new sensor " + get_parameters["devicetype"][0])
                    new_sensor_id = nextFreeId("sensors")
                    if get_parameters["devicetype"][0] == "ZLLSwitch" or get_parameters["devicetype"][0] == "ZGPSwitch":
                        print("ZLLSwitch")
                        bridge_config["sensors"][new_sensor_id] = {"state": {"buttonevent": 0, "lastupdated": "none"}, "config": {"on": True, "battery": 100, "reachable": True}, "name": "Dimmer Switch" if get_parameters["devicetype"][0] == "ZLLSwitch" else "Tap Switch", "type": get_parameters["devicetype"][0], "modelid": "RWL021" if get_parameters["devicetype"][0] == "ZLLSwitch" else "ZGPSWITCH", "manufacturername": "Philips", "swversion": "5.45.1.17846" if get_parameters["devicetype"][0] == "ZLLSwitch" else "", "uniqueid": get_parameters["mac"][0]}
                    elif get_parameters["devicetype"][0] == "ZLLPresence":
                        print("ZLLPresence")
                        addHueMotionSensor()
                    generateSensorsState()
            else: #switch action request
                for sensor in bridge_config["sensors"]:
                    if bridge_config["sensors"][sensor]["uniqueid"].startswith(get_parameters["mac"][0]) and bridge_config["sensors"][sensor]["config"]["on"]: #match senser id based on mac address
                        print("match sensor " + str(sensor))
                        if bridge_config["sensors"][sensor]["type"] == "ZLLSwitch" or bridge_config["sensors"][sensor]["type"] == "ZGPSwitch":
                            bridge_config["sensors"][sensor]["state"].update({"buttonevent": get_parameters["button"][0], "lastupdated": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")})
                            sensors_state[sensor]["state"]["lastupdated"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
                            rulesProcessor(sensor)
                        elif bridge_config["sensors"][sensor]["type"] == "ZLLPresence" and "presence" in get_parameters:
                            if str(bridge_config["sensors"][sensor]["state"]["presence"]).lower() != get_parameters["presence"][0]:
                                sensors_state[sensor]["state"]["presence"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
                            bridge_config["sensors"][sensor]["state"].update({"presence": True if get_parameters["presence"][0] == "true" else False, "lastupdated": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")})
                            rulesProcessor(sensor)
                            #if alarm is activ trigger the alarm
                            if "virtual_light" in bridge_config["alarm_config"] and bridge_config["lights"][bridge_config["alarm_config"]["virtual_light"]]["state"]["on"] and bridge_config["sensors"][sensor]["state"]["presence"] == True:
                                sendEmail(bridge_config["sensors"][sensor]["name"])
                                #triger_horn() need development
                        elif bridge_config["sensors"][sensor]["type"] == "ZLLLightLevel" and "lightlevel" in get_parameters:
                            if str(bridge_config["sensors"][sensor]["state"]["dark"]).lower() != get_parameters["dark"][0]:
                                sensors_state[sensor]["state"]["dark"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
                            bridge_config["sensors"][sensor]["state"].update({"lightlevel":int(get_parameters["lightlevel"][0]), "dark":True if get_parameters["dark"][0] == "true" else False, "daylight":True if get_parameters["daylight"][0] == "true" else False, "lastupdated": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")})
                            rulesProcessor(sensor) #process the rules to perform the action configured by application
        else:
            url_pices = self.path.split('/')
            if url_pices[2] in bridge_config["config"]["whitelist"]: #if username is in whitelist
                bridge_config["config"]["UTC"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
                bridge_config["config"]["localtime"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
                if len(url_pices) == 3: #print entire config
                    self.wfile.write(json.dumps({"lights": bridge_config["lights"], "groups": bridge_config["groups"], "config": bridge_config["config"], "scenes": bridge_config["scenes"], "schedules": bridge_config["schedules"], "rules": bridge_config["rules"], "sensors": bridge_config["sensors"], "resourcelinks": bridge_config["resourcelinks"]}))
                elif len(url_pices) == 4: #print specified object config
                    if url_pices[3] == "lights": #add changes from IKEA Tradfri gateway to bridge
                        syncWithLights()
                    self.wfile.write(json.dumps(bridge_config[url_pices[3]]))
                elif len(url_pices) == 5:
                    if url_pices[4] == "new": #return new lights and sensors only
                        new_lights.update({"lastscan": datetime.now().strftime("%Y-%m-%dT%H:%M:%S")})
                        self.wfile.write(json.dumps(new_lights))
                        new_lights.clear()
                    else:
                        self.wfile.write(json.dumps(bridge_config[url_pices[3]][url_pices[4]]))
                elif len(url_pices) == 6:
                    self.wfile.write(json.dumps(bridge_config[url_pices[3]][url_pices[4]][url_pices[5]]))
            elif (url_pices[2] == "nouser" or url_pices[2] == "config"): #used by applications to discover the bridge
                self.wfile.write(json.dumps({"name": bridge_config["config"]["name"],"datastoreversion": 59, "swversion": bridge_config["config"]["swversion"], "apiversion": bridge_config["config"]["apiversion"], "mac": bridge_config["config"]["mac"], "bridgeid": bridge_config["config"]["bridgeid"], "factorynew": False, "modelid": bridge_config["config"]["modelid"]}))
            else: #user is not in whitelist
                self.wfile.write(json.dumps([{"error": {"type": 1, "address": self.path, "description": "unauthorized user" }}]))


    def do_POST(self):
        self._set_headers()
        print ("in post method")
        self.data_string = self.rfile.read(int(self.headers['Content-Length']))
        post_dictionary = json.loads(self.data_string)
        url_pices = self.path.split('/')
        print(self.path)
        print(self.data_string)
        if len(url_pices) == 4: #data was posted to a location
            if url_pices[2] in bridge_config["config"]["whitelist"]:
                if ((url_pices[3] == "lights" or url_pices[3] == "sensors") and not bool(post_dictionary)):
                    #if was a request to scan for lights of sensors
                    Thread(target=scanForLights).start()
                    sleep(7) #give no more than 7 seconds for light scanning (otherwise will face app disconnection timeout)
                    self.wfile.write(json.dumps([{"success": {"/" + url_pices[3]: "Searching for new devices"}}]))
                else: #create object
                    # find the first unused id for new object
                    new_object_id = nextFreeId(url_pices[3])
                    if url_pices[3] == "scenes":
                        post_dictionary.update({"lightstates": {}, "version": 2, "picture": "", "lastupdated": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"), "owner" :url_pices[2]})
                        if "locked" not in post_dictionary:
                            post_dictionary["locked"] = False
                    elif url_pices[3] == "groups":
                        post_dictionary.update({"action": {"on": False}, "state": {"any_on": False, "all_on": False}})
                    elif url_pices[3] == "schedules":
                        post_dictionary.update({"created": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"), "time": post_dictionary["localtime"]})
                        if post_dictionary["localtime"].startswith("PT"):
                            post_dictionary.update({"starttime": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")})
                        if not "status" in post_dictionary:
                            post_dictionary.update({"status": "enabled"})
                    elif url_pices[3] == "rules":
                        post_dictionary.update({"owner": url_pices[2], "lasttriggered" : "none", "creationtime": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"), "timestriggered": 0})
                        if not "status" in post_dictionary:
                            post_dictionary.update({"status": "enabled"})
                    elif url_pices[3] == "sensors":
                        if post_dictionary["modelid"] == "PHWA01":
                            post_dictionary.update({"state": {"status": 0}})
                    elif url_pices[3] == "resourcelinks":
                        post_dictionary.update({"owner" :url_pices[2]})
                    generateSensorsState()
                    bridge_config[url_pices[3]][new_object_id] = post_dictionary
                    print(json.dumps([{"success": {"id": new_object_id}}], sort_keys=True, indent=4, separators=(',', ': ')))
                    self.wfile.write(json.dumps([{"success": {"id": new_object_id}}], sort_keys=True, indent=4, separators=(',', ': ')))
            else:
                self.wfile.write(json.dumps([{"error": {"type": 1, "address": self.path, "description": "unauthorized user" }}],sort_keys=True, indent=4, separators=(',', ': ')))
                print(json.dumps([{"error": {"type": 1, "address": self.path, "description": "unauthorized user" }}],sort_keys=True, indent=4, separators=(',', ': ')))
        elif "devicetype" in post_dictionary and bridge_config["config"]["linkbutton"]: #this must be a new device registration
                #create new user hash
                s = hashlib.new('ripemd160', post_dictionary["devicetype"][0]        ).digest()
                username = s.encode('hex')
                bridge_config["config"]["whitelist"][username] = {"last use date": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),"create date": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),"name": post_dictionary["devicetype"]}
                self.wfile.write(json.dumps([{"success": {"username": username}}], sort_keys=True, indent=4, separators=(',', ': ')))
                print(json.dumps([{"success": {"username": username}}], sort_keys=True, indent=4, separators=(',', ': ')))
        self.end_headers()
        saveConfig()

    def do_PUT(self):
        self._set_headers()
        print ("in PUT method")
        self.data_string = self.rfile.read(int(self.headers['Content-Length']))
        print(self.data_string)
        put_dictionary = json.loads(self.data_string)
        url_pices = self.path.split('/')
        if url_pices[2] in bridge_config["config"]["whitelist"]:
            if len(url_pices) == 4:
                bridge_config[url_pices[3]].update(put_dictionary)
                response_location = "/" + url_pices[3] + "/"
            if len(url_pices) == 5:
                if url_pices[3] == "schedules":
                    if "status" in put_dictionary and put_dictionary["status"] == "enabled" and bridge_config["schedules"][url_pices[4]]["localtime"].startswith("PT"):
                        put_dictionary.update({"starttime": (datetime.utcnow()).strftime("%Y-%m-%dT%H:%M:%S")})
                elif url_pices[3] == "scenes":
                    if "storelightstate" in put_dictionary:
                        for light in bridge_config["scenes"][url_pices[4]]["lightstates"]:
                            bridge_config["scenes"][url_pices[4]]["lightstates"][light]["on"] = bridge_config["lights"][light]["state"]["on"]
                            bridge_config["scenes"][url_pices[4]]["lightstates"][light]["bri"] = bridge_config["lights"][light]["state"]["bri"]
                            if "xy" in bridge_config["scenes"][url_pices[4]]["lightstates"][light]:
                                del bridge_config["scenes"][url_pices[4]]["lightstates"][light]["xy"]
                            elif "ct" in bridge_config["scenes"][url_pices[4]]["lightstates"][light]:
                                del bridge_config["scenes"][url_pices[4]]["lightstates"][light]["ct"]
                            elif "hue" in bridge_config["scenes"][url_pices[4]]["lightstates"][light]:
                                del bridge_config["scenes"][url_pices[4]]["lightstates"][light]["hue"]
                                del bridge_config["scenes"][url_pices[4]]["lightstates"][light]["sat"]
                            if bridge_config["lights"][light]["state"]["colormode"] in ["ct", "xy"]:
                                bridge_config["scenes"][url_pices[4]]["lightstates"][light][bridge_config["lights"][light]["state"]["colormode"]] = bridge_config["lights"][light]["state"][bridge_config["lights"][light]["state"]["colormode"]]
                            elif bridge_config["lights"][light]["state"]["colormode"] == "hs":
                                bridge_config["scenes"][url_pices[4]]["lightstates"][light]["hue"] = bridge_config["lights"][light]["state"]["hue"]
                                bridge_config["scenes"][url_pices[4]]["lightstates"][light]["sat"] = bridge_config["lights"][light]["state"]["sat"]

                if url_pices[3] == "sensors":
                    pprint(put_dictionary)
                    for key, value in put_dictionary.iteritems():
                        if type(value) is dict:
                            bridge_config[url_pices[3]][url_pices[4]][key].update(value)
                        else:
                            bridge_config[url_pices[3]][url_pices[4]][key] = value
                    rulesProcessor(url_pices[4])
                else:
                    bridge_config[url_pices[3]][url_pices[4]].update(put_dictionary)
                response_location = "/" + url_pices[3] + "/" + url_pices[4] + "/"
            if len(url_pices) == 6:
                if url_pices[3] == "groups": #state is applied to a group
                    if "scene" in put_dictionary: #if group is 0 and there is a scene applied
                        for light in bridge_config["scenes"][put_dictionary["scene"]]["lights"]:
                            bridge_config["lights"][light]["state"].update(bridge_config["scenes"][put_dictionary["scene"]]["lightstates"][light])
                            if "xy" in bridge_config["scenes"][put_dictionary["scene"]]["lightstates"][light]:
                                bridge_config["lights"][light]["state"]["colormode"] = "xy"
                            elif "ct" in bridge_config["scenes"][put_dictionary["scene"]]["lightstates"][light]:
                                bridge_config["lights"][light]["state"]["colormode"] = "ct"
                            elif "hue" or "sat" in bridge_config["scenes"][put_dictionary["scene"]]["lightstates"][light]:
                                bridge_config["lights"][light]["state"]["colormode"] = "hs"
                            Thread(target=sendLightRequest, args=[light, bridge_config["scenes"][put_dictionary["scene"]]["lightstates"][light]]).start()
                            updateGroupStats(light)
                    elif "bri_inc" in put_dictionary:
                        bridge_config["groups"][url_pices[4]]["action"]["bri"] += int(put_dictionary["bri_inc"])
                        if bridge_config["groups"][url_pices[4]]["action"]["bri"] > 254:
                            bridge_config["groups"][url_pices[4]]["action"]["bri"] = 254
                        elif bridge_config["groups"][url_pices[4]]["action"]["bri"] < 1:
                            bridge_config["groups"][url_pices[4]]["action"]["bri"] = 1
                        bridge_config["groups"][url_pices[4]]["state"]["bri"] = bridge_config["groups"][url_pices[4]]["action"]["bri"]
                        del put_dictionary["bri_inc"]
                        put_dictionary.update({"bri": bridge_config["groups"][url_pices[4]]["action"]["bri"]})
                        for light in bridge_config["groups"][url_pices[4]]["lights"]:
                            bridge_config["lights"][light]["state"].update(put_dictionary)
                            Thread(target=sendLightRequest, args=[light, put_dictionary]).start()
                    elif "ct_inc" in put_dictionary:
                        bridge_config["groups"][url_pices[4]]["action"]["ct"] += int(put_dictionary["ct_inc"])
                        if bridge_config["groups"][url_pices[4]]["action"]["ct"] > 500:
                            bridge_config["groups"][url_pices[4]]["action"]["ct"] = 500
                        elif bridge_config["groups"][url_pices[4]]["action"]["ct"] < 153:
                            bridge_config["groups"][url_pices[4]]["action"]["ct"] = 153
                        bridge_config["groups"][url_pices[4]]["state"]["ct"] = bridge_config["groups"][url_pices[4]]["action"]["ct"]
                        del put_dictionary["ct_inc"]
                        put_dictionary.update({"ct": bridge_config["groups"][url_pices[4]]["action"]["ct"]})
                        for light in bridge_config["groups"][url_pices[4]]["lights"]:
                            bridge_config["lights"][light]["state"].update(put_dictionary)
                            Thread(target=sendLightRequest, args=[light, put_dictionary]).start()
                    elif url_pices[4] == "0":
                        for light in bridge_config["lights"].iterkeys():
                            bridge_config["lights"][light]["state"].update(put_dictionary)
                            Thread(target=sendLightRequest, args=[light, put_dictionary]).start()
                        for group in bridge_config["groups"].iterkeys():
                            bridge_config["groups"][group][url_pices[5]].update(put_dictionary)
                            if "on" in put_dictionary:
                                bridge_config["groups"][group]["state"]["any_on"] = put_dictionary["on"]
                                bridge_config["groups"][group]["state"]["all_on"] = put_dictionary["on"]
                    else: # the state is applied to particular group (url_pices[4])
                        if "on" in put_dictionary:
                            bridge_config["groups"][url_pices[4]]["state"]["any_on"] = put_dictionary["on"]
                            bridge_config["groups"][url_pices[4]]["state"]["all_on"] = put_dictionary["on"]
                        for light in bridge_config["groups"][url_pices[4]]["lights"]:
                                bridge_config["lights"][light]["state"].update(put_dictionary)
                                Thread(target=sendLightRequest, args=[light, put_dictionary]).start()
                elif url_pices[3] == "lights": #state is applied to a light
                    Thread(target=sendLightRequest, args=[url_pices[4], put_dictionary]).start()
                    for key in put_dictionary.iterkeys():
                        if key in ["ct", "xy"]: #colormode must be set by bridge
                            bridge_config["lights"][url_pices[4]]["state"]["colormode"] = key
                        elif key in ["hue", "sat"]:
                            bridge_config["lights"][url_pices[4]]["state"]["colormode"] = "hs"
                    updateGroupStats(url_pices[4])
                if not url_pices[4] == "0": #group 0 is virtual, must not be saved in bridge configuration
                    try:
                        bridge_config[url_pices[3]][url_pices[4]][url_pices[5]].update(put_dictionary)
                    except KeyError:
                        bridge_config[url_pices[3]][url_pices[4]][url_pices[5]] = put_dictionary
                if url_pices[3] == "sensors" and url_pices[5] == "state":
                    for key in put_dictionary.iterkeys():
                        sensors_state[url_pices[4]]["state"].update({key: datetime.now().strftime("%Y-%m-%dT%H:%M:%S")})
                    rulesProcessor(url_pices[4])
                response_location = "/" + url_pices[3] + "/" + url_pices[4] + "/" + url_pices[5] + "/"
            if len(url_pices) == 7:
                try:
                    bridge_config[url_pices[3]][url_pices[4]][url_pices[5]][url_pices[6]].update(put_dictionary)
                except KeyError:
                    bridge_config[url_pices[3]][url_pices[4]][url_pices[5]][url_pices[6]] = put_dictionary
                bridge_config[url_pices[3]][url_pices[4]][url_pices[5]][url_pices[6]] = put_dictionary
                response_location = "/" + url_pices[3] + "/" + url_pices[4] + "/" + url_pices[5] + "/" + url_pices[6] + "/"
            response_dictionary = []
            for key, value in put_dictionary.iteritems():
                response_dictionary.append({"success":{response_location + key: value}})
            self.wfile.write(json.dumps(response_dictionary,sort_keys=True, indent=4, separators=(',', ': ')))
            print(json.dumps(response_dictionary, sort_keys=True, indent=4, separators=(',', ': ')))
        else:
            self.wfile.write(json.dumps([{"error": {"type": 1, "address": self.path, "description": "unauthorized user" }}],sort_keys=True, indent=4, separators=(',', ': ')))

    def do_DELETE(self):
        self._set_headers()
        url_pices = self.path.split('/')
        if url_pices[2] in bridge_config["config"]["whitelist"]:
            if url_pices[3] == "resourcelinks":
                for link in bridge_config["resourcelinks"][url_pices[4]]["links"]:
                    pices = link.split('/')
                    if pices[1] not in ["groups","lights"]:
                        try:
                            del bridge_config[pices[1]][pices[2]]
                            print("delete " + link)
                        except:
                            print(link + " not found, very likely it was already deleted by app")
            del bridge_config[url_pices[3]][url_pices[4]]
            if url_pices[3] == "lights":
                del bridge_config["lights_address"][url_pices[4]]
            self.wfile.write(json.dumps([{"success": "/" + url_pices[3] + "/" + url_pices[4] + " deleted."}]))

def run(server_class=HTTPServer, handler_class=S):
    server_address = ('', 80)
    httpd = server_class(server_address, handler_class)
    print ('Starting httpd...')
    httpd.serve_forever()

if __name__ == "__main__":
    if bridge_config["deconz"]["enabled"]:
        scanDeconz()
        Thread(target=websocketClient).start()
    try:
        updateAllLights()
        Thread(target=ssdpSearch).start()
        Thread(target=ssdpBroadcast).start()
        Thread(target=schedulerProcessor).start()
        run()
    except:
        print("server stopped")
    finally:
        run_service = False
        saveConfig()
        print ('config saved')
