"""Собирает ZIP для платформы: файлы в корне, без базы и без вопросов."""

import ast
import os
import py_compile
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
INCLUDE = (
    "solution.py",
    "consult.py",
    "consultant.py",
    "prompt.txt",
    "contract.py",
    "dialogue.py",
    "chunks.py",
    "retrieve.py",
    "llm.py",
    "config.py",
    "requirements.txt",
    "README.md",
)
FORBIDDEN = {
    "knowledge-base.zip",
    "knowledge_base.zip",
    "kb.zip",
    "questions.csv",
    "demo_questions.csv",
    "demo_output.csv",
    ".env",
}
ZIP_LIMIT = 128 * 1024 * 1024
LOCAL_MODULES = {
    "solution",
    "consult",
    "consultant",
    "contract",
    "dialogue",
    "chunks",
    "retrieve",
    "llm",
    "config",
}


def parse_requirements(path: Path) -> dict[str, str]:
    items = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if "==" not in line or ";" in line or " " in line:
            raise SystemExit(f"Нужна точная версия без маркеров: {raw}")
        name, version = line.split("==", 1)
        items[name.strip().lower()] = version.strip()
    return items


def check_requirements() -> None:
    allowed_path = ROOT / "_materials" / "requirements.txt"
    if not allowed_path.is_file():
        raise SystemExit(f"Нет списка разрешённых пакетов: {allowed_path}")
    allowed = parse_requirements(allowed_path)
    ours = parse_requirements(ROOT / "requirements.txt")
    if not ours:
        raise SystemExit("requirements.txt пустой")
    for name, version in ours.items():
        if name not in allowed:
            raise SystemExit(f"Пакет не из разрешённого списка: {name}")
        if allowed[name] != version:
            raise SystemExit(
                f"{name}=={version} не совпадает с разрешённой версией {allowed[name]}"
            )


def check_imports() -> None:
    stdlib = set(sys.stdlib_module_names)
    third_party = set(parse_requirements(ROOT / "requirements.txt"))
    # Имя пакета в requirements и имя модуля совпадают у httpx.
    # python-dotenv импортируется как dotenv.
    third_party.add("dotenv")
    third_party.discard("python-dotenv")
    for name in INCLUDE:
        if not name.endswith(".py"):
            continue
        tree = ast.parse((ROOT / name).read_text(encoding="utf-8"), filename=name)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name.split(".", 1)[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                modules = [node.module.split(".", 1)[0]]
            else:
                continue
            for module in modules:
                if module in LOCAL_MODULES or module in stdlib or module in third_party:
                    continue
                raise SystemExit(f"{name} импортирует {module}, его нет в requirements.txt")


def smoke_import(zip_path: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(tmp)
        env = os.environ.copy()
        env["ENERGYTOOL_SKIP_DOTENV"] = "1"
        command = (
            "import solution, consult, consultant, contract, dialogue, chunks, retrieve, llm, config"
        )
        proc = subprocess.run(
            [sys.executable, "-c", command],
            cwd=tmp,
            env=env,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise SystemExit("Импорт из ZIP не удался:\n" + (proc.stderr or proc.stdout))


def main() -> int:
    check_requirements()
    check_imports()
    missing = [name for name in INCLUDE if not (ROOT / name).is_file()]
    if missing:
        raise SystemExit("Нет файлов: " + ", ".join(missing))
    for name in INCLUDE:
        if name.endswith(".py"):
            py_compile.compile(str(ROOT / name), doraise=True)

    destination = ROOT / "out" / "submission.zip"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in INCLUDE:
            archive.write(ROOT / name, arcname=name)

    with zipfile.ZipFile(destination) as archive:
        names = archive.namelist()
        for name in names:
            if "/" in name or "\\" in name or name.startswith("/"):
                raise SystemExit(f"Вложенный путь в ZIP: {name}")
            if name in FORBIDDEN or name.endswith(".env"):
                raise SystemExit(f"В ZIP попал запрещённый файл: {name}")
        if "solution.py" not in names or "requirements.txt" not in names:
            raise SystemExit("В ZIP нет solution.py или requirements.txt")
        if set(names) != set(INCLUDE):
            raise SystemExit(f"Состав ZIP не совпал с ожидаемым: {names}")

    size = destination.stat().st_size
    if size > ZIP_LIMIT:
        raise SystemExit(f"ZIP {size} байт, лимит {ZIP_LIMIT}")
    smoke_import(destination)
    print(f"Готов {destination} ({size} байт)")
    print("В архиве только корень: " + ", ".join(INCLUDE))
    print("Базы знаний и questions.csv внутри нет.")
    print("Перед отправкой запишите гипотезу в journal/submits.md. Лимит — 5 сабмитов в сутки.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
