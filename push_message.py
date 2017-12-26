# -*- coding: utf-8 -*-
import requests
import json
from cookielib import CookieJar


class PushMessage:
    PUSHED_URL = "https://api.pushed.co/1/push"
    PUSHBULLET_URL = "https://api.pushbullet.com/v2/pushes"
    CONFIG_FILE = "./config.json"

    def __init__(self):
        self.cookies = CookieJar()
        self.config = json.load(open(self.CONFIG_FILE, 'r'))

    def send_pushed(self, msg):
        if len(msg) > 140:
            raise Exception("Message is too long")

        r = requests.post(self.PUSHED_URL, data={
            'app_key': self.config['pushed']['app_key'],
            'app_secret': self.config['pushed']['app_secret'],
            'content': msg,
            'target_type': 'app'
        }, headers={
            'Content-Type': 'application/json'
        })

        response = r.json()
        if 'error' in response:
            return {
                'result': 'error',
                'error': response['error']
            }
        else:
            return {
                'result': 'success',
                'response': response['response']
            }

    def send_pushbullet(self, msg, title="", device=False, channel=False):
        if device and channel:
            raise
        payload = {
            'body': msg,
            'type': 'note',
        }
        if device:
            payload["device_iden"] = self.config["pushbullet"]["device"]
        if channel:
            payload["channel_tag"] = self.config["pushbullet"]["channel"]
        if title:
            payload["title"] = title

        r = requests.post(self.PUSHBULLET_URL, data=json.dumps(payload), headers={
            'Content-Type': 'application/json',
            'Access-Token': self.config["pushbullet"]["token"]
        })
        response = r.json()

        if 'error' in response:
            return {
                'result': 'error',
                'response': response
            }
        else:
            return {
                'result': 'success',
                'response': response
            }

    def push(self, msg, title=""):
        platform = self.config["platform"]
        if platform == "pushed":
            msg = (title + " " + msg) if title else msg
            return self.send_pushed(msg)
        elif platform == "pushbullet":
            push_mode = self.config["pushbullet"]["push"]
            channel, device = False, False
            if push_mode == "channel":
                channel = True
            elif push_mode == "device":
                device = True
            return self.send_pushbullet(msg, title, channel=channel, device=device)
