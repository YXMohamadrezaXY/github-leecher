import os
import time
import re
import requests
import subprocess
from urllib.parse import urljoin, urlparse
from playwright.sync_api import sync_playwright

MIN_IMAGE_SIZE_KB = 5  # عکس‌های کوچکتر از ۵ کیلوبایت را رد می‌کنیم

def sanitize_filename(url, ext=None):
    """استخراج نام فایل معتبر از URL، با تشخیص پسوند."""
    parsed = urlparse(url)
    base = os.path.basename(parsed.path)
    if not base:
        base = "image" if ext else "file"
    base = base.split("?")[0]
    # اگر پسوندی در URL باشد، از آن استفاده کن
    if "." in base:
        # جدا کردن پسوند از نام
        name_part, url_ext = os.path.splitext(base)
        if url_ext.lower() in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"):
            ext = url_ext[1:]  # حذف نقطه
            base = name_part
    if ext and "." not in base:
        base += f".{ext}"
    return "".join(c if c.isalnum() or c in "._- " else "_" for c in base)

def download_file(url, save_path, headers=None):
    try:
        default_headers = {"User-Agent": "Mozilla/5.0"}
        if headers:
            default_headers.update(headers)
        r = requests.get(url, headers=default_headers, stream=True, timeout=60)
        r.raise_for_status()
        with open(save_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"❌ خطا در دانلود {url}: {e}")
        return False

def convert_to_original(url):
    """
    تبدیل URL پینترست به نسخه اصلی (originals).
    - جایگزینی /736x/، /474x/، /236x/ با /originals/
    - تغییر پسوند به png در صورت نیاز
    """
    if "pinimg.com" not in url:
        return url

    # جایگزینی سایز با originals
    modified = re.sub(r'/\d+x/', '/originals/', url)

    # اگر URL اصلی همان قبلی بود و originals در آن نیست، اضافه کن
    if "/originals/" not in modified:
        # الگوی دیگر: i.pinimg.com/236x/... --> i.pinimg.com/originals/...
        modified = re.sub(
            r'(i\.pinimg\.com)/(\d+x)/',
            r'\1/originals/',
            modified
        )

    # برخی تصاویر originals کیفیت بالاتری دارند، اما ممکن است jpg به png تبدیل شوند
    # (همانطور که در مستندات مشاهده شد)
    # این تغییر اختیاری است و می‌تواند کمک کند
    if "/originals/" in modified:
        # اگر پسوند jpg بود، سعی نکنیم به png تغییر دهیم (احتمال خطا)
        pass

    return modified

def extract_image_src(el):
    """بهترین منبع تصویر را با اولویت کیفیت اصلی Pinterest برمی‌گرداند."""
    # ۱. srcset (بیشترین وضوح)
    srcset = el.get_attribute("srcset")
    if srcset:
        candidates = re.findall(r'(\S+)\s+(\d+)w', srcset)
        if candidates:
            best = max(candidates, key=lambda x: int(x[1]))
            print(f"   📸 انتخاب از srcset: {best[1]}w -> {best[0][:80]}")
            return convert_to_original(best[0])

    # ۲. data-src / data-original / ...
    for attr in ("data-src", "data-original", "data-lazy-src", "data-srcset"):
        val = el.get_attribute(attr)
        if val:
            if attr.endswith("srcset"):
                candidates = re.findall(r'(\S+)\s+(\d+)w', val)
                if candidates:
                    best = max(candidates, key=lambda x: int(x[1]))
                    print(f"   📸 انتخاب از data-srcset: {best[1]}w")
                    return convert_to_original(best[0])
            print(f"   📸 انتخاب از {attr}")
            return convert_to_original(val)

    # ۳. src معمولی
    src = el.get_attribute("src")
    if src:
        print(f"   📸 استفاده از src")
        return convert_to_original(src)
    return None

def extract_images(page, url):
    print("🖼️ استخراج عکس‌های باکیفیت (با پشتیبانی از Pinterest originals)...")
    # اسکرول و صبر برای بارگذاری کامل
    for _ in range(3):
        page.evaluate("window.scrollBy(0, 800)")
        time.sleep(0.5)
    page.evaluate("window.scrollTo(0, 0)")
    time.sleep(1)
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except:
        pass

    images = []
    img_elements = page.query_selector_all("img")
    for idx, img in enumerate(img_elements):
        src = extract_image_src(img)
        if not src:
            continue
        absolute_url = urljoin(url, src.strip())
        try:
            width = img.evaluate("el => el.naturalWidth")
            height = img.evaluate("el => el.naturalHeight")
        except:
            width, height = 0, 0
        if width > 100 and height > 100:
            if absolute_url not in images:
                images.append(absolute_url)
                print(f"   ✅ عکس {idx+1}: {width}x{height} | {os.path.basename(absolute_url)[:60]}")
        else:
            print(f"   ⏭️ رد شد (ابعاد {width}x{height}): {os.path.basename(absolute_url)[:40]}")
    print(f"🎯 {len(images)} عکس واجد شرایط پیدا شد.")
    return images

# ---------- رهگیری شبکه برای ویدئوها (بدون تغییر) ----------
def click_possible_play_buttons(page):
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
            except:
                pass
    if not clicked:
        video_elem = page.query_selector("video")
        if video_elem:
            try:
                video_elem.click()
                print("✅ کلیک روی <video>")
                clicked = True
                time.sleep(1)
            except:
                pass
    return clicked

def capture_media_after_interaction(page, url, max_videos=5, wait_seconds=30):
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
    click_possible_play_buttons(page)
    time.sleep(1)
    page.evaluate("window.scrollBy(0, 400)")
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

def download_with_ytdlp(url, output_dir, max_videos, quality="bestvideo+bestaudio/best"):
    print(f"📥 yt-dlp روی: {url}")
    outtmpl = os.path.join(output_dir, "%(title)s.%(ext)s")
    cmd = [
        "yt-dlp", "-f", quality,
        "--no-playlist", "--max-downloads", str(max_videos),
        "--max-filesize", "500M", "--merge-output-format", "mp4",
        "--user-agent", "Mozilla/5.0",
        "-o", outtmpl, url
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        print(result.stdout)
        if result.returncode != 0:
            print(f"yt-dlp خطا:\n{result.stderr}")
            fallback = ["yt-dlp", "-f", "best", "--no-playlist", "--max-downloads", str(max_videos),
                        "--max-filesize", "500M", "-o", outtmpl, url]
            subprocess.run(fallback, capture_output=True, timeout=300)
        valid_count = 0
        valid_exts = (".mp4", ".webm", ".mkv", ".mov", ".avi", ".flv")
        for f in os.listdir(output_dir):
            fp = os.path.join(output_dir, f)
            if os.path.isfile(fp) and f.lower().endswith(valid_exts):
                if os.path.getsize(fp) > 100 * 1024:
                    valid_count += 1
                else:
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

        page2 = context.new_page()
        page2.goto(url, timeout=30000)
        page2.wait_for_load_state("load")
        time.sleep(2)
        video_urls = capture_media_after_interaction(page2, url, max_videos, wait_seconds=30)
        page2.close()
        browser.close()

    # --- دانلود عکس‌ها (حالا با لینک originals) ---
    img_downloaded = 0
    for img_url in images:
        fname = sanitize_filename(img_url)
        if "." not in fname:
            fname += ".jpg"
        headers = {"Referer": url}
        save_path = os.path.join(img_dir, fname)
        print(f"⬇️ دانلود عکس: {fname} ...")
        if download_file(img_url, save_path, headers=headers):
            size_kb = os.path.getsize(save_path) / 1024
            if size_kb >= MIN_IMAGE_SIZE_KB:
                print(f"   ✅ ذخیره شد ({size_kb:.1f} KB)")
                img_downloaded += 1
            else:
                print(f"   🗑️ حذف (حجم {size_kb:.1f} KB < {MIN_IMAGE_SIZE_KB} KB)")
                os.remove(save_path)
        else:
            print(f"   ❌ دانلود ناموفق")
            # شاید نسخه originals وجود نداشته باشد -> تلاش با 736x
            if "/originals/" in img_url:
                fallback_url = img_url.replace("/originals/", "/736x/")
                print(f"   🔄 تلاش با 736x: {fallback_url[:100]}")
                if download_file(fallback_url, save_path, headers=headers):
                    size_kb = os.path.getsize(save_path) / 1024
                    if size_kb >= MIN_IMAGE_SIZE_KB:
                        print(f"   ✅ ذخیره شد (fallback, {size_kb:.1f} KB)")
                        img_downloaded += 1

    # --- دانلود ویدئوها (بدون تغییر) ---
    vid_downloaded = 0
    if video_urls:
        for vurl in video_urls:
            ext = "mp4"
            for e in ("mp4", "webm", "mkv", "mov", "avi", "flv", "ts", "m3u8"):
                if vurl.lower().endswith(e):
                    ext = e
                    break
            if ext == "m3u8":
                outtmpl = os.path.join(vid_dir, "%(title)s.%(ext)s")
                subprocess.run(["yt-dlp", "-f", "best", "-o", outtmpl, vurl], capture_output=True, timeout=120)
                for f in os.listdir(vid_dir):
                    if f.endswith((".mp4", ".webm")) and os.path.getsize(os.path.join(vid_dir, f)) > 100*1024:
                        vid_downloaded += 1
            else:
                fname = sanitize_filename(vurl, ext)
                if download_file(vurl, os.path.join(vid_dir, fname), headers={"Referer": url}):
                    if os.path.getsize(os.path.join(vid_dir, fname)) > 100*1024:
                        vid_downloaded += 1
                    else:
                        os.remove(os.path.join(vid_dir, fname))
    else:
        print("🔍 رهگیری شبکه ۰ بود → yt-dlp")
        vid_downloaded = download_with_ytdlp(url, vid_dir, max_videos)

    report = f"✅ دانلود از {url} کامل شد.\n"
    report += f"🖼️ عکس‌های باکیفیت دانلود شده: {img_downloaded}/{len(images)}\n"
    report += f"🎥 فیلم‌های دانلود شده: {vid_downloaded} (حداکثر {max_videos})\n"
    with open(f"{output_dir}/report.txt", "w") as f:
        f.write(report)
    print(report)

if __name__ == "__main__":
    main()
