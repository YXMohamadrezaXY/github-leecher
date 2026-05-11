import os
import requests
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

def take_screenshot(url):
    os.makedirs("output", exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        try:
            page.goto(url, timeout=30000)
            page.screenshot(path="output/screenshot.png", full_page=True)
        except Exception as e:
            browser.close()
            raise e
        browser.close()

def main():
    query = os.environ.get("INPUT_QUERY", "").strip()
    os.makedirs("output", exist_ok=True)

    if query.startswith("http://") or query.startswith("https://"):
        # درخواست اسکرین‌شات
        try:
            take_screenshot(query)
            reply = "✅ اسکرین‌شات با موفقیت گرفته شد. فایل screenshot.png در خروجی."
        except Exception as e:
            reply = f"❌ خطا در گرفتن اسکرین‌شات: {e}"
    else:
        # درخواست جستجو
        reply = search_github(query)

    with open("output/reply.txt", "w", encoding="utf-8") as f:
        f.write(reply)

if __name__ == "__main__":
    main()
