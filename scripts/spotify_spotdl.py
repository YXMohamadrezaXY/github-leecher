import os
import subprocess
from pathlib import Path

SPLIT_MB = 90

def main():
    url = os.environ["SPOTIFY_URL"].strip()
    fmt = os.environ.get("FORMAT", "mp3")
    quality = os.environ.get("QUALITY", "320k")

    if not url.startswith("http"):
        print("❌ لینک معتبر وارد کنید.")
        return

    output_dir = "output/spotify"
    os.makedirs(output_dir, exist_ok=True)

    # استفاده از --audio piped (آرگومان صحیح در نسخه‌های جدیدتر)
    cmd = [
        "spotdl", "download", url,
        "--format", fmt,
        "--bitrate", quality,
        "--audio", "piped",
        "--output", str(Path(output_dir) / "{artists} - {title}.{output-ext}")
    ]
    if fmt == "flac":
        cmd = [c for c in cmd if c != "--bitrate" and c != quality]

    print(f"▶️ اجرا: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        print(result.stdout)
        if result.returncode != 0:
            print(f"❌ خطای spotdl:\n{result.stderr}")
            # تلاش با youtube-music
            print("🔄 تلاش با youtube-music...")
            cmd2 = [c if c != "piped" else "youtube-music" for c in cmd]
            result2 = subprocess.run(cmd2, capture_output=True, text=True, timeout=3600)
            print(result2.stdout)
            if result2.returncode != 0:
                print(f"❌ باز هم شکست:\n{result2.stderr}")
                return
    except subprocess.TimeoutExpired:
        print("⏰ زمان تمام شد.")
        return

    # ساخت ZIP
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

    for f in songs:
        try:
            os.remove(str(f))
        except:
            pass

    print("✅ فایل‌های ZIP آماده هستند.")

if __name__ == "__main__":
    main()
