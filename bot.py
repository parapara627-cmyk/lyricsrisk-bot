import os
import csv
import re
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

# ---------- ЗАГРУЗКА СЛОВАРЯ ----------
def load_dictionary():
    items = []
    with open("dictionary.csv", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            term = (row.get("term") or "").strip()
            if not term:
                continue
            row["term"] = term
            row["match_type"] = (row.get("match_type") or "word").strip()
            row["category"] = (row.get("category") or "unknown").strip()
            row["risk"] = (row.get("risk") or "low").strip()
            row["note"] = (row.get("note") or "").strip()
            row["exceptions"] = (row.get("exceptions") or "").strip()
            try:
                row["weight"] = int(row.get("weight") or 0)
            except ValueError:
                row["weight"] = 0
            items.append(row)
    return items

DICTIONARY = load_dictionary()

# ---------- АНАЛИЗ ----------
def normalize(text):
    text = text.lower().replace("ё", "е")
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def exceptions_hit(exceptions, context):
    if not exceptions:
        return False
    parts = [p.strip().lower() for p in exceptions.split("|") if p.strip()]
    return any(p in context for p in parts)

def find_hits(text):
    t = normalize(text)
    hits = []

    for e in DICTIONARY:
        term = e["term"]
        mt = e["match_type"]

        pattern = term if mt == "regex" else r"\b" + re.escape(term.lower()) + r"\b"

        try:
            for m in re.finditer(pattern, t):
                context = t[max(0, m.start()-70): m.end()+70]

                if exceptions_hit(e.get("exceptions"), context):
                    continue

                hits.append({
                    "term": term,
                    "category": e["category"],
                    "risk": e["risk"],
                    "weight": e["weight"],
                    "note": e["note"]
                })
        except:
            continue

    return hits

def score(hits):
    total = sum(h["weight"] for h in hits)
    if total >= 25:
        return "ВЫСОКИЙ", total
    if total >= 10:
        return "СРЕДНИЙ", total
    if total > 0:
        return "НИЗКИЙ", total
    return "НЕ ОБНАРУЖЕНО", total

# ---------- ОТЧЁТ ----------
def build_report(text):
    hits = find_hits(text)
    level, total = score(hits)

    categories = list(set(h["category"] for h in hits))

    report = f"🟥 Уровень риска: {level}\n\n"
    report += f"📊 Совпадений: {len(hits)}\n"
    if categories:
        report += "Категории:\n" + "\n".join(f"— {c}" for c in categories) + "\n\n"

    if hits:
        report += "🔍 Найденные фрагменты:\n"
        for h in hits[:8]:
            report += f"— {h['term']} → {h['category']}\n"
        report += "\n"

    # Интерпретация
    if level == "ВЫСОКИЙ":
        report += "🧠 Текст содержит прямые или множественные чувствительные формулировки.\n\n"
        report += "⚠️ Возможна необходимость дополнительной проверки перед публикацией.\n\n"
    elif level == "СРЕДНИЙ":
        report += "🧠 Обнаружены потенциально чувствительные формулировки.\n\n"
        report += "⚠️ Возможны вопросы при модерации.\n\n"
    elif level == "НИЗКИЙ":
        report += "🧠 Найдены отдельные контекстные совпадения.\n\n"
        report += "⚠️ Вероятность ограничений минимальна.\n\n"
    else:
        report += "🧠 Совпадений не обнаружено.\n\n"

    report += "📌 Рекомендации:\n"
    report += "• проверить контекст формулировок\n"
    report += "• избегать прямых упоминаний веществ\n"
    report += "• обратить внимание на сочетание действий\n\n"

    report += "🛡 Дисклеймер:\n"
    report += "Справочный автоматический анализ по словарю. Не является юридическим заключением."

    return report

# ---------- TELEGRAM ----------
dp = Dispatcher()

@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "Отправьте текст для проверки",
        reply_markup=start_keyboard
    )

@dp.message(F.text == "Проверить текст")
async def ask_text(message: Message):
    await message.answer("Вставьте текст трека")

@dp.message(F.text == "Проверить ещё")
async def again(message: Message):
    await message.answer("Отправьте новый текст")

@dp.message(F.text)
async def handle_text(message: Message):
    text = message.text.strip()

    if len(text) < 10:
        return

    report = build_report(text)

    if len(report) > 3800:
        report = report[:3800]

    await message.answer(report, reply_markup=again_keyboard)

async def main():
    bot = Bot(token=BOT_TOKEN)
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
