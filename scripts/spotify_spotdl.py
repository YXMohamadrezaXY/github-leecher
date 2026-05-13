import os
import subprocess
from pathlib import Path

SPLIT_MB = 90  # حداکثر حجم هر بخش از فایل ZIP

def main():
    url = os.environ["SPOTIFY_URL"].strip()
    fmt = os.environ.get("FORMAT", "mp3")
    quality = os.environ.get("QUALITY", "320k")

    if not url.startswith("http"):
        print("❌ لطفاً یک لینک معتبر وارد کنید.")
        return

    output_dir = "output/spotify"
    os.makedirs(output_dir, exist_ok=True)

    # ۱. دانلود با spotdl
    cmd = [
        "spotdl", "download", url,
        "--format", fmt,
        "--bitrate", quality,
        "--output", str(Path(output_dir) / "{artists} - {title}.{output-ext}")
    ]
    if fmt == "flac":
        cmd = [c for c in cmd if c != "--bitrate" and c != quality]

    print(f"▶️ اجرای دستور: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        print(result.stdout)
        if result.returncode != 0:
            print(f"❌ خطای spotdl:\n{result.stderr}")
            return
    except subprocess.TimeoutExpired:
        print("⏰ زمان دانلود به پایان رسید.")
        return

    # ۲. ساخت ZIP چندبخشی
    songs = list(Path(output_dir).glob(f"*.{fmt}"))
    if not songs:
        print("⚠️ هیچ فایلی دانلود نشد.")
        return

    print("🗜️ در حال ساخت ZIP چندبخشی...")
    zip_name = "spotify_playlist.zip"
    zip_path = os.path.join(output_dir, zip_name)
    subprocess.run(
        ["zip", "-s", f"{SPLIT_MB}m", "-r", zip_path, "."],
        cwd=output_dir, capture_output=True, text=True
    )

    # حذف فایل‌های صوتی اصلی برای کاهش حجم
    for f in songs:
        try:
            os.remove(str(f))
            print(f"🗑️ فایل اصلی حذف شد: {f.name}")
        except Exception as e:
            print(f"⚠️ خطا در حذف {f.name}: {e}")

    print("✅ فایل‌های ZIP در پوشه output/spotify آماده هستند.")

if __name__ == "__main__":
    main()
