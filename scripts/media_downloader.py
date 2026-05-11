import os
import time
import requests
import subprocess
from urllib.parse import urljoin, urlparse
from playwright.sync_api import sync_playwright

def sanitize_filename(url, ext=None):
    parsed = urlparse(url)
    base = os.path.basename(parsed.path)
    if not base:
        base = "video" if ext else "file"
    base = base.split("?")[0]
    if ext and "." not in base:
        base += f".{ext}"
    base = "".join(c if c.isalnum() or c in "._- " else "_" for c in base)
    return base

def download_file(url, save_path, headers=None):
    try:
        default_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        if headers:
            default_headers.update(headers)
        r = requests.get(url, headers=default_headers, stream=True, timeout=60)
        r.raise_for_status()
        with open(save_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"خطا در دانلود {url}: {e}")
        return False

def extract_images(page, url):
    print("استخراج عکس‌ها...")
    page.wait_for_load_state("networkidle")
    time.sleep(1)
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    time.sleep(1.5)
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_load_state("networkidle")

    images = []
    for img in page.query_selector_all("img"):
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

def capture_video_urls(page, url, max_videos=5):
    """
    با رهگیری شبکه، همهٔ درخواست‌های ویدئویی را ضبط می‌کند.
    برای فعال‌سازی پخش، صفحه را reload می‌کند و کمی صبر می‌کند.
    """
    video_urls = []
    video_extensions = (".mp4", ".webm", ".m3u8", ".ts", ".mkv", ".mov", ".avi", ".flv")

    def intercept(request):
        if request.resource_type == "media" or any(request.url.lower().endswith(ext) for ext in video_extensions):
            if request.url not in video_urls:
                video_urls.append(request.url)
        request.continue_()

    page.route("**/*", intercept)
    print("بارگذاری مجدد صفحه برای رهگیری ویدئوها...")
    page.goto(url, timeout=30000)
    # صبر برای پخش ویدئوها
    print("منتظر دریافت فایل‌های ویدئویی توسط مرورگر...")
    time.sleep(8)  # می‌توانید تا 15 ثانیه افزایش دهید
    page.unroute("**/*")

    unique = list(dict.fromkeys(video_urls))
    final = unique[:max_videos]
    print(f"تعداد فایل‌های ویدئویی یافت‌شده: {len(final)}")
    for v in final:
        print(f"  {v}")
    return final

def main():
    url = os.environ["INPUT_URL"].strip()
    max_videos = int(os.environ.get("INPUT_MAX_VIDEOS", "5"))

    if not url.startswith("http"):
        print("آدرس باید با http شروع شود.")
        return

    output_dir = "output/media"
    os.makedirs(output_dir, exist_ok=True)
    img_dir = os.path.join(output_dir, "images")
    vid_dir = os.path.join(output_dir, "videos")
    os.makedirs(img_dir, exist_ok=True)
    os.makedirs(vid_dir, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        print(f"بارگذاری اولیه: {url}")
        try:
            page.goto(url, timeout=30000)
        except Exception as e:
            print(f"خطا در بارگذاری: {e}")
            browser.close()
            with open(f"{output_dir}/report.txt", "w", encoding="utf-8") as f:
                f.write(f"❌ خطا در بارگذاری: {e}")
            return

        # عکس‌ها از همین صفحه
        images = extract_images(page, url)

        # یک صفحهٔ جدید برای رهگیری ویدئوها (تا با عکس‌ها تداخل نکند)
        page2 = context.new_page()
        video_urls = capture_video_urls(page2, url, max_videos)
        page2.close()
        browser.close()

    # دانلود عکس‌ها
    img_downloaded = 0
    for img_url in images:
        fname = sanitize_filename(img_url)
        if "." not in fname:
            fname += ".jpg"
        if download_file(img_url, os.path.join(img_dir, fname)):
            img_downloaded += 1

    # دانلود ویدئوها
    vid_downloaded = 0
    for video_url in video_urls:
        ext = None
        for v_ext in ("mp4", "webm", "mkv", "mov", "avi", "flv", "ts", "m3u8"):
            if video_url.lower().endswith(v_ext):
                ext = v_ext
                break
        if ext == "m3u8":
            print(f"دانلود HLS با yt-dlp: {video_url}")
            outtmpl = os.path.join(vid_dir, "%(title)s.%(ext)s")
            cmd = ["yt-dlp", "-f", "best", "--no-playlist", "--max-filesize", "500M", "-o", outtmpl, video_url]
            try:
                subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=120)
                vid_downloaded += 1
            except Exception as e:
                print(f"yt-dlp شکست خورد: {e}")
        else:
            fname = sanitize_filename(video_url, ext=ext if ext else "mp4")
            headers = {"Referer": url}
            if download_file(video_url, os.path.join(vid_dir, fname), headers=headers):
                vid_downloaded += 1

    report = f"✅ دانلود از {url} کامل شد.\n"
    report += f"🖼️ عکس‌های دانلود شده: {img_downloaded} از {len(images)}\n"
    report += f"🎥 فیلم‌های دانلود شده: {vid_downloaded} (حداکثر درخواستی: {max_videos})\n"
    report += f"📁 فایل‌ها در پوشه‌های `output/media/images` و `output/media/videos` قرار دارند."
    with open(f"{output_dir}/report.txt", "w", encoding="utf-8") as f:
        f.write(report)
    print(report)

if __name__ == "__main__":
    main()
