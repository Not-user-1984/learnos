---
name: youtube-to-summary
description: "YouTube → транскрипт: субтитры через yt-dlp (ru → en), автодетект SOCKS5-прокси, сохранение в data/youtube/<id>.md. Fallback Whisper — пока не реализован."
params:
  url:
    type: str
    desc: ссылка на видео (youtube.com / youtu.be)
version: 0.1
status: active
---

# youtube-to-summary

Порт скилла radmipa `youtube-to-summary` (v0: только субтитры).

1. Автодетект локального SOCKS5 `127.0.0.1:7890` (mihomo) — YouTube через VLESS-нод
2. `yt-dlp --skip-download` субтитры: ручные → авто, `ru → en`
3. VTT/SRT → чистый текст → `data/youtube/<video_id>.md`
4. Возвращает путь + превью (полный текст агент читает из файла по частям)

Нет субтитров → ошибка с подсказкой (Whisper-fallback добавим при наличии ключа/желания).
