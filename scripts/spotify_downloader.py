import os
import subprocess
import shutil
from pathlib import Path

SPLIT_MB = 90  # هر قطعه حداکثر ۹۰ مگابایت

def main():
    url = os.environ.get("SPOTIFY_URL", "").strip()
    fmt = os.environ.get("FORMAT", "mp3")
    quality = os.environ.get("QUALITY", "320k")

    if not url.startswith("http"):
        print("❌ لطفاً یک لینک معتبر Spotify وارد کنید.")
        return

    output_dir = "output/spotify"
    os.makedirs(output_dir, exist_ok=True)

    # ۱. دانلود آهنگ‌ها با spotdl
    cmd = [
        "spotdl", "download", url,
        "--format", fmt,
        "--bitrate", quality,
        "--output", f"{output_dir}/{{artists}} - {{title}}.{{output-ext}}"
    ]
    if fmt == "flac":
        cmd = [c for c in cmd if c != "--bitrate" and c != quality]

    print(f"▶️ اجرا: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        print(result.stdout)
        if result.returncode != 0:
            print(f"❌ خطای spotdl:\n{result.stderr}")
            return
    except subprocess.TimeoutExpired:
        print("⏰ زمان دانلود تمام شد (۶۰ دقیقه).")
        return

    # ۲. ساخت آرشیو zip چندبخشی و جایگزینی با فایل‌های اصلی
    songs = list(Path(output_dir).glob(f"*.{fmt}"))
    if not songs:
        print("⚠️ هیچ فایلی دانلود نشد.")
        return

    print("🗜️ ساخت آرشیو zip چندبخشی...")
    zip_name = "playlist.zip"
    zip_path = os.path.join(output_dir, zip_name)

    # ساخت zip اسپلیت‌شده با دستور zip -s
    cmd_zip = [
        "zip", "-s", f"{SPLIT_MB}m", "-r", zip_path, "."
    ]
    # اجرا در پوشه output/spotify
    p = subprocess.run(cmd_zip, cwd=output_dir, capture_output=True, text=True)
    if p.returncode != 0:
        print(f"❌ خطا در ساخت zip: {p.stderr}")
        return

    # حذف فایل‌های اصلی (فقط فایل‌های صوتی) برای جلوگیری از افزایش حجم ریپو
    for f in songs:
        try:
            os.remove(str(f))
            print(f"🗑️ پاک شد: {f.name}")
        except Exception as e:
            print(f"⚠️ خطا در حذف {f.name}: {e}")

    # قسمت‌های zip شامل playlist.zip، playlist.z01، ... خواهند بود.
    # همه در output/spotify باقی می‌مانند.
    print("✅ تمام فایل‌ها در پوشه output/spotify قرار دارند.")

if __name__ == "__main__":
    main()
