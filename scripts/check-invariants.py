#!/usr/bin/env python3
"""Проверяет, что тесты из колонки «Проверка» в invariants.md существуют.

Ссылки берутся из обратных кавычек:
  Suite.Name            — тест core: TEST/TEST_F/TEST_P/RC_GTEST_PROP в core/tests;
  путь к файлу          — файл есть в core (tests/...), в frontend (frontend/...,
                          либо имя файла/каталог где-то в frontend/src и e2e);
  INV-N: название теста — подстрока названия в it()/test()/describe() во
                          frontend/src и frontend/e2e (после «…» название обрезается).
Ссылки с пометкой «удалён» рядом не проверяются.

Код возврата: 0 — всё найдено, 1 — есть ненайденное.
"""
import argparse
import re
import sys
from pathlib import Path

CORE_TEST = re.compile(r"\b(?:TEST|TEST_F|TEST_P|RC_GTEST_PROP)\s*\(\s*(\w+)\s*,\s*(\w+)")
FRONT_TITLE = re.compile(r"\b(?:it|test|describe)(?:\.\w+)*\(\s*(['\"`])(.*?)\1")
SUITE_NAME = re.compile(r"^[A-Z]\w*\.[A-Z]\w*$")
FILE_EXT = re.compile(r"\.(cpp|hpp|h|ts|tsx|py|yml|yaml)$")
SKIP_MARK = re.compile(r"удал[её]н", re.IGNORECASE)


def read_files(root: Path, patterns):
    for pat in patterns:
        for f in root.glob(pat):
            if f.is_file() and "node_modules" not in f.parts:
                yield f.read_text(encoding="utf-8", errors="replace")


def expand_braces(s):
    m = re.search(r"\{([^{}]*)\}", s)
    if not m:
        return [s]
    return [r for alt in m.group(1).split(",")
            for r in expand_braces(s[:m.start()] + alt.strip() + s[m.end():])]


def parse_rows(path: Path):
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\|\s*(INV-\d+)\s*\|", line)
        if not m:
            continue
        cells = line.strip().strip("|").split("|")
        yield m.group(1), cells[-1]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--core", default="../core", type=Path)
    ap.add_argument("--frontend", default="../frontend", type=Path)
    ap.add_argument("--invariants", default=Path(__file__).resolve().parent.parent / "invariants.md", type=Path)
    a = ap.parse_args()

    for name, p in (("core", a.core), ("frontend", a.frontend)):
        if not p.is_dir():
            sys.exit(f"каталог {name} не найден: {p}")

    core_tests = {(s, n) for t in read_files(a.core, ["tests/**/*.cpp", "tests/**/*.hpp"])
                  for s, n in CORE_TEST.findall(t)}
    titles = [t for src in read_files(a.frontend, ["src/**/*.ts", "e2e/**/*.ts"])
              for _, t in FRONT_TITLE.findall(src)]

    def file_exists(ref):
        for r in expand_braces(ref):
            r = r.strip("/")
            if r.startswith("frontend/"):
                ok = (a.frontend / r[len("frontend/"):]).exists()
            elif r.startswith("core/"):
                ok = (a.core / r[len("core/"):]).exists()
            elif r.startswith("tests/"):
                ok = (a.core / r).exists()
            else:  # имя файла или каталог без префикса — ищем во frontend
                ok = any(a.frontend.glob(f"{d}/**/{r}") for d in ("src", "e2e"))
            if not ok:
                return False
        return True

    missing, checked = [], 0
    for inv, cell in parse_rows(a.invariants):
        for m in re.finditer(r"`([^`]+)`([^`]{0,24})", cell):
            ref, tail = m.group(1).strip(), m.group(2)
            if SKIP_MARK.search(tail[:12]):
                continue
            if SUITE_NAME.match(ref) and not FILE_EXT.search(ref):
                checked += 1
                s, n = ref.split(".")
                if (s, n) not in core_tests:
                    missing.append((inv, ref, "тест не найден в core/tests"))
            elif ref.startswith("INV-"):
                checked += 1
                title = ref.split("…")[0].strip()
                if not any(title in t for t in titles):
                    missing.append((inv, ref, "название теста не найдено во frontend"))
            elif FILE_EXT.search(ref) or "/" in ref:
                checked += 1
                if not file_exists(ref):
                    missing.append((inv, ref, "файл не найден"))

    for inv, ref, why in missing:
        print(f"{inv} → {ref}: {why}")
    print(f"проверено ссылок: {checked}, не найдено: {len(missing)}")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
