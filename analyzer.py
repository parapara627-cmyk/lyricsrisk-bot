import csv
import re
from collections import Counter

DICT_FILE = "dictionary.csv"

def _load_dictionary():
    items = []
    with open(DICT_FILE, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            term = (row.get("term") or "").strip()
            if not term:
                continue
            items.append({
                "term": term,
                "match_type": (row.get("match_type") or "word").strip(),
                "category": (row.get("category") or "unknown").strip(),
                "risk": (row.get("risk") or "low").strip(),
                "note": (row.get("note") or "").strip(),
                "exceptions": (row.get("exceptions") or "").strip(),
                "weight": int(row.get("weight") or 0)
            })
    return items

DICTIONARY = _load_dictionary()

def _normalize(text: str) -> str:
    text = text.lower().replace("ё", "е")
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def _exceptions_hit(exceptions: str, context: str) -> bool:
    if not exceptions:
        return False
    parts = [p.strip().lower().replace("ё", "е") for p in exceptions.split("|") if p.strip()]
    ctx = context.lower().replace("ё", "е")
    return any(p in ctx for p in parts)

def _find_hits(text: str):
    t = _normalize(text)
    hits = []
    for e in DICTIONARY:
        term = e["term"]
        mt = e["match_type"]
        pattern = term if mt == "regex" else r"\b" + re.escape(term.lower().replace("ё", "е")) + r"\b"
        try:
            for m in re.finditer(pattern, t):
                left = max(0, m.start() - 70)
                right = min(len(t), m.end() + 70)
                context = t[left:right]
                if _exceptions_hit(e["exceptions"], context):
                    continue
                hits.append({
                    "term": term,
                    "category": e["category"],
                    "risk": e["risk"],
                    "weight": e["weight"],
                    "note": e["note"],
                    "start": m.start()
                })
        except re.error:
            continue

    # дедуп
    uniq = {}
    for h in hits:
        key = (h["term"], h["start"])
        uniq[key] = h
    return sorted(uniq.values(), key=lambda x: (x["start"], -x["weight"]))

def _score(hits):
    total = sum(h["weight"] for h in hits)
    if total >= 25:
        return "ВЫСОКИЙ", total
    if total >= 10:
        return "СРЕДНИЙ", total
    if total > 0:
        return "НИЗКИЙ", total
    return "НЕ ОБНАРУЖЕНО", total

def build_report(text: str, limit: int = 8) -> str:
    hits = _find_hits(text)
    level, total = _score(hits)
    cats = Counter([h["category"] for h in hits])

    lines = []
    lines.append(f"🟥 Уровень риска: {level}")
    lines.append("")
    lines.append(f"📊 Совпадений: {len(hits)} | Балл: {total}")
    if cats:
        lines.append("Категории:")
        for c, n in cats.most_common():
            lines.append(f"— {c}: {n}")
        lines.append("")

    if hits:
        lines.append("🔍 Найденные фрагменты:")
        for h in hits[:limit]:
            note = f" — {h['note']}" if h["note"] else ""
            lines.append(f"— «{h['term']}» → {h['category']}{note}")
        if len(hits) > limit:
            lines.append(f"…ещё совпадений: {len(hits)-limit}")
        lines.append("")
    else:
        lines.append("Совпадений по словарю не найдено.")
        lines.append("")

    if level == "ВЫСОКИЙ":
        lines.append("🧠 Текст содержит прямые или множественные чувствительные формулировки.")
        lines.append("⚠️ Возможна необходимость дополнительной проверки перед публикацией.")
    elif level == "СРЕДНИЙ":
        lines.append("🧠 Обнаружены потенциально чувствительные формулировки.")
        lines.append("⚠️ Возможны вопросы при модерации.")
    elif level == "НИЗКИЙ":
        lines.append("🧠 Найдены отдельные контекстные совпадения.")
        lines.append("⚠️ Вероятность ограничений минимальна.")
    else:
        lines.append("🧠 Совпадений не обнаружено.")

    lines.append("")
    lines.append("📌 Рекомендации:")
    lines.append("• проверить контекст формулировок")
    lines.append("• избегать прямых упоминаний и сочетаний “действие + триггер”")
    lines.append("")
    lines.append("🛡 Дисклеймер: справочный анализ по словарю, не юридическая консультация.")
    return "\n".join(lines)
