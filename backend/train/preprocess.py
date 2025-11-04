import json

with open("mentalchat16k.json", "r", encoding="utf-8") as f1:
    d1 = json.load(f1)
with open("intent_mentalhealth.json", "r", encoding="utf-8") as f2:
    d2 = json.load(f2)

merged = []
def normalize(entry):
    user = entry.get("input") or entry.get("user") or entry.get("text") or ""
    assistant = entry.get("output") or entry.get("response") or entry.get("reply") or ""
    return {"question": user.strip(), "answer": assistant.strip()} if user and assistant else None

for data in (d1 if isinstance(d1, list) else d1.get("data", [])):
    norm = normalize(data)
    if norm: merged.append(norm)

for data in (d2 if isinstance(d2, list) else d2.get("data", [])):
    norm = normalize(data)
    if norm: merged.append(norm)

with open("merged_mira.json", "w", encoding="utf-8") as f:
    json.dump(merged, f, indent=2, ensure_ascii=False)

print(f"Merged {len(merged)} records ✅")
