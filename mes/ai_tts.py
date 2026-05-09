
# make_video_tts
# sk_d24927bc526acbf1e1e6c1664fe9dbb4c9b697395ef879ce

import requests

headers = {"xi-api-key": "sk_d24927bc526acbf1e1e6c1664fe9dbb4c9b697395ef879ce"}
response = requests.get("https://api.elevenlabs.io/v1/voices", headers=headers)


def text_to_speech(api_key, text, voice_id="21m00Tcm4TlvDq8ikWAM", output_file="output.mp3"):
    # API 端点
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

    # 请求头
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "accept": "audio/mpeg"  # 指定输出为 MP3
    }

    # 请求数据
    data = {
        "text": text,
        "voice_settings": {
            "stability": 0.5,  # 语音稳定性（0~1，数值越低越随机）
            "similarity_boost": 0.8  # 发音清晰度（0~1，数值越高越清晰）
        }
    }

    # 发送请求
    response = requests.post(url, json=data, headers=headers)

    # 处理响应
    if response.status_code == 200:
        with open(output_file, "wb") as f:
            f.write(response.content)
        print(f"语音已保存至 {output_file}")
    else:
        print(f"请求失败，状态码：{response.status_code}, 错误信息：{response.text}")


def list_voices(api_key):
    url = "https://api.elevenlabs.io/v2/voices?include_total_count=true"
    headers = {"xi-api-key": api_key}
    params = {
        "include_total_count": True,
        "page": 1,
        "page_size": 100,
        "enable_language_verification": True,
    }
    response = requests.get(url, headers=headers, params=params)

    if response.status_code == 200:
        data = response.json()
        print("total_count", data.get("total_count"), len(data.get("voices")))
        # 筛选支持日语的发音人
        japanese_speakers = []
        voice_list = []
        for voice in data.get("voices"):
            voice_dict = {}

            # 检查verified_languages字段
            voice_dict["id"] = voice.get('voice_id')
            voice_dict["名称"] = voice.get('name')
            voice_dict["基础语言"] = voice.get('fine_tuning').get("language")
            if isinstance(voice.get("high_quality_base_model_ids"), list):
                if "eleven_multilingual_v2" in voice.get("high_quality_base_model_ids"):
                    voice_dict["多语言支持"] = "支持"
                else:
                    voice_dict["多语言支持"] = "不支持"
                    print("不支持", voice.get('name'))
                    voice.get("high_quality_base_model_ids")
            else:
                voice_dict["多语言支持"] = "未知"
            voice_dict["地区语音支持"] = voice.get("labels").get("accent")
            print(voice.get("labels").get("accent"))

            voice_list.append(voice_dict)

            if isinstance(voice.get("labels"), dict):
                if voice.get("labels").get('language'):
                    labels = voice.get("labels")
                    # print(labels.get('language'))
                elif isinstance(voice.get("sharing"), dict):
                    labels = voice.get("sharing").get("labels")
                    # print(labels.get('language'))
        print(str(voice_list))
        print(len(voice_list))
        for voice in voice_list:
            # if voice["基础语言"] != "en":
            print(voice)
        # 打印结果
        print(f"找到 {len(japanese_speakers)} 个日语发音人：")
        for idx, speaker in enumerate(japanese_speakers, 1):
            print(f"\n{idx}. 名称: {speaker['name']}")
            print(f"   Voice ID: {speaker['voice_id']}")
            print(f"   模型ID: {speaker['model_id']}")
            print(f"   试听链接: {speaker['preview_url']}")
    else:
        print(f"请求失败: {response.text}")


def list_english_voices(api_key):
    url = "https://api.elevenlabs.io/v1/voices"
    headers = {"xi-api-key": api_key}
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        voices = response.json()["voices"]
        # 筛选支持日语的发音人
        japanese_speakers = []

        for voice in voices:
            # 检查verified_languages字段
            if isinstance(voice.get("verified_languages"), list):
                for lang_info in voice["verified_languages"]:
                    if lang_info.get("language") == "ja":
                        japanese_speakers.append({
                            "name": voice["name"],
                            "voice_id": voice["voice_id"],
                            "preview_url": lang_info["preview_url"],
                            "model_id": lang_info["model_id"]
                        })
                        break  # 找到日语即停止检查该voice

        # 打印结果
        print(f"找到 {len(japanese_speakers)} 个日语发音人：")
        for idx, speaker in enumerate(japanese_speakers, 1):
            print(f"\n{idx}. 名称: {speaker['name']}")
            print(f"   Voice ID: {speaker['voice_id']}")
            print(f"   模型ID: {speaker['model_id']}")
            print(f"   试听链接: {speaker['preview_url']}")
    else:
        print("请求失败:", response.text)


# 替换为你的 API Key 和语音 ID
API_KEY = "sk_d24927bc526acbf1e1e6c1664fe9dbb4c9b697395ef879ce"
TEXT = "你好，这是一个 ElevenLabs 文字转语音的测试。"

# 调用函数
# list_english_voices(API_KEY)
# 调用函数
list_voices(API_KEY)
# 调用函数
# text_to_speech(API_KEY, TEXT)

