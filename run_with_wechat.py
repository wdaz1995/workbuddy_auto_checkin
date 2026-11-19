#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_with_wechat.py

作用：在不改动原项目核心脚本的前提下，把通知改成：
  1. WxPusher 极简推送（推荐，个人微信/手机 App 都能收）
  2. 企业微信群机器人 Webhook（官方、免费，可通过微信插件同步到微信）
  3. 原版飞书机器人（作为兜底）

用法：把本文件放到仓库根目录，并把 workflow 中的
  python wb_auto.py
改成
  python run_with_wechat.py

需要的环境变量（至少配置一个）：
  WXPUSHER_SPT       WxPusher 极简推送 SPT
  WECOM_WEBHOOK      企业微信群机器人 Webhook
  FEISHU_WEBHOOK     飞书机器人 Webhook（原方案）

注意：SPT / Webhook 等同于通知权限，不要写进代码、不要提交到仓库，
只放进 GitHub Secrets。
"""

import html
import json
import os
import ssl
import sys
import urllib.request

import wb_auto

WXPUSHER_URL = "https://wxpusher.zjiecode.com/api/send/message/simple-push"
REQUEST_TIMEOUT = 15


def _post_json(url, payload):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    with urllib.request.urlopen(
        req, timeout=REQUEST_TIMEOUT, context=ssl.create_default_context()
    ) as resp:
        raw = resp.read().decode("utf-8", "replace")
        try:
            return resp.status, json.loads(raw)
        except ValueError:
            return resp.status, {"raw": raw[:300]}


def _build_text(title, checkin_line, buddy_line):
    return "%s\n\n签到：%s\n\n猫猫旅行：%s" % (
        title,
        checkin_line,
        buddy_line,
    )


def _send_wxpusher(spt, title, checkin_line, buddy_line, overall_ok):
    status_text = "成功" if overall_ok else "部分失败"
    summary = ("WorkBuddy " + status_text)[:100]
    content = (
        "<h3>%s</h3>"
        "<p><b>签到</b><br>%s</p>"
        "<p><b>猫猫旅行</b><br>%s</p>"
        "<p>整体：%s</p>"
    ) % (
        html.escape(title),
        html.escape(checkin_line),
        html.escape(buddy_line),
        html.escape(status_text),
    )
    payload = {
        "spt": spt,
        "content": content,
        "summary": summary,
        "contentType": 2,
    }
    try:
        code, body = _post_json(WXPUSHER_URL, payload)
        ok = code == 200 and body.get("code") == 1000
        reason = "" if ok else "WxPusher HTTP %s，返回 %s" % (code, body)
    except Exception as e:
        ok, reason = False, "WxPusher 请求异常：%s: %s" % (type(e).__name__, e)
    print("  [微信] WxPusher %s" % ("发送成功" if ok else reason), flush=True)
    return ok, reason


def _send_wecom(webhook, title, checkin_line, buddy_line, overall_ok):
    status_text = "成功" if overall_ok else "部分失败"
    # 用 text 而不是 markdown：企业微信的 markdown 消息同步到个人微信时会显示
    # “暂不支持此消息类型”，纯文本才能同时在企业微信和个人微信正常显示。
    content = (
        "%s\n"
        "整体：%s\n\n"
        "签到：%s\n\n"
        "猫猫旅行：%s"
    ) % (title, status_text, checkin_line, buddy_line)
    payload = {
        "msgtype": "text",
        "text": {"content": content},
    }
    try:
        code, body = _post_json(webhook, payload)
        ok = code == 200 and body.get("errcode") == 0
        reason = "" if ok else "企业微信 HTTP %s，返回 %s" % (code, body)
    except Exception as e:
        ok, reason = False, "企业微信请求异常：%s: %s" % (type(e).__name__, e)
    print("  [微信] 企业微信机器人 %s" % ("发送成功" if ok else reason), flush=True)
    return ok, reason


def patched_push(webhook, title, checkin_line, buddy_line, overall_ok):
    """保持与 wb_auto.push_feishu 相同签名，让原脚本无需改动即可调用。

    通道优先级：
      1. 若设置 NOTIFY_CHANNEL=wecom，强制走企业微信（即使同时存在 WXPUSHER_SPT）
      2. 否则 WXPUSHER_SPT > WECOM_WEBHOOK > 飞书
    """
    channel = (os.environ.get("NOTIFY_CHANNEL") or "").strip().lower()

    if channel in ("wecom", "wechat_work", "qywx"):
        wecom_webhook = os.environ.get("WECOM_WEBHOOK")
        if not wecom_webhook:
            return False, "已指定企业微信通道，但缺少 Secret WECOM_WEBHOOK"
        return _send_wecom(wecom_webhook, title, checkin_line, buddy_line, overall_ok)

    spt = os.environ.get("WXPUSHER_SPT")
    if spt:
        return _send_wxpusher(spt, title, checkin_line, buddy_line, overall_ok)

    wecom_webhook = os.environ.get("WECOM_WEBHOOK")
    if wecom_webhook:
        return _send_wecom(wecom_webhook, title, checkin_line, buddy_line, overall_ok)

    # 没有配置微信通道时，回退到原版飞书逻辑。
    return wb_auto.push_feishu(webhook, title, checkin_line, buddy_line, overall_ok)


def main():
    # 原脚本只有检测到 FEISHU_WEBHOOK 才会调用通知函数。
    # 这里填一个占位值，让原脚本调用我们替换后的通知函数。
    if not os.environ.get("FEISHU_WEBHOOK"):
        os.environ["FEISHU_WEBHOOK"] = "wechat-notifier-enabled"

    wb_auto.push_feishu = patched_push
    return wb_auto.main()


if __name__ == "__main__":
    sys.exit(main())
