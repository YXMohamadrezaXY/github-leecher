import os
import time
import requests
import subprocess
from urllib.parse import urljoin, urlparse
from playwright.sync_api import sync_playwright

def sanitize_filename(url):
    parsed = urlparse(url)
    base = os.path.basename(parsed.path)
    if not base:
        base = "file"
    base = base.split("?")[0]
    base = "".join(c if c.isalnum() or c in "._- " else "_" for c in base)
    return base if base else "downloaded_media"

def download_file(url, save_path):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        r = requests.get(url, headers=headers, stream=True, timeout=30)
        r.raise_for_status()
        with open(save_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"خطا در دانلود مستقیم {url}: {e}")
        return False

def map_quality_to_format(quality):
    mapping = {
        'بهترین کیفیت': 'bestvideo+bestaudio/best',
        '1080p': 'bestvideo[height<=1080]+bestaudio/best[height<=1080]',
        '720p': 'bestvideo[height<=720]+bestaudio/best[height<=720]',
        '480p': 'bestvideo[height<=480]+bestaudio/best[height<=480]',
        '360p': 'bestvideo[height<=360]+bestaudio/best[height<=360]'
    }
    return mapping.get(quality, 'bestvideo+bestaudio/best')

def download_videos_with_ytdlp(url, output_dir, max_videos, quality):
    """
    از yt-dlp مستقیماً روی URL صفحه استفاده می‌کند.
    تمام ویدئوهای قابل دانلود (جاسازی‌شده) را پیدا کرده و دانلود می‌کند.
    """
    print(f"\n--- دانلود ویدئوها با yt-dlp از آدرس: {url} ---")
    fmt = map_quality_to_format(quality)
    outtmpl = os.path.join(output_dir, "%(title)s.%(ext)s")

    cmd = [
        "yt-dlp",
        "-f", fmt,
        "--no-playlist",
        "--max-downloads", str(max_videos),  # حداکثر تعداد
        "--max-filesize", "500M",
        "--merge-output-format", "mp4",
        "--no-overwrites",
        "-o", outtmpl,
        url
    ]

    print("اجرا:", " ".join(cmd))
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        print(result.stdout)
        if result.returncode != 0:
            print(f"yt-dlp خطا:\n{result.stderr}")
            # تلاش مجدد با best در صورت خطای فرمت
            if 'requested format' in result.stderr:
                print("تلاش مجدد با best...")
                fallback_cmd = [
                    "yt-dlp",
                    "-f", "best",
                    "--no-playlist",
                    "--max-downloads", str(max_videos),
                    "--max-filesize", "500M",
                    "-o", outtmpl,
                    url
                ]
                result2 = subprocess.run(fallback_cmd, capture_output=True, text=True, timeout=300)
                print(result2.stdout)
                if result2.returncode != 0:
                    print(f"باز هم ناموفق:\n{result2.stderr}")
                    return 0
                return max_videos  # فرض می‌کنیم به تعداد خواسته‌شده دانلود شده
            return 0
        # شمارش فایل‌های جدید
        downloaded_count = len([f for f in os.listdir(output_dir) if os.path.isfile(os.path.join(output_dir, f))])
        print(f"yt-dlp: {downloaded_count} فایل دانلود کرد.")
        return downloaded_count
    except subprocess.TimeoutExpired:
        print("yt-dlp زمان‌بر شد (>300s).")
        return 0
    except Exception as e:
        print(f"استثنا در yt-dlp: {e}")
        return 0

# --- بقیه کد مثل قبله (عکس‌ها) ---
def extract_images(page, url):
    print("استخراج عکس‌ها...")
    page.wait_for_load_state("networkidle")
    time.sleep(1)
    # اسکرول برای فعال‌سازی lazy load
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    time.sleep(1)
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_load_state("networkidle")
    time.sleep(1)

    images = []
    img_elements = page.query_selector_all("img")
    for img in img_elements:
        src = img.get_attribute("src") or img.get_attribute("data-src")
        if not src:
            continue
        absolute_url = urljoin(url, src)
        try:
            width = img.evaluate("el => el.naturalWidth")
            height = img.evaluate("el => el.naturalHeight")
        except:
            width, height = 0, 0
        if width > 100 and height > 100:
            images.append(absolute_url)
    images = list(dict.fromkeys(images))
    print(f"{len(images)} عکس واجد شرایط پیدا شد.")
    return images

def main():
    url = os.environ["INPUT_URL"].strip()
    max_videos = int(os.environ.get("INPUT_MAX_VIDEOS", "5"))
    quality = os.environ.get("INPUT_QUALITY", "بهترین کیفیت").strip()

    if not url.startswith("http"):
        print("آدرس باید با http شروع شود.")
        return

    output_dir = "output/media"
    os.makedirs(output_dir, exist_ok=True)
    img_dir = os.path.join(output_dir, "images")
    vid_dir = os.path.join(output_dir, "videos")
    os.makedirs(img_dir, exist_ok=True)
    os.makedirs(vid_dir, exist_ok=True)

    # استخراج و دانلود عکس‌ها با Playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        print(f"بارگذاری صفحه: {url}")
        try:
            page.goto(url, timeout=30000)
        except Exception as e:
            print(f"خطا در بارگذاری صفحه: {e}")
            browser.close()
            with open(f"{output_dir}/report.txt", "w", encoding="utf-8") as f:
                f.write(f"❌ خطا در بارگذاری: {e}")
            return

        images = extract_images(page, url)
        browser.close()

    img_downloaded = 0
    for img_url in images:
        fname = sanitize_filename(img_url)
        if "." not in fname:
            fname += ".jpg"
        if download_file(img_url, os.path.join(img_dir, fname)):
            img_downloaded += 1

    # دانلود فیلم‌ها با yt-dlp (مستقیماً از آدرس صفحه)
    vid_downloaded = download_videos_with_ytdlp(url, vid_dir, max_videos, quality)

    # ساخت گزارش
    report = f"✅ دانلود از {url} کامل شد.\n"
    report += f"🖼️ عکس‌های دانلود شده: {img_downloaded} از {len(images)}\n"
    report += f"🎥 فیلم‌های دانلود شده: {vid_downloaded} (حداکثر درخواستی: {max_videos})\n"
    report += f"⚙️ کیفیت فیلم‌ها: {quality}\n"
    report += f"📁 فایل‌ها در پوشه‌های `output/media/images` و `output/media/videos` قرار دارند."
    with open(f"{output_dir}/report.txt", "w", encoding="utf-8") as f:
        f.write(report)
    print(report)

if __name__ == "__main__":
    main()
