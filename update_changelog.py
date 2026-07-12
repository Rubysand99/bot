#!/usr/bin/env python3
"""
update_changelog.py — Tự động bump version + ghi CHANGELOG.md
Dùng: python3 update_changelog.py

Chạy trên Termux:
  cd ~/bot
  python3 update_changelog.py
  git add CHANGELOG.md bot.py cogs/admin.py
  git commit -m "chore: bump version + update changelog"
  git push
"""

import re
import sys
from datetime import datetime, timezone

# ── Cấu hình đường dẫn ──────────────────────────────────────────────────────
CHANGELOG_FILE = "CHANGELOG.md"
BOT_PY         = "bot.py"
ADMIN_PY       = "cogs/admin.py"

# ── Đọc version hiện tại từ bot.py ──────────────────────────────────────────
def get_current_version() -> str:
    with open(BOT_PY, encoding="utf-8") as f:
        content = f.read()
    m = re.search(r'BOT_VERSION\s*=\s*"([\d.]+)"', content)
    if not m:
        raise RuntimeError("Không tìm thấy BOT_VERSION trong bot.py")
    return m.group(1)

# ── Bump version ─────────────────────────────────────────────────────────────
def bump_version(version: str, part: str) -> str:
    major, minor, patch = map(int, version.split("."))
    if part == "major":
        return f"{major+1}.0.0"
    elif part == "minor":
        return f"{major}.{minor+1}.0"
    else:  # patch
        return f"{major}.{minor}.{patch+1}"

# ── Cập nhật version trong file ──────────────────────────────────────────────
def update_version_in_file(filepath: str, new_version: str, new_date: str):
    with open(filepath, encoding="utf-8") as f:
        content = f.read()
    content = re.sub(
        r'(BOT_VERSION\s*=\s*")[^"]*(")',
        lambda m: f'{m.group(1)}{new_version}{m.group(2)}',
        content
    )
    content = re.sub(
        r'(BOT_UPDATED\s*=\s*")[^"]*(")',
        lambda m: f'{m.group(1)}{new_date}{m.group(2)}',
        content
    )
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

# ── Ghi CHANGELOG.md ─────────────────────────────────────────────────────────
def prepend_changelog(new_version: str, new_date: str, entries: dict):
    with open(CHANGELOG_FILE, encoding="utf-8") as f:
        existing = f.read()

    # Build entry mới
    lines = [f"## [v{new_version}] — {new_date}", ""]

    section_map = {
        "new":    "✨ Tính năng mới",
        "fix":    "🐛 Sửa lỗi",
        "change": "♻️ Thay đổi",
        "remove": "🗑️ Xoá bỏ",
    }
    for key in ["new", "fix", "change", "remove"]:
        items = entries.get(key, [])
        if items:
            lines.append(f"### {section_map[key]}")
            for item in items:
                lines.append(f"- {item}")
            lines.append("")

    lines.append("---")
    lines.append("")

    new_entry = "\n".join(lines)

    # Chèn sau dòng tiêu đề # CHANGELOG
    if "# CHANGELOG" in existing:
        parts = existing.split("\n", 1)
        updated = parts[0] + "\n\n" + new_entry + (parts[1].lstrip("\n") if len(parts) > 1 else "")
    else:
        updated = new_entry + existing

    with open(CHANGELOG_FILE, "w", encoding="utf-8") as f:
        f.write(updated)

# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    current = get_current_version()
    today   = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    print(f"\n{'='*50}")
    print(f"  TuyTam Bot — Cập nhật Changelog & Version")
    print(f"{'='*50}")
    print(f"  Version hiện tại : v{current}")
    print(f"  Ngày hôm nay     : {today}")
    print(f"{'='*50}\n")

    # Chọn loại bump
    print("Chọn loại thay đổi:")
    print("  1) patch  — sửa bug nhỏ        (v4.5.0 → v4.5.1)")
    print("  2) minor  — tính năng mới       (v4.5.0 → v4.6.0)")
    print("  3) major  — thay đổi lớn        (v4.5.0 → v5.0.0)")
    print("  4) giữ nguyên version")
    choice = input("\n> Nhập số (1/2/3/4): ").strip().strip("\ufeff").replace("\r", "")
    print(f"[debug] nhận được: {repr(choice)}")

    part_map = {"1": "patch", "2": "minor", "3": "major"}
    if choice in part_map:
        new_version = bump_version(current, part_map[choice])
    elif choice == "4":
        new_version = current
    else:
        print("❌ Lựa chọn không hợp lệ.")
        sys.exit(1)

    print(f"\n✅ Version mới: v{new_version}\n")

    # Nhập nội dung thay đổi
    entries = {}
    sections = [
        ("new",    "✨ Tính năng mới  (Enter để bỏ qua)"),
        ("fix",    "🐛 Sửa lỗi       (Enter để bỏ qua)"),
        ("change", "♻️ Thay đổi       (Enter để bỏ qua)"),
        ("remove", "🗑️ Xoá bỏ        (Enter để bỏ qua)"),
    ]

    for key, label in sections:
        print(f"\n{label}")
        print("  Nhập từng dòng, Enter trống để sang mục tiếp theo:")
        items = []
        while True:
            line = input("  - ").strip().strip("\ufeff").replace("\r", "")
            if not line:
                break
            items.append(line)
        if items:
            entries[key] = items

    if not entries:
        print("\n⚠️ Không có nội dung nào được nhập. Thoát.")
        sys.exit(0)

    # Xác nhận
    print(f"\n{'─'*50}")
    print(f"  Sẽ ghi vào CHANGELOG.md:")
    print(f"  ## [v{new_version}] — {today}")
    for key, items in entries.items():
        for item in items:
            print(f"  - {item}")
    print(f"{'─'*50}")
    confirm = input("\nXác nhận ghi? (y/n): ").strip().strip("\ufeff").replace("\r", "").lower()
    if confirm != "y":
        print("❌ Đã huỷ.")
        sys.exit(0)

    # Thực hiện
    prepend_changelog(new_version, today, entries)
    if new_version != current:
        update_version_in_file(BOT_PY, new_version, today)
        try:
            update_version_in_file(ADMIN_PY, new_version, today)
        except FileNotFoundError:
            pass  # admin.py không bắt buộc

    print(f"\n✅ Xong! CHANGELOG.md đã cập nhật — v{current} → v{new_version}")
    print("\nBước tiếp theo:")
    print("  git add CHANGELOG.md bot.py cogs/admin.py")
    print(f'  git commit -m "chore: v{new_version} — {today}"')
    print("  git push")

if __name__ == "__main__":
    main()
