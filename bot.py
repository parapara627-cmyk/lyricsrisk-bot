import os
import csv
import re
from collections import Counter
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart

BOT_TOKEN = os.getenv("BOT_TOKEN")

# ---------- КНОПКИ ----------
start_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Проверить текст")]],
    resize_keyboard=True
)

again_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Проверить ещё")]],
    resize_keyboard=True
)

# ---------- ЧЕЛОВЕЧЕСКИЕ НАЗВАНИЯ КАТЕГОРИЙ ----------
CATEGORY_LABELS = {
    "substance": "вещество",
    "action": "действие употребления",
    "distribution": "добыча/сбыт",
    "paraphernalia": "атрибутика",
    "context_positive": "нормализация/романтизация",
    "context_negative": "негативный контекст",
    "state": "состояние/эффект",
    "metaphor": "метафора",
}

# ---------- ЗАГРУЗКА СЛОВАРЯ ----------
def load_dictionary():
    items = []
    with open("dictionary.csv", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            term = (row.get("term") or "").strip()
            if not term:
                continue

            match_type = (row.get("match_type") or "word").strip().lower()
            category = (row.get("category") or "unknown").strip()
            risk = (row.get("risk") or "low").strip()
            note = (row.get("note") or "").strip()
            exceptions = (row.get("exceptions") or "").strip()

            try:
                weight = int(row.get("weight") or 0)
            except ValueError:
                weight = 0

            items.append({
                "term": term,
                "match_type": match_type,
                "category": category,
                "risk": risk,
                "weight": weight,
                "note": note,
                "exceptions": exceptions,
            })
    return items

DICTIONARY = load_dictionary()

# ---------- АНАЛИЗ ----------
def normalize(text: str) -> str:
    text = text.lower().replace("ё", "е")
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def exceptions_hit(exceptions: str, context: str) -> bool:
    if not exceptions:
        return False
    parts = [p.strip().lower().replace("ё", "е") for p in exceptions.split("|") if p.strip()]
    ctx = context.lower().replace("ё", "е")
    return any(p in ctx for p in parts)

def find_hits(text: str):
    t = normalize(text)
    hits = []

    for e in DICTIONARY:
        term = e["term"]
        mt = e["match_type"]

        if mt == "regex":
            pattern = term
        else:
            # word/phrase: границы слова
            pattern = r"\b" + re.escape(term.lower().replace("ё", "е")) + r"\b"

        try:
            for m in re.finditer(pattern, t):
                context = t[max(0, m.start() - 70): min(len(t), m.end() + 70)]
                if exceptions_hit(e.get("exceptions", ""), context):
                    continue

                hits.append({
                    "term": term,                # как в словаре
                    "matched": m.group(0),        # что реально встретилось
                    "category": e["category"],
                    "risk": e["risk"],
                    "weight": e["weight"],
                    "note": e["note"],
                    "start": m.start(),
                })
        except re.error:
            # если regex в словаре кривой — просто пропускаем
            continue

    # дедуп совпадений
    uniq = {}
    for h in hits:
        key = (h["term"], h["start"])
        uniq[key] = h

    return sorted(uniq.values(), key=lambda x: (x["start"], -x["weight"]))

def score_and_reasons(hits):
    total = sum(h["weight"] for h in hits)
    cats = set(h["category"] for h in hits)

    has_substance = "substance" in cats
    has_action = "action" in cats
    has_positive = "context_positive" in cats

    reasons = []

    # Сцена: вещество + действие
    if has_substance and has_action:
        total += 10
        reasons.append("есть сочетание «вещество + действие»")

    # Нормализация: вещество + позитивный маркер
    if has_substance and has_positive:
        total += 6
        reasons.append("есть маркеры нормализации рядом с темой")

    # Плотность/масштаб: много совпадений
    if len(hits) >= 4:
        total += 4
        reasons.append("много совпадений по теме")

    if total >= 25:
        return "ВЫСОКИЙ", total, reasons
    if total >= 10:
        return "СРЕДНИЙ", total, reasons
    if total > 0:
        return "НИЗКИЙ", total, reasons
    return "НЕ ОБНАРУЖЕНО", total, reasons

# ---------- ОТЧЁТ ----------
def build_report(text: str):
    hits = find_hits(text)
    level, total, reasons = score_and_reasons(hits)

    cat_counter = Counter([h["category"] for h in hits])

    lines = []
    lines.append(f"🟥 Уровень риска: {level}")
    lines.append("")
    lines.append(f"📊 Совпадений: {len(hits)} | Балл: {total}")

    if cat_counter:
        lines.append("Категории:")
        for c, n in cat_counter.most_common():
            lines.append(f"— {CATEGORY_LABELS.get(c, c)}: {n}")
        lines.append("")

    if reasons:
        lines.append("📌 Почему так:")
        for r in reasons:
            lines.append(f"— {r}")
        lines.append("")

    if hits:
        lines.append("🔍 Найденные фрагменты:")
        for h in hits[:10]:
            shown = h.get("matched") or h["term"]
            cat = CATEGORY_LABELS.get(h["category"], h["category"])
            note = f" — {h['note']}" if h.get("note") else ""
            lines.append(f"— «{shown}» → {cat}{note}")
        if len(hits) > 10:
            lines.append(f"…ещё совпадений: {len(hits) - 10}")
        lines.append("")
    else:
        lines.append("Совпадений по словарю не найдено.")
        lines.append("")

    # Интерпретация (коротко, без юридических формулировок)
    if level == "ВЫСОКИЙ":
        lines.append("🧠 Текст содержит прямые или множественные чувствительные формулировки.")
        lines.append("⚠️ Перед публикацией стоит сделать дополнительную проверку формулировок.")
    elif level == "СРЕДНИЙ":
        lines.append("🧠 Обнаружены потенциально чувствительные формулировки.")
        lines.append("⚠️ Возможны вопросы при модерации/проверке.")
    elif level == "НИЗКИЙ":
        lines.append("🧠 Найдены отдельные контекстные совпадения.")
        lines.append("⚠️ Риск невысокий, но стоит проверить контекст.")
    else:
        lines.append("🧠 Существенных совпадений по словарю не обнаружено.")

    lines.append("")
    lines.append("📌 Рекомендации:")
    lines.append("• проверь места, где встречаются «вещество + действие»")
    lines.append("• если релиз публичный/коммерческий — сделай финальную проверку текста")
    lines.append("")
    lines.append("🛡 Дисклеймер: справочный автоматический анализ по словарю. Не является юридическим заключением.")

    return "\n".join(lines)

# ---------- TELEGRAM ----------
dp = Dispatcher()

@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "Нажми «Проверить текст» и пришли текст трека одним сообщением.",
        reply_markup=start_keyboard
    )

@dp.message(F.text == "Проверить текст")
async def ask_text(message: Message):
    await message.answer("Вставь текст трека одним сообщением.")

@dp.message(F.text == "Проверить ещё")
async def again(message: Message):
    await message.answer("Ок. Пришли новый текст одним сообщением.")

@dp.message(F.text)
async def handle_text(message: Message):
    text = (message.text or "").strip()

    # не обрабатываем короткие сообщения и нажатия кнопок как текст трека
    if text in ("Проверить текст", "Проверить ещё"):
        return
    if len(text) < 20:
        await message.answer("Пришли текст подлиннее (хотя бы 1–2 строки).")
        return

    report = build_report(text)

    if len(report) > 3800:
        report = report[:3800] + "\n…(обрезано по лимиту Telegram)"

    await message.answer(report, reply_markup=again_keyboard)

async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN отсутствует в окружении. Проверь Railway → Variables.")
    bot = Bot(token=BOT_TOKEN)
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
