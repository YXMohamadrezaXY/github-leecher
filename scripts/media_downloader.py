import os
import time
import requests
import subprocess
from urllib.parse import urljoin, urlparse
from playwright.sync_api import sync_playwright

# ---------- تنظیمات ----------
MIN_VIDEO_SIZE_KB = 100  # فایل‌های کوچکتر از ۱۰۰ کیلوبایت را رد می‌کنیم

def sanitize_filename(url, ext=None):
    parsed = urlparse(url)
    base = os.path.basename(parsed.path)
    if not base:
        base = "video" if ext else "file"
    base = base.split("?")[0]
    if ext and "." not in base:
        base += f".{ext}"
    return "".join(c if c.isalnum() or c in "._- " else "_" for c in base)

def download_file(url, save_path, headers=None):
    try:
        default_headers = {"User-Agent": "Mozilla/5.0"}
        if headers:
            default_headers.update(headers)
        r = requests.get(url, headers=default_headers, stream=True, timeout=120)
        r.raise_for_status()
        with open(save_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"خطا در دانلود مستقیم: {e}")
        return False

def extract_images(page, url):
    print("🖼️ استخراج عکس‌ها...")
    try: page.wait_for_load_state("networkidle", timeout=10000)
    except: pass
    time.sleep(2)
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    time.sleep(2)
    page.evaluate("window.scrollTo(0, 0)")
    try: page.wait_for_load_state("networkidle", timeout=10000)
    except: pass

    images = []
    for img in page.query_selector_all("img"):
        src = img.get_attribute("src") or img.get_attribute("data-src")
        if not src: continue
        absolute_url = urljoin(url, src)
        try:
            w = img.evaluate("el => el.naturalWidth")
            h = img.evaluate("el => el.naturalHeight")
        except: w, h = 0, 0
        if w > 100 and h > 100 and absolute_url not in images:
            images.append(absolute_url)
    print(f"{len(images)} عکس واجد شرایط پیدا شد.")
    return images

def click_possible_play_buttons(page):
    """روی دکمه‌های Play و خود ویدئو کلیک می‌کند تا پخش شروع شود."""
    print("🔍 جستجوی دکمه‌های Play...")
    selectors = [
        "button[aria-label*='play']",
        "button[aria-label*='Play']",
        "button.play",
        ".play-button",
        "[class*='play']",
        "video",
        ".video-js .vjs-big-play-button"
    ]
    clicked = False
    for sel in selectors:
        for elem in page.query_selector_all(sel):
            try:
                if elem.is_visible():
                    elem.click()
                    print(f"✅ کلیک روی: {elem.evaluate('el => el.outerHTML')[:80]}...")
                    clicked = True
                    time.sleep(1)
            except: pass
    if not clicked:
        video_elem = page.query_selector("video")
        if video_elem:
            try:
                video_elem.click()
                print("✅ کلیک روی <video>")
                clicked = True
                time.sleep(1)
            except: pass
    return clicked

def capture_media_after_interaction(page, url, max_videos=5, wait_seconds=30):
    """با کلیک‌های قوی، ۳۰ ثانیه صبر می‌کند و شبکه را رهگیری می‌کند."""
    video_urls = []
    video_extensions = (".mp4", ".webm", ".m3u8", ".ts", ".mkv", ".mov", ".avi", ".flv")

    def intercept(request):
        try:
            if request.resource_type == "media" or any(request.url.lower().endswith(ext) for ext in video_extensions):
                if request.url not in video_urls:
                    video_urls.append(request.url)
            request.continue_()
        except: request.continue_()

    page.route("**/*", intercept)
    # کلیک‌ها را تکرار کن
    click_possible_play_buttons(page)
    time.sleep(1)
    # کمی اسکرول برای تحریک lazy load
    page.evaluate("window.scrollBy(0, 400)")
    time.sleep(0.5)
    page.evaluate("window.scrollTo(0, 0)")
    print(f"⏳ منتظر دریافت فایل‌های ویدئویی ({wait_seconds} ثانیه)...")
    time.sleep(wait_seconds)
    page.unroute("**/*")

    unique = list(dict.fromkeys(video_urls))
    final = unique[:max_videos]
    print(f"📹 تعداد فایل‌های ویدئویی یافت‌شده: {len(final)}")
    for v in final: print(f"   {v}")
    return final

def download_with_ytdlp(url, output_dir, max_videos, quality="bestvideo+bestaudio/best"):
    """yt-dlp با gالیت بالا و اعتبارسنجی فایل خروجی."""
    print(f"📥 yt-dlp روی: {url}")
    outtmpl = os.path.join(output_dir, "%(title)s.%(ext)s")
    cmd = [
        "yt-dlp",
        "-f", quality,
        "--no-playlist",
        "--max-downloads", str(max_videos),
        "--max-filesize", "500M",
        "--merge-output-format", "mp4",
        "--user-agent", "Mozilla/5.0",
        "-o", outtmpl,
        url
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        print(result.stdout)
        if result.returncode != 0:
            print(f"yt-dlp خطا:\n{result.stderr}")
            # fallback with best
            fallback = ["yt-dlp", "-f", "best", "--no-playlist", "--max-downloads", str(max_videos),
                        "--max-filesize", "500M", "-o", outtmpl, url]
            subprocess.run(fallback, capture_output=True, timeout=300)
        
        # اعتبارسنجی فایل‌های تولیدشده
        valid_count = 0
        valid_exts = (".mp4", ".webm", ".mkv", ".mov", ".avi", ".flv")
        for f in os.listdir(output_dir):
            fp = os.path.join(output_dir, f)
            if os.path.isfile(fp) and f.lower().endswith(valid_exts):
                size_kb = os.path.getsize(fp) / 1024
                if size_kb >= MIN_VIDEO_SIZE_KB:
                    valid_count += 1
                else:
                    print(f"🗑️ حذف فایل کم‌حجم: {f} ({size_kb:.1f} KB)")
                    os.remove(fp)
            else:
                # حذف فایل‌های غیرویدیویی
                if os.path.isfile(fp) and not f.endswith(".txt"):
                    os.remove(fp)
        return valid_count
    except Exception as e:
        print(f"yt-dlp exception: {e}")
        return 0

def main():
    url = os.environ["INPUT_URL"].strip()
    max_videos = int(os.environ.get("INPUT_MAX_VIDEOS", "5"))
    if not url.startswith("http"):
        print("آدرس باید با http شروع شود.")
        return

    output_dir = "output/media"
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
        print(f"🌐 بارگذاری: {url}")
        try:
            page.goto(url, timeout=30000)
            page.wait_for_load_state("load")
        except Exception as e:
            print(f"❌ خطا: {e}")
            browser.close()
            with open(f"{output_dir}/report.txt", "w") as f:
                f.write(f"❌ خطا: {e}")
            return

        images = extract_images(page, url)

        # صفحه جدید برای رهگیری بدون تداخل
        page2 = context.new_page()
        page2.goto(url, timeout=30000)
        page2.wait_for_load_state("load")
        time.sleep(2)
        video_urls = capture_media_after_interaction(page2, url, max_videos, wait_seconds=30)
        page2.close()
        browser.close()

    # عکس‌ها
    img_downloaded = 0
    for img_url in images:
        fname = sanitize_filename(img_url, "jpg")
        if download_file(img_url, os.path.join(img_dir, fname)):
            img_downloaded += 1

    # ویدئوها
    vid_downloaded = 0
    if video_urls:
        for vurl in video_urls:
            ext = "mp4"
            for e in ("mp4", "webm", "mkv", "mov", "avi", "flv", "ts", "m3u8"):
                if vurl.lower().endswith(e):
                    ext = e; break
            if ext == "m3u8":
                # yt-dlp سریع
                outtmpl = os.path.join(vid_dir, "%(title)s.%(ext)s")
                subprocess.run(["yt-dlp", "-f", "best", "--no-playlist", "-o", outtmpl, vurl],
                               capture_output=True, timeout=120)
                # اعتبارسنجی مشابه
                for f in os.listdir(vid_dir):
                    if f.endswith((".mp4", ".webm")) and os.path.getsize(os.path.join(vid_dir, f)) > 100*1024:
                        vid_downloaded += 1
            else:
                fname = sanitize_filename(vurl, ext)
                if download_file(vurl, os.path.join(vid_dir, fname)):
                    if os.path.getsize(os.path.join(vid_dir, fname)) > MIN_VIDEO_SIZE_KB*1024:
                        vid_downloaded += 1
                    else:
                        os.remove(os.path.join(vid_dir, fname))
    else:
        print("🔍 رهگیری شبکه ۰ بود → yt-dlp")
        vid_downloaded = download_with_ytdlp(url, vid_dir, max_videos)

    report = f"✅ دانلود از {url} کامل شد.\n"
    report += f"🖼️ عکس‌ها: {img_downloaded}/{len(images)}\n"
    report += f"🎥 فیلم‌ها: {vid_downloaded} (حداکثر {max_videos})\n"
    with open(f"{output_dir}/report.txt", "w") as f:
        f.write(report)
    print(report)

if __name__ == "__main__":
    main()
