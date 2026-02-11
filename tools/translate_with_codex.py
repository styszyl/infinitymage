#!/usr/bin/env python3
import json
import os
import re
import subprocess
import sys
import tempfile
import shutil
from pathlib import Path

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


def build_prompt(num: int, src_title: str, src_text: str, glossary: str, guidelines: str):
    return (
        "Przetlumacz rozdzial na jezyk polski.\n"
        "Zasady:\n"
        "- Zwracaj TYLKO przetlumaczony tekst, bez komentarzy i bez formatowania Markdown.\n"
        "- Zachowaj format i podzialy akapitow.\n"
        "- Nie dodawaj pustej linii po kazdej linijce. Zachowuj tylko logiczne przerwy miedzy akapitami.\n"
        "- Zachowaj znaczniki typu * * * oraz linie z numerem [num].\n"
        "- Uzywaj cudzyslowow angielskich: \u201c...\u201d.\n"
        "- Pierwsza linia ma miec forme: [NUM] POLSKI_TYTUL\n"
        "- Tytul w pierwszej linii ma byc po polsku i odpowiadac tresci.\n"
        "- Stosuj terminologie z glosariusza.\n\n"
        "- Nie uzywaj znakow koreanskich (Hangul). Jesli pojawiaja sie w oryginale, zapisz je lacina zgodnie z glosariuszem.\n\n"
        "=== GLOSARIUSZ ===\n"
        f"{glossary}\n\n"
        "=== WSKAZOWKI ===\n"
        f"{guidelines}\n\n"
        "=== ORYGINAL ===\n"
        f"[NUM] {num}\n"
        f"[TITLE] {src_title}\n\n"
        f"{src_text}\n"
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


def replace_hangul(text: str) -> str:
    for src, dst in HANGUL_MAP.items():
        text = text.replace(src, dst)
    return text


def _is_double_spaced(text: str) -> bool:
    lines = text.splitlines()
    if not lines:
        return False
    empty = sum(1 for line in lines if line.strip() == "")
    return empty >= len(lines) * 0.4


def normalize_spacing(src_text: str, translated: str) -> str:
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
    lines = [line for line in translated.splitlines() if not line.startswith("[TITLE]")]
    lines = [line for line in lines if not line.startswith("[NUM]")]
    non_empty = [i for i, line in enumerate(lines) if line.strip() != ""]
    if non_empty:
        first_idx = non_empty[0]
        if not re.match(rf"^\\[{num}\\]\\s", lines[first_idx]):
            lines.insert(first_idx, f"[{num}] {title}")
        else:
            lines[first_idx] = f"[{num}] {title}"
        # remove duplicate header lines right after
        for i in range(first_idx + 1, min(first_idx + 3, len(lines))):
            if lines[i].strip() == f"[{num}] {title}":
                lines.pop(i)
                break
    else:
        lines = [f"[{num}] {title}"]
    return "\n".join(lines).strip()


def parse_title(text: str, num: int, fallback: str) -> str:
    first = text.splitlines()[0].strip()
    m = re.match(r"^\[(\d+)\]\s*(.+)$", first)
    if not m:
        return fallback
    n = int(m.group(1))
    if n != num:
        return fallback
    return m.group(2).strip() or fallback


def save_translation(num: int, title: str, text: str) -> str:
    OUT_DIR.mkdir(exist_ok=True)
    filename = f"Chapter - {num} - {title}.txt"
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


def main():
    if len(sys.argv) != 2:
        print("Uzycie: python3 tools/translate_with_codex.py <target_chapter>")
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
        translated = run_codex(prompt)
        if not translated:
            print(f"Brak wyniku dla {num}")
            break
        translated = replace_hangul(translated)
        translated = normalize_spacing(src_text, translated)
        if re.search(r"[가-힣]", translated):
            print(f"Uwaga: wykryto znaki Hangul w {num}; sprawdz tlumaczenie recznie.")
        title = parse_title(translated, num, src_title)
        translated = clean_headers(translated, num, title)
        file_name = save_translation(num, title, translated)
        update_progress(num, file_name, title)
        print(f"OK {num}")


if __name__ == '__main__':
    main()
