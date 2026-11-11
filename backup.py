import time
import hashlib
import json
import shutil
import tarfile
from datetime import datetime
from pathlib import Path

SOURCE = Path("company_data")
BACKUP_DIR = Path("backups")
KEEP_LAST = 4


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def make_manifest(folder):
    return {
        str(p.relative_to(folder)): sha256(p)
        for p in sorted(folder.rglob("*")) if p.is_file()
    }


def create_backup():
    BACKUP_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    archive = BACKUP_DIR / f"backup_{stamp}.tar.gz"

    with tarfile.open(archive, "w:gz") as tar:
        tar.add(SOURCE, arcname=SOURCE.name)

    manifest = {
        "created": stamp,
        "archive_sha256": sha256(archive),
        "files": make_manifest(SOURCE)
    }

    archive.with_suffix("").with_suffix(".json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    print(
        f"[OK] Создан {archive.name}, "
        f"файлов: {len(manifest['files'])}, "
        f"размер: {archive.stat().st_size / 1024:.1f} КБ"
    )

    return archive


def rotate():
    archives = sorted(BACKUP_DIR.glob("backup_*.tar.gz"))

    for old in archives[:-KEEP_LAST]:
        old.unlink()
        old.with_suffix("").with_suffix(".json").unlink(
            missing_ok=True
        )
        print(f"[ROTATE] Удалена старая копия {old.name}")



def verify_restore(archive):
    manifest_path = archive.with_suffix("").with_suffix(".json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    if sha256(archive) != manifest["archive_sha256"]:
        print("[FAIL] Архив повреждён: контрольная сумма не совпадает")
        return False

    tmp = Path("restore_test")
    shutil.rmtree(tmp, ignore_errors=True)

    with tarfile.open(archive) as tar:
        tar.extractall(tmp, filter="data")

    restored = make_manifest(tmp / SOURCE.name)
    shutil.rmtree(tmp)

    expected = manifest["files"]

    if restored == expected:
        print(f"[OK] Восстановление проверено: {len(restored)} файлов совпадают")
        return True

    missing = sorted(set(expected) - set(restored))
    extra = sorted(set(restored) - set(expected))
    changed = sorted(
        p for p in set(expected) & set(restored)
        if expected[p] != restored[p]
    )

    print("[FAIL] Обнаружены различия:")

    for file in missing:
        print(f"[MISSING] Отсутствует: {file}")

    for file in extra:
        print(f"[EXTRA] Лишний файл: {file}")

    for file in changed:
        print(f"[CHANGED] Изменён: {file}")

    return False


def restore(archive):
    manifest_path = archive.with_suffix("").with_suffix(".json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    if sha256(archive) != manifest["archive_sha256"]:
        print("[FAIL] Архив повреждён")
        return False

    start = time.perf_counter()

    shutil.rmtree(SOURCE, ignore_errors=True)

    with tarfile.open(archive, "r:gz") as tar:
        tar.extractall(".", filter="data")

    restored = make_manifest(SOURCE)
    elapsed = time.perf_counter() - start

    if restored == manifest["files"]:
        print("[OK] Данные успешно восстановлены")
        print(f"[OK] Восстановлено файлов: {len(restored)}")
        print(f"[TIME] Время восстановления: {elapsed:.4f} сек")
        return True

    print("[FAIL] Ошибка восстановления")
    return False


if __name__ == "__main__":
    archive = create_backup()
    rotate()
    verify_restore(archive)
