import os
import time
import requests
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright

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

def find_scrollable_container(page):
    """
    تشخیص می‌دهد که اسکرول اصلی صفحه روی کدام عنصر است.
    اگر اسکرول روی body باشد، None برمی‌گرداند.
    """
    # اسکرول‌المنت پیش‌فرض (معمولاً <html> یا body)
    scrolling_element = page.evaluate("document.scrollingElement.tagName.toLowerCase()")
    if scrolling_element in ["html", "body"]:
        return None  # اسکرول روی بدنه است

    # در غیر این صورت یک container داخلی اسکرول دارد (مثل div.app)
    # یک سلکتور ساده برای پیداکردن container اصلی که overflow-y داشته باشد
    container = page.evaluate("""() => {
        const all = document.querySelectorAll('*');
        for (const el of all) {
            const style = window.getComputedStyle(el);
            if ((style.overflowY === 'auto' || style.overflowY === 'scroll') && el.scrollHeight > el.clientHeight) {
                return el.tagName + (el.id ? '#' + el.id : '') + (el.className ? '.' + el.className.split(' ').join('.') : '');
            }
        }
        return null;
    }""")
    return container  # اگر پیدا کرد نام سلکتور رو برمی‌گردونه

def intelligent_scroll(page, container_selector=None):
    """
    اسکرول هوشمند: اگر container_selector داده شود، داخل آن اسکرول می‌کند.
    در غیر این صورت بدنه صفحه را اسکرول می‌کند.
    """
    if container_selector:
        print(f"تشخیص container اسکرول: {container_selector}")
        # منتظر بودن برای اینکه container در DOM باشد
        page.wait_for_selector(container_selector, timeout=5000)
        scroll_element = page.locator(container_selector)
    else:
        print("اسکرول روی بدنه یا html")
        scroll_element = None

    print("شروع اسکرول هوشمند...")
    if scroll_element:
        # اسکرول داخل container
        last_scroll_top = page.evaluate(f"document.querySelector('{container_selector}').scrollTop")
        unchanged_count = 0
        while True:
            page.evaluate(f"document.querySelector('{container_selector}').scrollTo(0, document.querySelector('{container_selector}').scrollHeight)")
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except:
                pass
            time.sleep(0.5)
            new_scroll_top = page.evaluate(f"document.querySelector('{container_selector}').scrollTop")
            if new_scroll_top == last_scroll_top:
                unchanged_count += 1
                if unchanged_count >= 3:
                    break
            else:
                unchanged_count = 0
                last_scroll_top = new_scroll_top
    else:
        # اسکرول بدنه
        last_height = page.evaluate("document.body.scrollHeight")
        unchanged_count = 0
        while True:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except:
                pass
            time.sleep(0.5)
            new_height = page.evaluate("document.body.scrollHeight")
            if new_height == last_height:
                unchanged_count += 1
                if unchanged_count >= 3:
                    break
            else:
                unchanged_count = 0
                last_height = new_height

    # برگرد به بالای container یا صفحه
    if scroll_element:
        page.evaluate(f"document.querySelector('{container_selector}').scrollTo(0, 0)")
    else:
        page.evaluate("window.scrollTo(0, 0)")
    time.sleep(0.3)

def expand_container_for_full_page_screenshot(page, container_selector):
    """
    استایل container را طوری تغییر می‌دهد که کل محتوایش نمایان شود و
    body نیز کل آن را در بر بگیرد تا اسکرین‌شات full_page صحیح کار کند.
    """
    if not container_selector:
        return
    print(f"گسترش container برای اسکرین‌شات کامل...")
    # ذخیره استایل‌های قبلی (اختیاری برای بازگردانی)
    page.evaluate(f"""
        const el = document.querySelector('{container_selector}');
        if (el) {{
            el.style.overflow = 'visible';
            el.style.height = 'auto';
            el.style.maxHeight = 'none';
        }}
    """)
    # کمی صبر کن تا ری‌فلوی صفحه انجام شود
    time.sleep(0.5)

def wait_for_all_media(page):
    print("منتظر بارگذاری کامل عکس‌ها و ویدیوها...")
    try:
        page.wait_for_function("""
            () => {
                const imgs = Array.from(document.images);
                const allImgs = imgs.every(img => img.complete && img.naturalWidth > 0);
                const videos = Array.from(document.querySelectorAll('video'));
                const allVideos = videos.every(v => v.readyState >= 2);
                return allImgs && allVideos;
            }
        """, timeout=15000)
        print("عکس‌ها و ویدیوها کامل بارگذاری شدند.")
    except Exception as e:
        print(f"⚠️ زمان انتظار برای رسانه‌ها تمام شد: {e}")

def take_screenshot_and_extract_links(url, full_page=True):
    os.makedirs("output", exist_ok=True)
    links = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        try:
            print(f"بارگذاری صفحه: {url}")
            page.goto(url, timeout=30000)
            page.wait_for_load_state("load")

            # ۱. تشخیص container اسکرول (اگر وجود داشته باشد)
            container = find_scrollable_container(page)

            # ۲. اسکرول هوشمند در container یا بدنه
            intelligent_scroll(page, container)

            # ۳. منتظر ماندن برای لود عکس‌ها و ویدیوها
            wait_for_all_media(page)

            # ۴. اگر container بود، گسترشش بده تا body کل محتوا رو ببینه
            if container:
                expand_container_for_full_page_screenshot(page, container)

            # ۵. اسکرین‌شات (full_page=True با توجه به انتخاب)
            print("گرفتن اسکرین‌شات...")
            page.screenshot(path="output/screenshot.png", full_page=full_page)
            print("اسکرین‌شات ذخیره شد.")

            # ۶. استخراج لینک‌ها
            anchors = page.query_selector_all("a[href]")
            for a in anchors:
                href = a.get_attribute("href")
                if href:
                    links.append(urljoin(url, href))

            unique_links = list(dict.fromkeys(links))
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
    full_page = False if "نه" in full_page_option else True

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
