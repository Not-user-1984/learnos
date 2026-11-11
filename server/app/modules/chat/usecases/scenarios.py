"""Сценарии чата: режимы, интенты, ресёрч-директива, агент по разговору (B-009).

Вынесено из chat/service.py без изменения поведения.
"""

MODES = {"free", "quick", "session", "tuning", "root"}
INTENTS = ("review", "study", "session", "quote", "tune", "reinforce")

AGENT_BY_MODE = {
    "free": "free_chat",
    "quick": "quick_reviewer",
    "session": "session_tutor",
    "tuning": "prompt_tuner",
    "root": "root",
}

# Ресёрч как состояние чата: директива видна только агенту (в system_extra),
# пользователь пишет тему как обычное сообщение.
RESEARCH_DIRECTIVE = (
    "Это сообщение запускает ресёрч-цикл по теме пользователя. Найди лучшие источники: "
    "официальные доки, статьи, видео. Ищи вширь (2–3 захода), остановись при повторах. "
    "Прогресс комментируй коротко: что нашёл, что читаешь. Итог — список кандидатов "
    "топ-3–5 с пояснением «почему этот». НИЧЕГО не добавляй в Библиотеку сам: покажи "
    "список и предложи добавление карточкой offer_action (в description — что именно "
    "добавишь). Согласие — «Да» на карточке или ответ с правкой списка («добавь только "
    "первые два», «добавь ещё видео»): добавь именно выбранные источники (kind=web "
    "через add_source + process_source; YouTube — kind=video) и подтверди, что добавил. "
    "Отказ — ничего не добавляй, продолжай по желаниям пользователя. "
    "Для научных/фундаментальных тем зови academic_search: ищет сразу по arXiv + OpenAlex + "
    "Semantic Scholar, у каждой статьи поле provider — упоминай источник находки. "
    "Доступен torrent_fetch (поиск книг/фильмов/музыки по трекерам): если тема — книга или "
    "пользователь просит медиа, покажи кандидатов и спроси, не скачать ли сразу; книги "
    "(cat=books) после загрузки сами попадают в Библиотеку с нарезкой глав."
)
RESEARCH_MAX_STEPS = 30  # цикл «поиск → чтение статей → добавление» не укладывается в дефолтные 12

# Сценарии единого входа (T-039): клиент передаёт код с первым сообщением,
# сервер собирает директиву агенту — видимый текст сообщения остаётся пользователю.
INTENT_DIRECTIVES = {
    "review": (
        "Сценарий «быстрый разбор»: источник и глава — в блоке «Контекст». Прочитай материал "
        "(read_chapter; видео — весь транскрипт, листай offset до конца) и покажи разбор "
        "карточкой show_chapter_review (главное 3–5 пунктов, ключевые понятия, что применимо "
        "пользователю, 1–2 вопроса на подумать; title — глава или название видео), текстом — "
        "2–3 строки сопровождения. Без сессии."
    ),
    "study": (
        "Сценарий «изучение источника»: пользователь начал с карты глав. Формат выбери сам — "
        "быстрый разбор текущей главы или сессия-урок (тогда start_session, сессия привяжется "
        "к разговору, и веди её шагами advance/practice_step/finish_session). После каждой главы "
        "решайте вместе кнопками offer_replies: дальше, подробнее или закрепить "
        "(mark_chapter_done по подтверждению)."
    ),
    "session": (
        "Сценарий «сессия-урок»: сессия уже создана и привязана к разговору (состояние — в "
        "«Контексте»). Веди урок сам: теория по первым понятиям коротко → вопросы фейнмана "
        "по одному → практика под железо из профиля → разбор; шаги — advance/practice_step/"
        "finish_session без session_id, итог — блок-урок."
    ),
    "quote": (
        "Сценарий «разбор фрагмента»: сообщение пользователя — выделенный фрагмент текущей "
        "главы. Объясни, что имеется в виду, сверься с текстом главы (read_chapter), поправь "
        "неточности понимания и свяжи фрагмент с ключевыми понятиями главы."
    ),
    "tune": (
        "Сценарий «настройка агента»: имя агента — в сообщении пользователя. Уточни вопросами, "
        "каким должно быть поведение, и предложи правку промпта карточкой propose_change("
        "kind='prompt', target=<агент>, …) — дифф увидит пользователь, применение по его кнопке."
    ),
    "reinforce": (
        "Сценарий «закрепление пройденного»: возьми очередь повторений (get_review_queue) и "
        "слабые места блоков (search/list_blocks), выбери 3–5 самых созревших или слабых и "
        "проводи короткое повторение по одному; каждый ответ оценивай answer_review."
    ),
}

# handoff (T-050 Э4): интент первого сообщения передаёт разговор специалисту,
# дальше он ведёт по своему промпту — директива больше не «одноразовая вставка»
INTENT_AGENT = {
    "review": "quick_reviewer",
    "session": "session_tutor",
}


def agent_for_conversation(registry, conv: dict) -> str:
    """Кто ведёт разговор: active_agent (handoff/интент), иначе режим (легаси)."""
    active = conv.get("active_agent")
    if active:
        try:
            registry.get(active)
            return active
        except KeyError:
            pass  # агента удалили — падаем обратно на режим, разговор не теряем
    return agent_for_mode(registry, conv["mode"])


def agent_for_mode(registry, mode: str) -> str:
    """Имя агента по режиму разговора: дефолтные режимы — из таблицы, agent:<name> — кастомный."""
    if mode.startswith("agent:"):
        name = mode.split(":", 1)[1]
        try:
            registry.get(name)
            return name
        except KeyError:
            return "free_chat"  # кастомного агента удалили — разговор не теряем
    return AGENT_BY_MODE.get(mode, "free_chat")


def valid_mode(registry, mode: str) -> bool:
    if mode in MODES:
        return True
    if mode.startswith("agent:"):
        try:
            registry.get(mode.split(":", 1)[1])
            return True
        except KeyError:
            return False
    return False


def history_notes(m: dict) -> str:
    """Компактное дополнение сообщения для контекста LLM: карточки и трасса инструментов (R-12)."""
    notes: list[str] = []
    cards = m.get("cards") or []
    for c in cards[:4]:
        kind = c.get("type", "?")
        key = c.get("title") or c.get("task") or c.get("summary") or c.get("path") or ""
        note = f"[карточка {kind}" + (f": {str(key)[:90]}" if key else "") + "]"
        notes.append(note)
    trace = m.get("tool_calls") or []
    if trace:
        done = "; ".join(
            f"{t.get('name')}({'ок' if t.get('ok') else 'ошибка'}: {t.get('summary', '')[:60]})"
            for t in trace[:8]
        )
        notes.append(f"[инструменты: {done}]")
    return ("\n" + " ".join(notes)) if notes else ""


def chapter_label(ch: dict) -> str:
    """Читаемое имя главы: номер книги важнее позиционного idx («Глава 3. Ветвление в Git»)."""
    import re

    title = ch.get("title") or ""
    inner = re.sub(r"^\s*\d+[.)]?\s+", "", title)
    number = ch.get("number")
    if number:
        return f"Глава {number} ({inner or title})"
    return f"глава {ch.get('idx')}. {title}"
