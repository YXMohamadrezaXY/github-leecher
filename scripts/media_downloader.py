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

def extract_images(page, url):
    """استخراج عکس‌های باکیفیت از صفحه"""
    print("استخراج عکس‌ها...")
    page.wait_for_load_state("networkidle")
    time.sleep(1)
    # اسکرول برای فعال‌سازی lazy loading
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    time.sleep(1.5)
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_load_state("networkidle")

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
            if absolute_url not in images:
                images.append(absolute_url)
    print(f"{len(images)} عکس واجد شرایط پیدا شد.")
    return images

def extract_video_urls(page, url):
    """
    استخراج همهٔ لینک‌های فیلم از صفحهٔ بارگذاری‌شده:
    - تگ <video> با src مستقیم
    - تگ <source> داخل video
    - iframe با src از دامنه‌های شناخته‌شده (youtube, vimeo, ...)
    - embedهای با src
    """
    print("استخراج لینک فیلم‌ها...")
    video_urls = []

    # ۱. تگ‌های video و source
    video_elements = page.query_selector_all("video")
    for video in video_elements:
        src = video.get_attribute("src")
        if src:
            video_urls.append(urljoin(url, src))
        else:
            sources = video.query_selector_all("source")
            for s in sources:
                src = s.get_attribute("src")
                if src:
                    video_urls.append(urljoin(url, src))

    # ۲. iframeهای ویدئویی معروف
    known_domains = [
        "youtube.com/embed", "youtube-nocookie.com", "youtu.be",
        "vimeo.com", "player.vimeo.com",
        "dailymotion.com/embed",
        "twitch.tv", "player.twitch.tv",
        "facebook.com/plugins/video",
        "video.ibm.com", "vlive.tv"
    ]
    iframe_elements = page.query_selector_all("iframe")
    for iframe in iframe_elements:
        src = iframe.get_attribute("src")
        if not src:
            continue
        abs_src = urljoin(url, src)
        parsed = urlparse(abs_src)
        path_and_domain = parsed.netloc + parsed.path
        if any(k in path_and_domain for k in known_domains):
            video_urls.append(abs_src)

    # ۳. تگ‌های embed
    embed_elements = page.query_selector_all("embed")
    for embed in embed_elements:
        src = embed.get_attribute("src")
        if src:
            video_urls.append(urljoin(url, src))

    # حذف تکراری‌ها
    unique_urls = list(dict.fromkeys(video_urls))
    print(f"{len(unique_urls)} لینک فیلم پیدا شد:")
    for u in unique_urls:
        print(f"  {u}")
    return unique_urls

def download_videos_with_ytdlp(video_urls, output_dir, quality):
    """
    با استفاده از yt-dlp، فایل urls.txt را می‌سازد و سپس batch دانلود می‌کند.
    """
    if not video_urls:
        print("هیچ لینک فیلمی برای دانلود وجود ندارد.")
        return 0

    # نوشتن لینک‌ها در یک فایل موقت
    batch_file = os.path.join(output_dir, "..", "video_urls.txt")
    with open(batch_file, "w") as f:
        for url in video_urls:
            f.write(url + "\n")

    fmt = map_quality_to_format(quality)
    outtmpl = os.path.join(output_dir, "%(title)s.%(ext)s")
    cmd = [
        "yt-dlp",
        "-f", fmt,
        "--no-playlist",
        "--max-filesize", "500M",
        "--merge-output-format", "mp4",
        "--no-overwrites",
        "-a", batch_file,     # حالت batch
        "-o", outtmpl
    ]
    print("اجرا:", " ".join(cmd))
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        print(result.stdout)
        if result.returncode != 0:
            print(f"yt-dlp خطا:\n{result.stderr}")
            # fallback
            fallback_cmd = [
                "yt-dlp",
                "-f", "best",
                "--no-playlist",
                "--max-filesize", "500M",
                "-a", batch_file,
                "-o", outtmpl
            ]
            print("تلاش با best...")
            result2 = subprocess.run(fallback_cmd, capture_output=True, text=True, timeout=300)
            print(result2.stdout)
            if result2.returncode != 0:
                print(f"باز هم ناموفق: {result2.stderr}")
                return 0
        # شمارش فایل‌های دانلود شده
        count = 0
        for f in os.listdir(output_dir):
            if os.path.isfile(os.path.join(output_dir, f)):
                count += 1
        return count
    except subprocess.TimeoutExpired:
        print("yt-dlp زمان‌بر شد (>300s).")
        return 0
    except Exception as e:
        print(f"استثنا در yt-dlp: {e}")
        return 0

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

    # --- Playwright: بارگذاری صفحه و استخراج ---
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

        # استخراج عکس‌ها
        images = extract_images(page, url)
        # استخراج لینک‌های فیلم (بعد از لود کامل)
        video_urls = extract_video_urls(page, url)
        browser.close()

    # --- دانلود عکس‌ها ---
    img_downloaded = 0
    for img_url in images:
        fname = sanitize_filename(img_url)
        if "." not in fname:
            fname += ".jpg"
        if download_file(img_url, os.path.join(img_dir, fname)):
            img_downloaded += 1

    # --- محدود کردن تعداد فیلم‌ها (در صورت نیاز) ---
    if len(video_urls) > max_videos:
        print(f"تعداد فیلم‌های یافت‌شده ({len(video_urls)}) بیش از حد مجاز ({max_videos}) است. {max_videos} انتخاب می‌شود.")
        video_urls = video_urls[:max_videos]

    # --- دانلود فیلم‌ها با yt-dlp ---
    vid_downloaded = download_videos_with_ytdlp(video_urls, vid_dir, quality)

    # --- گزارش ---
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
