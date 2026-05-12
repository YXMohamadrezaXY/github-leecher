import os
import time
import requests
import subprocess
import re
from urllib.parse import urljoin, urlparse
from playwright.sync_api import sync_playwright

# ---------- توابع کمکی ----------
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
        print(f"خطا در دانلود مستقیم {url}: {e}")
        return False

# ---------- استخراج عکس ----------
def extract_images(page, url):
    print("🖼️ استخراج عکس‌ها...")
    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except:
        pass
    time.sleep(1)
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    time.sleep(1.5)
    page.evaluate("window.scrollTo(0, 0)")
    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except:
        pass

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

# ---------- رهگیری شبکه (لایه اول) ----------
def capture_media_urls(page, url, max_videos=5, wait_seconds=15):
    """تمام درخواست‌های رسانه‌ای (mp4, webm, m3u8, ...) را جمع می‌کند."""
    video_urls = []
    video_extensions = (".mp4", ".webm", ".m3u8", ".ts", ".mkv", ".mov", ".avi", ".flv")

    def intercept(request):
        try:
            if request.resource_type == "media" or any(request.url.lower().endswith(ext) for ext in video_extensions):
                if request.url not in video_urls:
                    video_urls.append(request.url)
            request.continue_()
        except:
            request.continue_()

    page.route("**/*", intercept)
    print("🔄 بارگذاری مجدد برای رهگیری ویدئوها...")
    try:
        page.goto(url, timeout=30000)
    except Exception as e:
        print(f"خطا در بارگذاری برای رهگیری: {e}")
        page.unroute("**/*")
        return []

    # انجام اسکرول برای فعال‌سازی پخش ویدئوهای تنبل
    print("📜 اسکرول صفحه برای فعال‌سازی محتوای تنبل...")
    for _ in range(3):
        page.evaluate("window.scrollBy(0, 300)")
        time.sleep(0.5)
    page.evaluate("window.scrollTo(0, 0)")
    
    print(f"⏳ منتظر دریافت فایل‌های ویدئویی ({wait_seconds} ثانیه)...")
    time.sleep(wait_seconds)
    page.unroute("**/*")

    unique = list(dict.fromkeys(video_urls))
    final = unique[:max_videos]
    print(f"📹 تعداد فایل‌های ویدئویی یافت‌شده: {len(final)}")
    for v in final:
        print(f"   {v}")
    return final

# ---------- Invidious (برای یوتیوب بدون تحریم) ----------
def get_best_invidious_instance():
    try:
        resp = requests.get("https://api.invidious.io/instances.json?sort=health", timeout=10)
        data = resp.json()
        for item in data:
            if isinstance(item, list) and len(item) > 1:
                info = item[1]
                if info.get("type") == "https" and info.get("api") and info["monitor"]["statusClass"] == "success":
                    uri = info["uri"]
                    print(f"🔗 استفاده از Invidious: {uri}")
                    return uri.rstrip("/")
    except Exception as e:
        print(f"⚠️ خطا در دریافت لیست Invidious: {e}")
    return None

def convert_youtube_to_invidious(url):
    parsed = urlparse(url)
    if "youtube.com" in parsed.netloc or "youtu.be" in parsed.netloc:
        if "youtu.be" in parsed.netloc:
            vid_id = parsed.path.strip("/")
        else:
            qs = dict(part.split("=", 1) for part in parsed.query.split("&") if "=" in part)
            vid_id = qs.get("v")
        if vid_id:
            instance = get_best_invidious_instance()
            if instance:
                return f"{instance}/watch?v={vid_id}"
    return url

# ---------- yt-dlp قدرتمند (لایه دوم) ----------
def download_with_ytdlp(url, output_dir, max_videos, quality="best"):
    """yt-dlp با Deno، هدر Referer، و bypass جغرافیایی"""
    print(f"📥 استفاده از yt-dlp برای دانلود از: {url}")
    
    # تبدیل یوتیوب به Invidious (بدون کوکی)
    url = convert_youtube_to_invidious(url)
    
    outtmpl = os.path.join(output_dir, "%(title)s.%(ext)s")
    cmd = [
        "yt-dlp",
        "-f", quality,
        "--js-runtimes", "deno",
        "--no-playlist",
        "--max-downloads", str(max_videos),
        "--max-filesize", "500M",
        "--geo-bypass",
        "--add-header", f"Referer:{url}",  # اضافه کردن Referer
        "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "-o", outtmpl,
        url
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        print(result.stdout)
        if result.returncode != 0:
            print(f"yt-dlp خطا:\n{result.stderr}")
            # تلاش با best
            fallback_cmd = [arg if arg != quality else "best" for arg in cmd]
            result2 = subprocess.run(fallback_cmd, capture_output=True, text=True, timeout=300)
            if result2.returncode == 0:
                print("fallback to best succeeded")
            else:
                print(f"fallback also failed:\n{result2.stderr}")
                return 0
        count = len([f for f in os.listdir(output_dir) if os.path.isfile(os.path.join(output_dir, f))])
        return count
    except Exception as e:
        print(f"yt-dlp exception: {e}")
        return 0

# ---------- تابع اصلی ----------
def main():
    url = os.environ["INPUT_URL"].strip()
    max_videos = int(os.environ.get("INPUT_MAX_VIDEOS", "5"))
    quality_input = os.environ.get("INPUT_QUALITY", "بهترین کیفیت").strip()
    ytdl_quality = "best" if quality_input == "بهترین کیفیت" else quality_input

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

        print(f"🌐 بارگذاری اولیه: {url}")
        try:
            page.goto(url, timeout=30000)
        except Exception as e:
            print(f"❌ خطا در بارگذاری اولیه: {e}")
            browser.close()
            with open(f"{output_dir}/report.txt", "w", encoding="utf-8") as f:
                f.write(f"❌ خطا در بارگذاری: {e}")
            return

        images = extract_images(page, url)

        # رهگیری شبکه (از یک صفحه جدید با rate limit)
        page2 = context.new_page()
        video_urls = capture_media_urls(page2, url, max_videos, wait_seconds=15)
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
    if video_urls:
        print("📁 استفاده از فایل‌های رهگیری‌شده...")
        for video_url in video_urls:
            ext = None
            for v_ext in ("mp4", "webm", "mkv", "mov", "avi", "flv", "ts", "m3u8"):
                if video_url.lower().endswith(v_ext):
                    ext = v_ext
                    break
            if ext == "m3u8":
                outtmpl = os.path.join(vid_dir, "%(title)s.%(ext)s")
                subprocess.run(["yt-dlp", "-f", "best", "-o", outtmpl, video_url], capture_output=True, timeout=120)
                vid_downloaded += 1
            else:
                fname = sanitize_filename(video_url, ext=ext if ext else "mp4")
                if download_file(video_url, os.path.join(vid_dir, fname), headers={"Referer": url}):
                    vid_downloaded += 1
    else:
        print("🔍 رهگیری شبکه نتیجه‌ای نداشت → yt-dlp")
        vid_downloaded = download_with_ytdlp(url, vid_dir, max_videos, ytdl_quality)

    # گزارش
    report = f"✅ دانلود از {url} کامل شد.\n"
    report += f"🖼️ عکس‌های دانلود شده: {img_downloaded} از {len(images)}\n"
    report += f"🎥 فیلم‌های دانلود شده: {vid_downloaded} (حداکثر درخواستی: {max_videos})\n"
    report += f"📁 فایل‌ها در `output/media` قرار دارند."
    with open(f"{output_dir}/report.txt", "w", encoding="utf-8") as f:
        f.write(report)
    print(report)

if __name__ == "__main__":
    main()
