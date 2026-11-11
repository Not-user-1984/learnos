# YouTube-субтитры (скилл youtube-to-summary)

- Путь: `library/service.py:_run_video` → скилл `youtube-to-summary/run.py` (yt-dlp, только субтитры, таймаут 180 с).
- Прокси: UI → app_settings → xray socks5 → `--proxy` (`research/connectivity.py`). На проде работает.
- **Ловушка:** в automatic_captions дорожки `en`/`ru` часто **переводы** (`tlang`), оригинал — `xx-orig`.
  Переводы YouTube режет 429, а yt-dlp без `--ignore-errors` прерывается на первой ошибке.
  Брать `*-orig` (см. B-001). Пример: YqJ4asgj1R8 — `en-orig` ок, `ru` → 429.
- Список `*-orig` у видео бывает длинным и ложным (bn-orig, nl-orig…); настоящий — тот, чей VTT `Language:` совпадает.
- Ошибка job — в `jobs.error` (`service.py:309`), у `sources` поля ошибки нет (до B-001).
- Whisper-fallback не реализован.
- Локально `yt-dlp --list-subs URL` с мака работает без прокси.
