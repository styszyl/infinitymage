#!/usr/bin/env python3
import json
import os
import re
import subprocess
import sys
import tempfile
import shutil
from pathlib import Path
from typing import List

BASE = Path(__file__).resolve().parents[1]
SRC_DIR = BASE / 'Infinity Mage Chapters 1-1277 original'
OUT_DIR = BASE / 'pl'
PROGRESS = BASE / 'reader' / 'chapters_pl.json'
GLOSSARY = BASE / 'translation_glossary.md'
GUIDELINES = BASE / 'translation_guidelines.md'

HANGUL_MAP = {
    "천폭": "Cheonpok",
    "극락곤": "Geon of Paradise",
    "천보륜": "Cheonbo-ryun",
    "천도은하륜": "Cheondo Eunha-ryun",
}

TERM_CANONICAL_MAP = {
    # Common drift from model output; keep canonical names from glossary.
    "Karel": "Kariel",
    "Ichael": "Ikael",
    "Nefilim": "Nephilim",
    "Arman": "Armand",
    "Armana": "Armanda",
}

MAX_REPAIR_ATTEMPTS = 2

CHARACTER_GENDER = {
    "Sirone": "M",
    "Amy": "F",
    "Seriel": "F",
    "Shakora": "M",
    "Isis": "F",
    "Olivia": "F",
    "Alfeas": "M",
    "Kariel": "M",
    "Uriel": "M",
    "Ikael": "F",
    "Gangnan": "F",
    "Gaold": "M",
    "Armand": "M",
    "Nade": "M",
    "Iruki": "M",
}

FEMININE_MARKERS = {
    "powiedziała", "zapytała", "odpowiedziała", "weszła", "wyszła",
    "spojrzała", "odwróciła", "uśmiechnęła", "skinęła", "była",
    "miała", "zrobiła", "sama", "zmęczona", "zaskoczona",
}

MASCULINE_MARKERS = {
    "powiedział", "zapytał", "odpowiedział", "wszedł", "wyszedł",
    "spojrzał", "odwrócił", "uśmiechnął", "skinął", "był",
    "miał", "zrobił", "sam", "zmęczony", "zaskoczony",
}

def get_last_translated_num():
    if not PROGRESS.exists():
        return 299
    try:
        data = json.loads(PROGRESS.read_text(encoding='utf-8'))
    except Exception:
        return 299
    nums = [d.get('num') for d in data if isinstance(d, dict) and isinstance(d.get('num'), int)]
    return max(nums) if nums else 299


def find_src_file(num: int):
    matches = list(SRC_DIR.glob(f"Chapter - {num} - *.txt"))
    return matches[0] if matches else None


def load_text(path: Path):
    return path.read_text(encoding='utf-8')


def build_gender_rules_text() -> str:
    labels = {"M": "mezczyzna", "F": "kobieta"}
    lines = []
    for name in sorted(CHARACTER_GENDER):
        gender = CHARACTER_GENDER[name]
        lines.append(f"- {name}: {labels.get(gender, gender)}")
    return "\n".join(lines)


def build_prompt(num: int, src_title: str, src_text: str, glossary: str, guidelines: str):
    gender_rules = build_gender_rules_text()
    return (
        "Przetlumacz rozdzial na jezyk polski.\n"
        "Zasady:\n"
        "- Zwracaj TYLKO przetlumaczony tekst, bez komentarzy i bez formatowania Markdown.\n"
        "- Tlumacz bezposrednio z koreanskiego na polski, bez tlumaczenia przez angielski.\n"
        "- Zachowaj sens i ton sceny, ale skladnia ma byc naturalna po polsku.\n"
        "- Nie stosuj kalek i nienaturalnego szyku.\n"
        "- Zachowaj podzial akapitow i separatorow scen.\n"
        "- Nie dodawaj pustej linii po kazdej linijce. Uzywaj tylko logicznych przerw akapitowych.\n"
        "- Zachowaj znaczniki typu * * * oraz linie z numerem [num].\n"
        "- Uzywaj cudzyslowow angielskich: \u201c...\u201d.\n"
        "- PIERWSZA LINIA MA MIEC DOKLADNIE FORME: [NUM] POLSKI_TYTUL\n"
        "- Nie wypisuj linii [TITLE] ani [NUM] jako osobnych metadanych.\n"
        "- Tytul w pierwszej linii ma byc po polsku i odpowiadac tresci.\n"
        "- Stosuj terminologie z glosariusza.\n\n"
        "- Nie uzywaj znakow koreanskich (Hangul). Jesli pojawiaja sie w oryginale, zapisz je lacina zgodnie z glosariuszem.\n\n"
        "=== GLOSARIUSZ ===\n"
        f"{glossary}\n\n"
        "=== WSKAZOWKI ===\n"
        f"{guidelines}\n\n"
        "=== PLEC_POSTACI ===\n"
        f"{gender_rules}\n\n"
        "=== ORYGINAL ===\n"
        f"[NUM] {num}\n"
        f"[TITLE] {src_title}\n\n"
        f"{src_text}\n"
    )


def build_repair_prompt(
    num: int,
    src_title: str,
    src_text: str,
    current_translation: str,
    glossary: str,
    guidelines: str,
    issues: List[str],
):
    gender_rules = build_gender_rules_text()
    issues_text = "\n".join(f"- {issue}" for issue in issues)
    return (
        "Popraw ponizsze tlumaczenie rozdzialu na jezyk polski.\n"
        "Masz naprawic problemy jakosci i formatowania bez zmiany sensu tresci.\n"
        "Zasady:\n"
        "- Zwracaj TYLKO finalny poprawiony tekst, bez komentarzy.\n"
        "- Pierwsza linia ma byc DOKLADNIE: [NUM] POLSKI_TYTUL.\n"
        "- Nie wypisuj linii [TITLE] ani [NUM] jako metadanych.\n"
        "- Uzywaj cudzyslowow angielskich: \u201c...\u201d.\n"
        "- Usun znaki Hangul i stosuj nazwy z glosariusza.\n"
        "- Nie dodawaj pustej linii po kazdej linijce.\n\n"
        "=== WYKRYTE PROBLEMY ===\n"
        f"{issues_text}\n\n"
        "=== GLOSARIUSZ ===\n"
        f"{glossary}\n\n"
        "=== WSKAZOWKI ===\n"
        f"{guidelines}\n\n"
        "=== PLEC_POSTACI ===\n"
        f"{gender_rules}\n\n"
        "=== ORYGINAL ===\n"
        f"[NUM] {num}\n"
        f"[TITLE] {src_title}\n\n"
        f"{src_text}\n\n"
        "=== BIEZACE TLUMACZENIE DO POPRAWY ===\n"
        f"{current_translation}\n"
    )


def run_codex(prompt: str) -> str:
    # Prefer explicit CODEX_PATH (e.g. codex.js) for Windows with blocked ps1
    codex_path = os.environ.get('CODEX_PATH')
    use_node = False
    if codex_path:
        codex_path = str(Path(codex_path))
        if codex_path.lower().endswith('.js'):
            use_node = True
    else:
        codex_path = shutil.which('codex') or shutil.which('codex.cmd')
    if not codex_path:
        raise FileNotFoundError(
            "Nie znaleziono komendy 'codex' ani CODEX_PATH. "
            "Ustaw CODEX_PATH na pełną ścieżkę do codex.js, "
            "np. C:\\Users\\Lukasz\\AppData\\Roaming\\npm\\node_modules\\@openai\\codex\\dist\\codex.js"
        )
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        out_path = tmp.name

    try:
        if use_node:
            cmd = [
                'node', codex_path, 'exec', '-',
                '--output-last-message', out_path,
                '--skip-git-repo-check'
            ]
        else:
            cmd = [
                codex_path, 'exec', '-',
                '--output-last-message', out_path,
                '--skip-git-repo-check'
            ]
        subprocess.run(
            cmd,
            input=prompt.encode('utf-8'),
            text=False,
            check=True
        )
        output = Path(out_path).read_text(encoding='utf-8').strip()
        return output
    finally:
        try:
            os.remove(out_path)
        except OSError:
            pass


def run_codex_checked(prompt: str, num: int, stage: str) -> str:
    try:
        return run_codex(prompt)
    except FileNotFoundError as exc:
        print(f"Blad {num} ({stage}): {exc}")
        return ""
    except subprocess.CalledProcessError as exc:
        print(f"Blad {num} ({stage}): codex zakonczyl sie kodem {exc.returncode}.")
        return ""


def replace_hangul(text: str) -> str:
    for src, dst in HANGUL_MAP.items():
        text = text.replace(src, dst)
    return text


def canonicalize_terms(text: str) -> str:
    for src, dst in TERM_CANONICAL_MAP.items():
        text = re.sub(rf"\b{re.escape(src)}\b", dst, text)
    return text


def sanitize_title_for_filename(title: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", title)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().rstrip(". ")
    return cleaned or "Bez tytulu"


def count_non_empty_lines(text: str) -> int:
    return len([line for line in text.splitlines() if line.strip() != ""])


def _is_double_spaced(text: str) -> bool:
    lines = text.splitlines()
    if not lines:
        return False
    empty = sum(1 for line in lines if line.strip() == "")
    return empty >= len(lines) * 0.4


def normalize_spacing(src_text: str, translated: str) -> str:
    if _is_double_spaced(src_text):
        compact = [line.rstrip() for line in translated.splitlines() if line.strip() != ""]
        out = []
        for line in compact:
            if line.strip() == "* * *":
                if out and out[-1] != "":
                    out.append("")
                out.append(line)
                out.append("")
                continue
            out.append(line)
        while out and out[-1] == "":
            out.pop()
        return "\n".join(out).strip()

    lines = [line.rstrip() for line in translated.splitlines()]
    out = []
    prev_empty = False
    for line in lines:
        is_empty = line.strip() == ""
        if is_empty:
            if prev_empty:
                continue
            if _is_double_spaced(src_text):
                continue
            out.append("")
            prev_empty = True
            continue
        out.append(line)
        prev_empty = False
    return "\n".join(out).strip()


def clean_headers(translated: str, num: int, title: str) -> str:
    lines = [line for line in translated.splitlines() if not line.lstrip().startswith("[TITLE]")]
    lines = [line for line in lines if not line.lstrip().startswith("[NUM]")]
    non_empty = [i for i, line in enumerate(lines) if line.strip() != ""]
    if non_empty:
        first_idx = non_empty[0]
        if not re.match(rf"^\[{num}\]\s", lines[first_idx]):
            lines.insert(first_idx, f"[{num}] {title}")
        else:
            lines[first_idx] = f"[{num}] {title}"
        # remove any additional [num] header variants directly below the first header
        i = first_idx + 1
        while i < len(lines) and i <= first_idx + 6:
            stripped = lines[i].strip()
            if stripped == "":
                i += 1
                continue
            if re.match(rf"^\[{num}\]\s+.+$", stripped):
                lines.pop(i)
                continue
            break
    else:
        lines = [f"[{num}] {title}"]
    return "\n".join(lines).strip()


def normalize_quotes(text: str) -> str:
    # Convert ASCII quotes into opening/closing English curly quotes.
    parts = text.split('"')
    if len(parts) == 1:
        return text
    out = []
    open_quote = True
    for idx, part in enumerate(parts):
        out.append(part)
        if idx == len(parts) - 1:
            break
        out.append("“" if open_quote else "”")
        open_quote = not open_quote
    return "".join(out)


def postprocess_translation(text: str, src_text: str, num: int, title: str) -> str:
    text = replace_hangul(text)
    text = canonicalize_terms(text)
    text = normalize_spacing(src_text, text)
    text = clean_headers(text, num, title)
    text = normalize_quotes(text)
    return text


def detect_gender_mismatches(text: str) -> List[str]:
    issues: List[str] = []
    lines = text.splitlines()
    max_issues = 8

    feminine_group = "|".join(re.escape(marker) for marker in sorted(FEMININE_MARKERS))
    masculine_group = "|".join(re.escape(marker) for marker in sorted(MASCULINE_MARKERS))

    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue
        for name, gender in CHARACTER_GENDER.items():
            if name not in stripped:
                continue
            if gender == "M":
                pattern = rf"\b{re.escape(name)}\b[^\n.?!]{{0,80}}\b(?:{feminine_group})\b"
            else:
                pattern = rf"\b{re.escape(name)}\b[^\n.?!]{{0,80}}\b(?:{masculine_group})\b"
            if re.search(pattern, stripped, flags=re.IGNORECASE):
                excerpt = stripped if len(stripped) <= 140 else stripped[:137] + "..."
                issues.append(f"Podejrzenie blednej plci dla {name} (linia {idx}: {excerpt})")
                break
        if len(issues) >= max_issues:
            break
    return issues


def validate_translation(text: str, src_text: str, num: int) -> List[str]:
    issues: List[str] = []
    lines = text.splitlines()
    if not lines:
        issues.append("Pusty wynik tlumaczenia.")
        return issues

    first_non_empty = next((line.strip() for line in lines if line.strip() != ""), "")
    if not re.match(rf"^\[{num}\]\s+.+$", first_non_empty):
        issues.append(f"Brak poprawnego naglowka [{num}] POLSKI_TYTUL.")

    if re.search(r"(?m)^\[TITLE\]", text):
        issues.append("Wynik zawiera linie [TITLE].")
    if re.search(r"(?m)^\[NUM\]", text):
        issues.append("Wynik zawiera linie [NUM].")
    if re.search(r"[가-힣]", text):
        issues.append("Wynik zawiera znaki Hangul.")

    src_lines = count_non_empty_lines(src_text)
    out_lines = count_non_empty_lines(text)
    if src_lines > 0:
        ratio = out_lines / src_lines
        if ratio < 0.55:
            issues.append(f"Za malo tresci po tlumaczeniu (ratio linii {ratio:.2f}).")
        if ratio > 1.70:
            issues.append(f"Za duzo tresci po tlumaczeniu (ratio linii {ratio:.2f}).")

    if re.search(r"\n{3,}", text):
        issues.append("Wykryto nadmiarowe puste linie.")

    issues.extend(detect_gender_mismatches(text))

    return issues


def parse_title(text: str, num: int, fallback: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines[:6]:
        m = re.match(r"^\[(\d+)\]\s*(.+)$", line)
        if m and int(m.group(1)) == num:
            return m.group(2).strip() or fallback
    for line in lines[:8]:
        m = re.match(r"^\[TITLE\]\s*(.+)$", line)
        if m:
            return m.group(1).strip() or fallback
    return fallback


def save_translation(num: int, title: str, text: str) -> str:
    OUT_DIR.mkdir(exist_ok=True)
    safe_title = sanitize_title_for_filename(title)
    filename = f"Chapter - {num} - {safe_title}.txt"
    (OUT_DIR / filename).write_text(text, encoding='utf-8')
    return filename


def update_progress(num: int, file_name: str, title: str):
    data = []
    if PROGRESS.exists():
        try:
            data = json.loads(PROGRESS.read_text(encoding='utf-8'))
        except Exception:
            data = []
    data = [d for d in data if d.get('num') != num]
    data.append({"num": num, "file": file_name, "title": title})
    data.sort(key=lambda x: x['num'])
    PROGRESS.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def load_progress_data() -> List[dict]:
    if not PROGRESS.exists():
        return []
    try:
        data = json.loads(PROGRESS.read_text(encoding='utf-8'))
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def repair_existing_range(start: int, end: int):
    data = load_progress_data()
    by_num = {
        entry.get("num"): entry
        for entry in data
        if isinstance(entry, dict) and isinstance(entry.get("num"), int)
    }

    for num in range(start, end + 1):
        entry = by_num.get(num)
        if not entry:
            print(f"Brak wpisu w progress dla {num}")
            continue

        file_name = entry.get("file")
        if not isinstance(file_name, str):
            print(f"Brak pliku w progress dla {num}")
            continue

        path = OUT_DIR / file_name
        if not path.exists():
            print(f"Brak pliku tlumaczenia dla {num}: {file_name}")
            continue

        src = find_src_file(num)
        if not src:
            print(f"Brak pliku zrodlowego dla {num}")
            continue
        src_text = load_text(src)

        text = load_text(path)
        title = parse_title(text, num, str(entry.get("title") or f"Rozdzial {num}"))
        repaired = postprocess_translation(text, src_text, num, title)
        issues = validate_translation(repaired, src_text, num)
        path.write_text(repaired, encoding='utf-8')
        entry["title"] = title
        if issues:
            print(f"Naprawiono {num} z ostrzezeniami: {'; '.join(issues)}")
        else:
            print(f"Naprawiono {num}")

    PROGRESS.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    if len(sys.argv) == 4 and sys.argv[1] == "--repair-existing":
        start = int(sys.argv[2])
        end = int(sys.argv[3])
        if start > end:
            print("Bledny zakres: start musi byc <= end.")
            sys.exit(1)
        repair_existing_range(start, end)
        return

    if len(sys.argv) != 2:
        print("Uzycie:")
        print("  python3 tools/translate_with_codex.py <target_chapter>")
        print("  python3 tools/translate_with_codex.py --repair-existing <start> <end>")
        sys.exit(1)
    target = int(sys.argv[1])

    last = get_last_translated_num()
    glossary = load_text(GLOSSARY) if GLOSSARY.exists() else ""
    guidelines = load_text(GUIDELINES) if GUIDELINES.exists() else ""

    for num in range(last + 1, target + 1):
        src = find_src_file(num)
        if not src:
            print(f"Brak pliku zrodlowego dla {num}")
            continue
        src_title = re.sub(r"^Chapter - \d+ - ", "", src.stem)
        src_text = load_text(src)
        prompt = build_prompt(num, src_title, src_text, glossary, guidelines)
        translated = run_codex_checked(prompt, num, "tlumaczenie")
        if not translated:
            print(f"Brak wyniku dla {num}; pomijam rozdzial.")
            continue
        if translated.strip().startswith("ERROR:"):
            print(f"Blad {num} (tlumaczenie): {translated.strip()}")
            continue
        if translated.strip().startswith("Warning:"):
            print(f"Blad {num} (tlumaczenie): nieprawidlowy output z Codex.")
            continue
        fallback_title = f"Rozdzial {num}"
        title = parse_title(translated, num, fallback_title)
        translated = postprocess_translation(translated, src_text, num, title)

        issues = validate_translation(translated, src_text, num)
        repair_attempt = 0
        while issues and repair_attempt < MAX_REPAIR_ATTEMPTS:
            repair_attempt += 1
            print(
                f"Uwaga {num}: wykryto problemy jakosci ({'; '.join(issues)}). "
                f"Proba automatycznej poprawy {repair_attempt}/{MAX_REPAIR_ATTEMPTS}."
            )
            repair_prompt = build_repair_prompt(
                num=num,
                src_title=src_title,
                src_text=src_text,
                current_translation=translated,
                glossary=glossary,
                guidelines=guidelines,
                issues=issues,
            )
            repaired = run_codex_checked(repair_prompt, num, "naprawa")
            if not repaired:
                break
            title = parse_title(repaired, num, title)
            translated = postprocess_translation(repaired, src_text, num, title)
            issues = validate_translation(translated, src_text, num)

        if issues:
            print(f"Uwaga {num}: pozostale problemy po naprawie: {'; '.join(issues)}")

        file_name = save_translation(num, title, translated)
        update_progress(num, file_name, title)
        print(f"OK {num}")


if __name__ == '__main__':
    main()
