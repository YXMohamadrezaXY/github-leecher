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
        print(f"خطا در دانلود {url}: {e}")
        return False

def map_quality_to_format(quality):
    """تبدیل گزینه‌های انتخابی به فرمت yt-dlp"""
    mapping = {
        'بهترین کیفیت': 'best',
        '1080p': 'bestvideo[height<=1080]+bestaudio/best[height<=1080]',
        '720p': 'bestvideo[height<=720]+bestaudio/best[height<=720]',
        '480p': 'bestvideo[height<=480]+bestaudio/best[height<=480]',
        '360p': 'bestvideo[height<=360]+bestaudio/best[height<=360]'
    }
    return mapping.get(quality, 'best')

def download_with_ytdlp(url, output_dir, quality):
    """دانلود ویدئوی جاسازی شده با yt-dlp و کیفیت انتخابی."""
    fmt = map_quality_to_format(quality)
    print(f"دانلود با yt-dlp (کیفیت: {quality}): {url}")
    outtmpl = os.path.join(output_dir, "%(title)s.%(ext)s")
    cmd = [
        "yt-dlp",
        "-f", fmt,
        "--no-playlist",
        "--max-filesize", "500M",
        "-o", outtmpl,
        url
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            print("yt-dlp موفق بود.")
            return True
        else:
            print(f"yt-dlp خطا داد:\n{result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        print("yt-dlp زمان‌بر شد (بیش از ۲ دقیقه).")
        return False
    except Exception as e:
        print(f"استثنا در yt-dlp: {e}")
        return False

def extract_media(page, url, max_videos=5):
    page.wait_for_load_state("load")
    time.sleep(2)

    print("استخراج عکس‌ها...")
    images = []
    img_elements = page.query_selector_all("img")
    for img in img_elements:
        src = img.get_attribute("src")
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

    print("استخراج فیلم‌های مستقیم...")
    direct_videos = []
    video_elements = page.query_selector_all("video")
    for video in video_elements:
        src = video.get_attribute("src")
        if not src:
            source_elements = video.query_selector_all("source")
            for source in source_elements:
                src = source.get_attribute("src")
                if src:
                    break
        if src:
            absolute_url = urljoin(url, src)
            if absolute_url not in direct_videos:
                direct_videos.append(absolute_url)

    print("استخراج فیلم‌های جاسازی شده (iframe)...")
    embedded_urls = []
    iframe_elements = page.query_selector_all("iframe")
    known_video_domains = [
        "youtube.com", "youtu.be",
        "vimeo.com",
        "dailymotion.com",
        "twitch.tv",
        "facebook.com/plugins/video",
        "player.vimeo.com",
        "video.ibm.com",
        "vlive.tv"
    ]
    for iframe in iframe_elements:
        src = iframe.get_attribute("src")
        if not src:
            continue
        src_absolute = urljoin(url, src)
        parsed = urlparse(src_absolute)
        domain = parsed.netloc.lower()
        if any(k in domain for k in known_video_domains):
            if src_absolute not in embedded_urls:
                embedded_urls.append(src_absolute)

    all_videos = direct_videos + embedded_urls
    unique_videos = list(dict.fromkeys(all_videos))
    final_videos = unique_videos[:max_videos]
    print(f"مجموعاً {len(final_videos)} فیلم برای دانلود انتخاب شد.")
    return images, final_videos

def main():
    url = os.environ["INPUT_URL"].strip()
    max_videos = int(os.environ.get("INPUT_MAX_VIDEOS", "5"))
    quality = os.environ.get("INPUT_QUALITY", "بهترین کیفیت").strip()

    if not url.startswith("http"):
        print("آدرس باید با http شروع شود.")
        return

    output_dir = "output/media"
    os.makedirs(output_dir, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        print(f"بارگذاری صفحه: {url}")
        try:
            page.goto(url, timeout=30000)
        except Exception as e:
            print(f"خطا در بارگذاری: {e}")
            browser.close()
            with open(f"{output_dir}/report.txt", "w", encoding="utf-8") as f:
                f.write(f"❌ خطا در بارگذاری: {e}")
            return

        images, videos = extract_media(page, url, max_videos)
        browser.close()

    # دانلود عکس‌ها
    img_dir = os.path.join(output_dir, "images")
    os.makedirs(img_dir, exist_ok=True)
    downloaded_images = 0
    for img_url in images:
        fname = sanitize_filename(img_url)
        if "." not in fname:
            fname += ".jpg"
        save_path = os.path.join(img_dir, fname)
        if download_file(img_url, save_path):
            downloaded_images += 1

    # دانلود فیلم‌ها
    vid_dir = os.path.join(output_dir, "videos")
    os.makedirs(vid_dir, exist_ok=True)
    downloaded_videos = 0
    direct_extensions = (".mp4", ".webm", ".ogg", ".mkv", ".avi", ".mov", ".flv")
    for vid_url in videos:
        if any(vid_url.lower().endswith(ext) for ext in direct_extensions):
            fname = sanitize_filename(vid_url)
            save_path = os.path.join(vid_dir, fname)
            if download_file(vid_url, save_path):
                downloaded_videos += 1
        else:
            if download_with_ytdlp(vid_url, vid_dir, quality):
                downloaded_videos += 1

    report = f"✅ دانلود از {url} کامل شد.\n"
    report += f"🖼️ عکس‌های دانلود شده: {downloaded_images} از {len(images)}\n"
    report += f"🎥 فیلم‌های دانلود شده: {downloaded_videos} از {len(videos)}\n"
    report += f"⚙️ کیفیت فیلم‌های جاسازی: {quality}\n"
    report += f"📁 فایل‌ها در پوشه‌های `output/media/images` و `output/media/videos` قرار دارند."
    with open(f"{output_dir}/report.txt", "w", encoding="utf-8") as f:
        f.write(report)
    print(report)

if __name__ == "__main__":
    main()
