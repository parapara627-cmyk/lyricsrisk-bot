import csv
import re

def load_dictionary():
    words = []
    with open("dictionary.csv", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            words.append(row)
    return words

def check_text(text):
    text = text.lower()
    dictionary = load_dictionary()
    results = []

    for entry in dictionary:
        term = entry["term"]
        match_type = entry["match_type"]

        if match_type == "regex":
            if re.search(term, text):
                results.append(entry)
        else:
            if term.lower() in text:
                results.append(entry)

    return results

if __name__ == "__main__":
    test_text = input("Вставь текст:\n")
    matches = check_text(test_text)

    print("\nНайдено совпадений:", len(matches))
    for m in matches:
        print("-", m["term"], "|", m["category"])
