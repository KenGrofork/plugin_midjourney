#!/usr/bin/env python
# -*- coding=utf-8 -*-
"""
@time: 2023/4/25 11:46
@Project ：chatgpt-on-wechat
@file: midjourney.py
"""
import json
import os
import time

import requests
from bridge.context import ContextType
from bridge.reply import Reply, ReplyType
from config import conf
import plugins
from plugins import *
from common.log import logger
from common.expired_dict import ExpiredDict


@plugins.register(name="Midjourney", desc="利用midjourney api来画图", desire_priority=1, version="0.1",
                  author="ffwen123")
class Midjourney(Plugin):
    def __init__(self):
        super().__init__()
        curdir = os.path.dirname(__file__)
        config_path = os.path.join(curdir, "config.json")
        self.params_cache = ExpiredDict(60 * 60)
        if not os.path.exists(config_path):
            logger.info('[RP] 配置文件不存在，将使用config.json.template模板')
            config_path = os.path.join(curdir, "config.json.template")
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                self.api_url = config["api_url"]
                self.call_back_url = config["call_back_url"]
                self.headers = config["headers"]
                self.default_params = config["defaults"]
                self.slash_commands_data = config["slash_commands_data"]
                self.mj_api_key = self.headers.get("Authorization", "")
                if "你的API 密钥" in self.mj_api_key or not self.mj_api_key:
                    raise Exception("please set your api key in config or environment variable.")
            self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
            logger.info("[RP] inited")
        except Exception as e:
            if isinstance(e, FileNotFoundError):
                logger.warn(f"[RP] init failed, config.json not found.")
            else:
                logger.warn("[RP] init failed." + str(e))
            raise e

    def on_handle_context(self, e_context: EventContext):

        if e_context['context'].type != ContextType.IMAGE_CREATE:
            return
        logger.debug("[RP] on_handle_context. content: %s" % e_context['context'].content)

        logger.info("[RP] image_query={}".format(e_context['context'].content))
        reply = Reply()
        try:
            content = e_context['context'].content[:]
            # 解析用户输入 如":cat"
            content = content.replace("，", ",").replace("：", ":")
            if ":" in content:
                keywords, prompt = content.split(":", 1)
            else:
                keywords = content
                prompt = ""
            keywords = keywords.split()
            if "help" in keywords or "帮助" in keywords or not prompt:
                reply.type = ReplyType.INFO
                reply.content = self.get_help_text(verbose=True)
            else:
                post_json = {**self.default_params, **{
                    "ref": self.slash_commands_data.get("ref", "fast"),
                    "msg": prompt if prompt else self.slash_commands_data.get("msg", "fast")
                }}
                # 调用midjourney api来画图
                api_data = requests.post(url=self.api_url, headers=self.headers, json=post_json, timeout=120.05)
                if api_data.status_code != 200:
                    time.sleep(2)
                    api_data = requests.post(url=self.api_url, headers=self.headers, json=post_json, timeout=120.05)
                if api_data.status_code == 200:
                    # 调用Webhook URL的响应，来获取图片的URL
                    get_imageUrl = requests.get(url=self.call_back_url, data={"id": api_data.json().get("messageId")},
                                                timeout=120.05)
                    if get_imageUrl.status_code != 200:
                        time.sleep(2)
                        get_imageUrl = requests.get(url=self.call_back_url,
                                                    data={"id": api_data.json().get("messageId")}, timeout=120.05)
                    if get_imageUrl.status_code == 200:
                        if "imageUrl" in get_imageUrl.text:
                            reply.type = ReplyType.IMAGE_URL
                            reply.content = get_imageUrl.json().get("imageUrl")
                        else:
                            reply.type = ReplyType.INFO
                            reply.content = get_imageUrl.text
                        e_context.action = EventAction.BREAK_PASS  # 事件结束后，跳过处理context的默认逻辑，下同
                        e_context['reply'] = reply
                    else:
                        reply.type = ReplyType.ERROR
                        reply.content = "图片URL获取失败"
                        e_context['reply'] = reply
                        logger.error("[RP] get_imageUrl: %s " % get_imageUrl.text)
                        e_context.action = EventAction.BREAK_PASS
                else:
                    reply.type = ReplyType.ERROR
                    reply.content = "画图失败"
                    e_context['reply'] = reply
                    logger.error("[RP] Midjourney API api_data: %s " % api_data.text)
                    e_context.action = EventAction.BREAK_PASS
        except Exception as e:
            reply.type = ReplyType.ERROR
            reply.content = "[RP] " + str(e)
            e_context['reply'] = reply
            logger.exception("[RP] exception: %s" % e)
            e_context.action = EventAction.CONTINUE

    def get_help_text(self, verbose=False, **kwargs):
        if not conf().get('image_create_prefix'):
            return "画图功能未启用"
        else:
            trigger = conf()['image_create_prefix'][0]
        help_text = "利用midjourney api来画图。\n"
        if not verbose:
            return help_text

        help_text += f"使用方法:\n使用\"{trigger}:提示语\"的格式作画，如\"{trigger}:girl\"\n"
        # help_text += "目前可用关键词：\n"
        # for rule in self.rules:
        #     keywords = [f"[{keyword}]" for keyword in rule['keywords']]
        #     help_text += f"{','.join(keywords)}"
        #     if "desc" in rule:
        #         help_text += f"-{rule['desc']}\n"
        #     else:
        #         help_text += "\n"
        return help_text