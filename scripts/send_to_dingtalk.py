#!/usr/bin/env python3
"""
发送消息到钉钉机器人
用法: cat report.txt | python3 scripts/send_to_dingtalk.py
从 config/settings.yaml 读取 webhook 地址
"""

import sys
import re
import requests


def get_webhook():
    with open("/Users/tianye/Documents/a_stock_monitor/config/settings.yaml") as f:
        content = f.read()
    m = re.search(r"dingtalk_webhook:\s*(.+)", content)
    if not m:
        print("ERROR: dingtalk_webhook not found in settings.yaml")
        sys.exit(1)
    return m.group(1).strip().strip("'\"")


def main():
    text = sys.stdin.read().strip()
    if not text:
        print("No input, skipping")
        return

    webhook = get_webhook()
    payload = {"msgtype": "text", "text": {"content": text}}
    r = requests.post(webhook, json=payload, timeout=15)
    result = r.json()
    code = result.get("errcode", -1)
    print(f"DingTalk: errcode={code}, errmsg={result.get('errmsg', '')}")
    if code != 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
