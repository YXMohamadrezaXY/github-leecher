import os
import subprocess
import shutil

def main():
    url = os.environ.get("SPOTIFY_URL", "").strip()
    fmt = os.environ.get("FORMAT", "mp3")
    quality = os.environ.get("QUALITY", "320k")

    if not url.startswith("http"):
        print("❌ لطفاً یک لینک معتبر Spotify وارد کنید.")
        return

    output_dir = "output/spotify"
    os.makedirs(output_dir, exist_ok=True)

    # ساخت دستور spotdl
    cmd = [
        "spotdl", "download", url,
        "--format", fmt,
        "--bitrate", quality,
        "--output", output_dir + "/{artists} - {title}.{output-ext}"
    ]

    # برای flac، bitrate مهم نیست -> حذفش کن
    if fmt == "flac":
        cmd = [c for c in cmd if c != "--bitrate" and c != quality]

    print(f"▶️ اجرای دستور: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        print(result.stdout)
        if result.returncode != 0:
            print(f"خطای spotdl:\n{result.stderr}")
        else:
            print("✅ دانلود با موفقیت انجام شد.")
            # فشرده‌سازی فایل‌های حجیم (اختیاری)
            compress_large_files(output_dir)
    except subprocess.TimeoutExpired:
        print("⏰ زمان دانلود به پایان رسید (۶۰ دقیقه).")
    except Exception as e:
        print(f"❌ خطا: {e}")

def compress_large_files(folder):
    """فشرده‌سازی فایل‌های بزرگتر از ۵۰ مگابایت"""
    from pathlib import Path
    for f in Path(folder).rglob("*"):
        if f.is_file() and f.suffix in (".mp3", ".flac") and f.stat().st_size > 50 * 1024 * 1024:
            print(f"🗜️ فشرده‌سازی {f.name}...")
            new = str(f).replace(f.suffix, f"_compressed{f.suffix}")
            subprocess.run(["ffmpeg", "-i", str(f), "-b:a", "128k", new, "-y"], capture_output=True)
            os.replace(new, str(f))

if __name__ == "__main__":
    main()
  
