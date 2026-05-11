import os
import requests
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright
import time

def search_github(query):
    url = f"https://api.github.com/search/repositories?q={query}"
    headers = {"Accept": "application/vnd.github.v3+json"}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", [])[:5]
    except Exception as e:
        return f"❌ خطا در جستجو: {e}"

    if not items:
        return "🔍 نتیجه‌ای یافت نشد."

    result = "**نتایج جستجو:**\n"
    for item in items:
        result += f"- [{item['full_name']}]({item['html_url']}) ⭐ {item['stargazers_count']}\n"
    return result

def wait_for_media_to_load(page, timeout=5000):
    """منتظر می‌ماند تا عکس‌ها و ویدیوهای در حال بارگذاری کامل شوند."""
    print("منتظر بارگذاری عکس‌ها و ویدیوها...")
    try:
        page.wait_for_function("""
            () => {
                const images = Array.from(document.querySelectorAll('img[loading="lazy"], img:not([src]), img[data-src]'));
                const allImagesLoaded = images.every(img => img.complete && img.naturalWidth > 0);
                
                const videos = Array.from(document.querySelectorAll('video'));
                const allVideosReady = videos.every(video => video.readyState >= 2); // HAVE_CURRENT_DATA
                
                return allImagesLoaded && allVideosReady;
            }
        """, timeout=timeout)
        print("عکس‌ها و ویدیوها با موفقیت بارگذاری شدند.")
    except Exception as e:
        print(f"اخطار: زمان انتظار برای بارگذاری رسانه‌ها به پایان رسید: {e}")

def scroll_to_load_lazy_content(page):
    """کل صفحه را اسکرول می‌کند و برمی‌گردد تا محتوای lazy-loaded بارگذاری شود."""
    print("در حال اسکرول صفحه برای فعال‌سازی lazy loading...")
    try:
        scroll_height = page.evaluate("document.body.scrollHeight")
        current_position = 0
        step = 500  # هر بار ۵۰۰ پیکسل اسکرول کن

        while current_position < scroll_height:
            page.evaluate(f"window.scrollTo(0, {current_position})")
            time.sleep(0.2)  # کمی صبر کن تا محتوا شروع به بارگذاری کنه
            current_position += step
        
        # یک بار تا ته صفحه برو
        page.evaluate(f"window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(0.5)

        # برگرد به بالای صفحه برای گرفتن اسکرین‌شات کامل
        page.evaluate("window.scrollTo(0, 0)")
        time.sleep(0.3)
        print("اسکرول کامل شد.")
    except Exception as e:
        print(f"خطا در هنگام اسکرول: {e}")

def take_screenshot_and_extract_links(url, full_page=True):
    os.makedirs("output", exist_ok=True)
    links = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        try:
            print(f"در حال بارگذاری صفحه: {url}")
            page.goto(url, timeout=30000)
            
            # 1. صبر کن تا وضعیت شبکه به load برسه
            page.wait_for_load_state("load")
            
            # 2. اسکرول کن تا محتوای lazy فعال بشه
            scroll_to_load_lazy_content(page)
            
            # 3. صبر کن تا عکس‌ها و ویدیوها کامل بارگذاری بشن
            wait_for_media_to_load(page)
            
            print("در حال گرفتن اسکرین‌شات...")
            # 4. اسکرین‌شات با توجه به تنظیم full_page
            page.screenshot(path="output/screenshot.png", full_page=full_page)
            print("اسکرین‌شات گرفته شد.")

            # 5. استخراج لینک‌ها
            anchor_elements = page.query_selector_all("a[href]")
            for a in anchor_elements:
                href = a.get_attribute("href")
                if href:
                    absolute_url = urljoin(url, href)
                    links.append(absolute_url)

            # حذف تکراری‌ها
            seen = set()
            unique_links = []
            for link in links:
                if link not in seen:
                    seen.add(link)
                    unique_links.append(link)

            with open("output/links.txt", "w", encoding="utf-8") as f:
                f.write(f"All links found on: {url}\n")
                f.write("=" * 60 + "\n")
                for link in unique_links:
                    f.write(link + "\n")

        except Exception as e:
            browser.close()
            raise e
        browser.close()

def main():
    query = os.environ.get("INPUT_QUERY", "").strip()
    full_page_option = os.environ.get("INPUT_FULL_PAGE", "").strip()
    
    # تبدیل گزینه به True/False
    full_page = True  # پیش‌فرض کل صفحه
    if "نه" in full_page_option:
        full_page = False

    os.makedirs("output", exist_ok=True)

    if query.startswith("http://") or query.startswith("https://"):
        try:
            take_screenshot_and_extract_links(query, full_page)
            mode = "کل صفحه" if full_page else "نمای قابل مشاهده"
            reply = f"✅ اسکرین‌شات ({mode}) با موفقیت گرفته شد.\n📎 فایل `links.txt` شامل تمام لینک‌های صفحه نیز ایجاد شد."
        except Exception as e:
            reply = f"❌ خطا در گرفتن اسکرین‌شات: {e}"
    else:
        reply = search_github(query)

    with open("output/reply.txt", "w", encoding="utf-8") as f:
        f.write(reply)

if __name__ == "__main__":
    main()
