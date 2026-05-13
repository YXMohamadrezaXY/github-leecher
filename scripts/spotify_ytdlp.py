import os
import subprocess
from pathlib import Path

SPLIT_MB = 90  # اندازه هر قطعه ZIP

def main():
    url = os.environ["SPOTIFY_URL"].strip()
    fmt = os.environ.get("FORMAT", "mp3")
    quality = os.environ.get("QUALITY", "320k")

    if not url.startswith("http"):
        print("❌ لینک معتبر وارد کنید.")
        return

    output_dir = "output/spotify"
    os.makedirs(output_dir, exist_ok=True)

    # ۱. دانلود با yt-dlp از Spotify -> جستجو در YouTube
    # انتخاب فرمت صوتی بر اساس ورودی
    if fmt == "mp3":
        format_str = f"bestaudio[ext=m4a]/bestaudio/best"
        postprocess = [
            "--extract-audio",
            "--audio-format", "mp3",
            "--audio-quality", quality
        ]
    elif fmt == "flac":
        format_str = "bestaudio/best"
        postprocess = [
            "--extract-audio",
            "--audio-format", "flac",
            "--audio-quality", "0"  # best for flac
        ]
    else:  # m4a
        format_str = "bestaudio[ext=m4a]/bestaudio"
        postprocess = []

    cmd = [
        "yt-dlp",
        "-f", format_str,
        "--no-playlist" if "/track/" in url else "",  # فقط برای تک‌آهنگ، پلی‌لیست کامل
        "--yes-playlist" if "/playlist/" in url or "/album/" in url else "",
        "--ignore-errors",
        "--no-overwrites",
        "--embed-thumbnail",
        "--add-metadata",
        "-o", f"{output_dir}/%(artist)s - %(title)s.%(ext)s"
    ]
    # حذف آرگومان‌های خالی
    cmd = [c for c in cmd if c]
    # اضافه کردن postprocessors
    cmd.extend(postprocess)
    cmd.append(url)

    print(f"▶️ اجرا: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)
        print(result.stdout)
        if result.returncode != 0:
            print(f"❌ yt-dlp خطا داد:\n{result.stderr}")
            return
    except subprocess.TimeoutExpired:
        print("⏰ زمان دانلود تمام شد.")
        return

    # ۲. ساخت ZIP چندبخشی از کل پوشه
    songs = list(Path(output_dir).glob(f"*.{fmt}"))
    if not songs:
        print("⚠️ هیچ فایلی دانلود نشد.")
        return

    print("🗜️ ساخت ZIP چندبخشی...")
    zip_name = "spotify_playlist.zip"
    zip_path = os.path.join(output_dir, zip_name)
    subprocess.run(
        ["zip", "-s", f"{SPLIT_MB}m", "-r", zip_path, "."],
        cwd=output_dir, capture_output=True, text=True
    )

    # حذف فایل‌های صوتی اصلی برای کاهش حجم ریپو
    for f in songs:
        try:
            os.remove(str(f))
            print(f"🗑️ پاک شد: {f.name}")
        except Exception as e:
            print(f"⚠️ خطا در حذف {f.name}: {e}")

    print("✅ ZIP آماده است. فایل‌ها در output/spotify قرار دارند.")

if __name__ == "__main__":
    main()
