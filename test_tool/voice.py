import pygame.mixer as playing

voice_file_name_dict = {
    "pass": "mp3\\测试通过.mp3",
    "NG": "mp3\\测试失败.mp3",
    "sn_is_used": "mp3\\sn码已使用.mp3",
    "db_error": "mp3\\数据库异常.mp3"
}


def play_voice_init():
    playing.init()


def play_voice(name: str):
    file = voice_file_name_dict.get(name, None)

    if file:
        try:
            playing.music.load(file)  # 加载语音
            playing.music.play()
        except Exception as e:
            print(f"语音播放异常: {str(e)}")




