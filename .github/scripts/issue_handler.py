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
    # اطمینان از وجود پوشه output
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
    return "output/screenshot.png"

def main():
    title = os.environ["ISSUE_TITLE"].strip()
    body = os.environ.get("ISSUE_BODY", "").strip()
    issue_number = int(os.environ["ISSUE_NUMBER"])
    repo_full = os.environ["REPO"]

    # --- تشخیص نوع درخواست ---
    if title.lower().startswith("search:"):
        # query رو از خود عنوان بعد از search: بردار، اگه خالی بود از بدنه
        query = title[7:].strip() or body
        if not query:
            reply = "❌ لطفاً عبارت جستجو را وارد کنید."
        else:
            reply = search_github(query)
    elif title.lower().startswith("screenshot:"):
        url = title[11:].strip() or body
        if not url.startswith("http"):
            reply = "❌ لینک معتبر نیست (باید با http شروع شود)."
        else:
            try:
                take_screenshot(url)
                reply = "✅ اسکرین‌شات با موفقیت گرفته شد و پیوست می‌شود."
            except Exception as e:
                reply = f"❌ خطا در گرفتن اسکرین‌شات: {e}"
    else:
        reply = (
            "⚠️ فرمت ناشناخته.\n"
            "لطفاً عنوان Issue را با یکی از موارد زیر شروع کنید:\n"
            "`search: عبارت جستجو`\n"
            "`screenshot: لینک صفحه`"
        )

    # --- نوشتن پاسخ در یک فایل موقت (یا مستقیم با gh) ---
    # به‌جای اینکه مستقیم با PyGithub کامنت بذاریم،
    # ریپلای رو به stdout چاپ می‌کنیم تا قدم بعدی ازش استفاده کنه.
    # اما بهتره مستقیماً با gh کامنت بذاریم. برای سادگی، ما اینجا فایل کامنت رو می‌سازیم.
    # توجه: چون GITHUB_TOKEN در environment موجود هست، می‌تونیم از gh استفاده کنیم.
    # برای اینکه کدمون ساده بمونه، خروجی رو در فایل مینویسیم و مرحله بعدی در workflow میذاره.
    with open("output/reply.txt", "w", encoding="utf-8") as f:
        f.write(reply)

if __name__ == "__main__":
    main()
