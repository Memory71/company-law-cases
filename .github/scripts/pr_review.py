"""
每天由 GitHub Actions 排程執行：
1. 抓取 repo 目前所有開啟中的 Pull Request，逐一做「初步審查意見」（合併前參考用）
2. 抓取所有 PR（不限狀態），依評分規則產生「學生建議分數總表」，依學號排序
3. 遮蔽內容中出現的學生姓名（只留頭尾兩字，中間用○取代），保護隱私
4. 把上述內容彙整成一則新的 GitHub Issue（同一天重複觸發會更新同一則，不重複建立）

注意：這是「助教式初步審查／建議分數」，不是正式評分。最終分數與是否合併，仍由老師人工決定。
"""

import os
import re
import json
import datetime
import requests

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
REPO = os.environ["GITHUB_REPOSITORY"]  # e.g. "mjib007/company-law-cases"

GH_API = "https://api.github.com"
GH_HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
}

MAX_DIFF_CHARS_PER_PR = 6000  # 避免單一 PR 內容過長，超出的部分截斷

SELF_VERIFICATION_RULES = """\
審查時請依照以下規則檢查，並在意見中具體指出哪裡符合、哪裡有疑慮（不要只給籠統評語）：

1. 條號、法規名稱、修法內容、新聞事件細節、日期、數字，是否看起來像是有依據，而非憑印象斷言。
2. 若引用「§X至§Y」這種範圍條號，是否每一條都個別列出，而非只寫頭尾兩條。
3. 若標註了法規連結，pcode 格式是否合理（例如公司法 J0080001、證券交易法 G0400001，不是 G0400021）。
4. 是否針對補充或修正的內容，在段落後面加上「（姓名，學號）」的具名格式。
5. 內容的論述是否有明顯的邏輯跳躍或過度簡化。
6. 這是初步審查意見，不是最終分數，請避免使用「不通過」「打回票」這類語氣，改用「建議老師確認」「值得留意」等中性描述。
"""

RUBRIC = [
    ("具名格式", 10, "是否在補充內容後正確標註「（姓名，學號）」"),
    ("論述完整度與邏輯", 30, "論述是否完整、有無明顯邏輯跳躍或過度簡化"),
    ("法規依據", 30, "是否引用具體條號，條號範圍是否逐條列出，pcode是否合理"),
    ("查證與來源", 20, "事件細節、日期、數字是否有依據，是否可能是憑印象斷言"),
    ("格式規範遵守", 10, "是否遵照既有區塊格式填寫，未破壞其他區塊內容或樣式"),
]

NAME_PATTERN = re.compile(r"（([^\uFF0C,，]{2,6})[，,]\s*([0-9○\*]{4,12})）")


def mask_name(name: str) -> str:
    """只留頭尾兩字，中間以○取代，保護學生隱私。若已是遮蔽格式則不重複處理。"""
    if "○" in name:
        return name
    if len(name) <= 2:
        return name
    return name[0] + "○" * (len(name) - 2) + name[-1]


def mask_id(sid: str) -> str:
    """只留末三碼，其餘以*取代，保護學生隱私。若已是遮蔽格式則不重複處理。"""
    if "○" in sid or "*" in sid:
        return sid
    if len(sid) <= 3:
        return sid
    return "*" * (len(sid) - 3) + sid[-3:]


def mask_names_in_text(text: str) -> str:
    def _replace(m):
        name, sid = m.group(1), m.group(2)
        return f"（{mask_name(name)}，{mask_id(sid)}）"
    return NAME_PATTERN.sub(_replace, text)


def list_open_prs():
    resp = requests.get(
        f"{GH_API}/repos/{REPO}/pulls",
        headers=GH_HEADERS,
        params={"state": "open", "per_page": 100},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def list_all_prs():
    resp = requests.get(
        f"{GH_API}/repos/{REPO}/pulls",
        headers=GH_HEADERS,
        params={"state": "all", "per_page": 100},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def extract_students(text: str):
    """從文字中找出所有「（姓名，學號）」，回傳去重後的 (姓名, 學號) list（未遮蔽版本）。"""
    seen = []
    for name, sid in NAME_PATTERN.findall(text):
        pair = (name, sid)
        if pair not in seen:
            seen.append(pair)
    return seen


def get_pr_files(pr_number: int):
    resp = requests.get(
        f"{GH_API}/repos/{REPO}/pulls/{pr_number}/files",
        headers=GH_HEADERS,
        params={"per_page": 100},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def build_diff_summary(files):
    parts = []
    total = 0
    for f in files:
        patch = f.get("patch")
        if not patch:
            continue
        chunk = f"### 檔案：{f['filename']}\n```diff\n{patch}\n```\n"
        if total + len(chunk) > MAX_DIFF_CHARS_PER_PR:
            parts.append("（後續變更內容過長，已截斷，請至 PR 頁面查看完整內容）")
            break
        parts.append(chunk)
        total += len(chunk)
    return "\n".join(parts) if parts else "（此 PR 沒有可讀取的文字變更內容）"


def call_claude_review(pr_title: str, pr_body: str, diff_summary: str) -> str:
    if not ANTHROPIC_API_KEY:
        return "⚠️ 未設定 ANTHROPIC_API_KEY，略過 AI 審查。"

    prompt = f"""你是公司法教學助教，負責初步審查學生提交的 Pull Request 內容。

{SELF_VERIFICATION_RULES}

PR 標題：{pr_title}
PR 說明：{pr_body or "（無）"}

變更內容：
{diff_summary}

請用繁體中文、條列式，簡短具體地寫出初步審查意見（3-6點即可），不需要重複貼出原文內容。"""

    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-sonnet-5",
            "max_tokens": 1000,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=120,
    )
    if resp.status_code != 200:
        try:
            err_detail = resp.json().get("error", {}).get("message", resp.text[:300])
        except Exception:
            err_detail = resp.text[:300]
        print(f"Claude API 呼叫失敗：HTTP {resp.status_code} - {err_detail}")
        return f"⚠️ 呼叫 Claude API 失敗（HTTP {resp.status_code}）：{err_detail}"

    data = resp.json()
    texts = [b["text"] for b in data.get("content", []) if b.get("type") == "text"]
    return "\n".join(texts) if texts else "⚠️ Claude 未回傳文字內容。"


def call_claude_score(pr_title: str, diff_summary: str) -> dict:
    """呼叫 Claude 依 RUBRIC 給建議分數，回傳 dict：{breakdown: {...}, total: int, reason: str}"""
    if not ANTHROPIC_API_KEY:
        return {"error": "未設定 ANTHROPIC_API_KEY"}

    rubric_desc = "\n".join(
        f"- {name}（滿分{max_score}）：{desc}" for name, max_score, desc in RUBRIC
    )

    prompt = f"""你是公司法教學助教，依照以下評分規則，為學生提交的 Pull Request 內容打「建議分數」。

評分規則：
{rubric_desc}

PR 標題：{pr_title}

變更內容：
{diff_summary}

請只回傳一個 JSON 物件，不要有任何其他文字、不要用 markdown code fence 包起來，格式如下：
{{"breakdown": {{"具名格式": 分數, "論述完整度與邏輯": 分數, "法規依據": 分數, "查證與來源": 分數, "格式規範遵守": 分數}}, "total": 總分, "reason": "一段簡短理由，說明扣分或加分關鍵"}}"""

    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-sonnet-5",
            "max_tokens": 2000,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=120,
    )
    if resp.status_code != 200:
        try:
            err_detail = resp.json().get("error", {}).get("message", resp.text[:300])
        except Exception:
            err_detail = resp.text[:300]
        return {"error": f"HTTP {resp.status_code} - {err_detail}"}

    data = resp.json()
    texts = [b["text"] for b in data.get("content", []) if b.get("type") == "text"]
    raw = "\n".join(texts).strip()
    raw = re.sub(r"^```(json)?|```$", "", raw, flags=re.MULTILINE).strip()

    try:
        parsed = json.loads(raw)
        return parsed
    except Exception:
        return {"error": "無法解析評分結果", "raw": raw[:500], "stop_reason": data.get("stop_reason")}


def build_score_table(prs) -> str:
    """對所有 PR 產生依學號排序的建議分數表。"""
    rows = []  # (學號, 姓名遮蔽, breakdown, total, 狀態, 連結, error)

    for pr in prs:
        number = pr["number"]
        title = pr["title"]
        html_url = pr["html_url"]

        if pr.get("merged_at"):
            status = "Merged"
        elif pr["state"] == "closed":
            status = "Closed（未合併）"
        else:
            status = "Open"

        files = get_pr_files(number)
        diff_summary_raw = build_diff_summary(files)
        students = extract_students(diff_summary_raw) or extract_students(pr.get("body") or "")

        diff_summary_masked = mask_names_in_text(diff_summary_raw)
        score = call_claude_score(title, diff_summary_masked)

        if not students:
            rows.append({
                "sid": "（未標註學號）", "sid_display": "（未標註學號）", "name": "-", "score": score,
                "status": status, "url": html_url, "pr": number,
            })
        else:
            for name, sid in students:
                rows.append({
                    "sid": sid, "sid_display": mask_id(sid), "name": mask_name(name), "score": score,
                    "status": status, "url": html_url, "pr": number,
                })

    rows.sort(key=lambda r: r["sid"])

    header = "| 學號 | 姓名 | " + " | ".join(n for n, _, _ in RUBRIC) + " | 總分 | PR狀態 | 連結 |\n"
    header += "|---|---|" + "---|" * len(RUBRIC) + "---|---|---|\n"

    lines = [header]
    for r in rows:
        score = r["score"]
        if "error" in score:
            line = f"| {r['sid_display']} | {r['name']} | " + "無法評分 | " * len(RUBRIC) + f"- | {r['status']} | #{r['pr']} |\n"
            lines.append(line)
            lines.append(f"> ⚠️ PR #{r['pr']} 評分失敗：{score['error']}\n")
            if "raw" in score:
                lines.append(f"> 原始回傳（除錯用）：`{score['raw']}`（stop_reason: {score.get('stop_reason')}）\n")
            continue
        breakdown = score.get("breakdown", {})
        cells = " | ".join(str(breakdown.get(n, "-")) for n, _, _ in RUBRIC)
        total = score.get("total", "-")
        line = f"| {r['sid_display']} | {r['name']} | {cells} | {total} | {r['status']} | #{r['pr']} |\n"
        lines.append(line)
        reason = score.get("reason")
        if reason:
            lines.append(f"> {reason}\n")

    return "".join(lines)


def find_existing_report_issue(title: str):
    resp = requests.get(
        f"{GH_API}/repos/{REPO}/issues",
        headers=GH_HEADERS,
        params={"state": "open", "labels": "ai-review", "per_page": 30},
        timeout=30,
    )
    resp.raise_for_status()
    for issue in resp.json():
        if issue["title"] == title:
            return issue
    return None


def main():
    open_prs = list_open_prs()
    all_prs = list_all_prs()

    if not open_prs and not all_prs:
        print("目前沒有任何 PR，不建立審查報告。")
        return

    today = datetime.date.today().isoformat()
    sections = []

    for pr in open_prs:
        number = pr["number"]
        title = pr["title"]
        author = pr["user"]["login"]
        html_url = pr["html_url"]
        body = pr.get("body") or ""

        files = get_pr_files(number)
        diff_summary = build_diff_summary(files)
        diff_summary = mask_names_in_text(diff_summary)
        body_masked = mask_names_in_text(body)

        review = call_claude_review(title, body_masked, diff_summary)
        review = mask_names_in_text(review)

        sections.append(
            f"## PR #{number}：{title}\n"
            f"- GitHub 帳號：{author}\n"
            f"- 連結：{html_url}\n\n"
            f"**AI 初步審查意見（僅供參考，最終評分由老師決定）：**\n\n{review}\n"
        )

    review_part = (
        f"## 一、開啟中 PR 的初步審查意見（合併前參考用）\n\n"
        + (
            "\n---\n\n".join(sections) if sections
            else "目前沒有開啟中的 PR。\n"
        )
    )

    score_table = build_score_table(all_prs) if all_prs else "目前沒有任何 PR，無法產生分數表。\n"
    score_part = (
        f"## 二、學生建議分數總表（依學號排序，所有 PR 皆列入，不限是否已合併）\n\n"
        f"以下分數為 AI 依評分規則產生的**建議分數**，僅供參考，最終分數請老師人工複核後決定。\n\n"
        + score_table
    )

    report_body = (
        f"# PR 每日審查報告 - {today}\n\n"
        f"本報告由 GitHub Actions 排程自動產生。學生姓名已遮蔽（僅留頭尾兩字）。"
        f"以下內容**不代表最終分數或是否合併之決定**，請老師人工複核。\n\n---\n\n"
        + review_part + "\n\n---\n\n" + score_part
    )

    title = f"PR 每日審查報告 - {today}"
    existing = find_existing_report_issue(title)

    if existing:
        resp = requests.patch(
            f"{GH_API}/repos/{REPO}/issues/{existing['number']}",
            headers=GH_HEADERS,
            json={"body": report_body},
            timeout=30,
        )
        resp.raise_for_status()
        print(f"已更新既有審查報告 Issue：{resp.json()['html_url']}")
    else:
        resp = requests.post(
            f"{GH_API}/repos/{REPO}/issues",
            headers=GH_HEADERS,
            json={
                "title": title,
                "body": report_body,
                "labels": ["ai-review"],
            },
            timeout=30,
        )
        resp.raise_for_status()
        print(f"已建立審查報告 Issue：{resp.json()['html_url']}")


if __name__ == "__main__":
    main()
