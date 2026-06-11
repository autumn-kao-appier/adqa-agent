---
name: brew
description: 蒸餾 skill — 從 Slack channel 和 Jira 萃取已結案的調查案例，轉成 schema.json 格式，寫入 knowledge/cases.jsonl。
---

# brew — 蒸餾 Skill

每天 09:00 由 scheduler 觸發，或手動呼叫 `/brew`。

**核心原則：以 Slack thread 為主要知識來源，Jira 為補充參考。**
如果某個欄位從 thread 內容找不到，必須比對 Jira ticket、上下文、相關討論，盡力做出總結。不要因為找不到完整資訊就放棄——只有確實無法推斷才填 null。

---

## 前置條件

讀取 `knowledge/index.json`，取得：
- `last_distilled_at`：上次蒸餾時間（ISO8601 UTC）
- `processed`：已處理的 Jira ticket key 與 Slack thread_ts 及其最後處理時間

---

## Step 1：掃描 Slack channel

依 `config/channels.yaml` 的 channel 清單，用 `slack_read_channel`（**response_format=detailed**，limit=50）逐頁讀取，直到訊息時間早於 `last_distilled_at`。

`response_format=detailed` 是必要的，才能取得每則訊息的精確 `message_ts`（用於後續 `slack_read_thread`）。

記錄每則訊息的 `message_ts`、內容、thread reply 數。

---

## Step 2：找有深度的討論 thread

從 Step 1 的訊息中識別「值得蒸餾的討論」：
- 有 ADQA-XXXX 票號的訊息
- 有 3 個以上 reply 的 thread
- 包含技術問題關鍵字（CTR / bid / attribution / endcard / SSP / root cause / 問題 / 原因）

對每個符合條件的訊息，用 Step 1 取得的精確 `message_ts` 讀完整 thread：
```
slack_read_thread(channel_id, message_ts, response_format=concise)
```

收集訊息中出現的所有 ADQA-XXXX 票號。Thread 內容是蒸餾的**主要來源**。

---

## Step 3：查 Jira，作為補充參考

對每個票號呼叫：
```
mcp__claude_ai_Atlassian_Rovo__getJiraIssue(
  issueIdOrKey='ADQA-XXXX',
  fields=["summary","description","comment","status","resolution","updated",
          "assignee","reporter","priority","labels","components","issuelinks",
          "attachment","subtasks","fixVersions","sprint","story_points"]
)
```

取得欄位說明：

| 欄位 | 說明 |
|---|---|
| `comment` | 最新 5 則；總數 > 10 則標注「共 N 則，顯示最新 5 則」|
| `subtasks` | 子任務清單（key + summary + status）|
| `issuelinks` | 關聯 issue（類型 + key + summary）|
| `fixVersions` / `sprint` / `story_points` | 版本 / Sprint / 點數（有值才顯示）|
| `resolution` / `updated` | 結案狀態 / 最後更新時間（brew 蒸餾邏輯用）|

**只保留 status = Done / Resolved / Closed 的票。**

比對 `index.json.processed.jira`：
- 票號不存在 → 新案件，處理
- 票號存在但 `updated > last_processed_at` → 有更新，重新處理（upsert）
- 票號存在且無更新 → 跳過

### Jira 內容過大 Fallback Chain

當 `getJiraIssue` 回傳「result exceeds maximum allowed tokens，已存至檔案」時，依序走：

**Fallback 1 — 從暫存檔抽取留言文字**

```python
import json

def extract_text(node):
    texts = []
    if isinstance(node, dict):
        if node.get('type') == 'text':
            texts.append(node.get('text', ''))
        for v in node.values():
            texts.extend(extract_text(v))
    elif isinstance(node, list):
        for item in node:
            texts.extend(extract_text(item))
    return texts

with open('{暫存檔路徑}') as f:
    data = json.load(f)

comments = data['issues']['nodes'][0]['fields']['comment']['comments']
for c in comments:
    author = c['author']['displayName']
    date = c['created'][:10]
    texts = extract_text(c['body'])
    content = ' '.join(t for t in texts if t.strip())
    if content.strip():
        print(f'=== {author} ({date}) ===')
        print(content[:500])
```

取得留言後尋找 root cause 關鍵字：`root cause`、`結論`、`confirmed`、`因為`、`原因`、`resolved`、`fix`。

**Fallback 2 — 搜尋 Slack**

若 Fallback 1 仍找不到 root cause：
```
mcp__claude_ai_Slack__slack_search_public_and_private(query='ADQA-XXXX')
```
找到相關 thread 後用 `slack_read_thread` 讀完整討論。

**Fallback 3 — 跳過**

Fallback 1 + 2 都找不到 root cause → 跳過，不寫進 cases.jsonl。不填猜測內容。

---

## Step 3.1：識別 Test Ticket

取得 Jira 資料後，先判斷是否為 test ticket：

**識別條件（符合任一）：**
- summary 含關鍵字：`Validating`、`實刷`、`驗證`、`QA test`、`QA Test`
- issuelinks 中有 `relates to` 或 `clones` 指向另一張 ADQA 調查票

若符合 → 進入下方 **Test Case 蒸餾路徑**，跳過 Steps 4–9 的調查票流程。
若不符合 → 繼續走原有流程（Steps 4–9）。

---

## Test Case 蒸餾路徑

### TC-1：讀 Jira 測試結果

從 Jira description 和 comments 萃取：
- **測試結論**：整體 pass / fail / partial
- **逐 bundle 結果**：Pass / Skip / Fail + 原因
- **bidobjid**（如有）

展開 Jira description 和每則 comment 中的所有外部連結（同 Step 4 規則）：
- screen recording、Google Drive 資料夾 → Google Drive MCP 讀取
- 其他連結依 Step 4 各類型規則處理

讀 Jira 附件（同 Step 4.1 規則）：圖片走 vision、PDF/Excel 截斷至 600 字。

### TC-2：搜尋對應 Slack 討論

用票號搜尋 Slack，補充測試背景與後續決策：
```
mcp__claude_ai_Slack__slack_search_public_and_private(
  query='ADQA-XXXX',
  sort='timestamp',
  sort_dir='desc',
  limit=5
)
```
找到 thread 後用 `slack_read_thread` 讀完整討論。

對讀到的每則訊息，展開所有外部連結（同 Step 5「Slack 訊息內的外部連結」規則）：
- Slack 格式：`<https://...>` 或 `<https://...|顯示文字>` 與裸 URL 全部掃描
- 去重後依 Step 4 各類型規則展開
- 訊息附件用 `slack_read_file` 取得，處理規則同 Step 4.1

### TC-3：Schema 填法

Test case 的欄位填法與調查票不同：

| 欄位 | 填法 |
|---|---|
| `symptom.signature` | `{SSP} {region/os} {廣告類型} 實刷驗證` |
| `symptom.funnel_stage` | 推斷測試的 funnel 階段（如驗 CTR → `["Click"]`，驗 delivery → `["Win-Show"]`）|
| `status` | 無問題 → `by-design`；發現問題 → `resolved`（指向 related_cases 的修復票）|
| `root_cause.summary` | 測試結論一句話（如「Pangle JP 無 auto-click，行為正常」）|
| `root_cause.confidence` | 所有指定 bundle 測完 → `confirmed`；部分 Skip → `likely` |
| `root_cause.category` | 依測試內容填（通常 `upstream-ssp`）|
| `resolution.fix` | `null`（`by-design` 無修法）|
| `resolution.note` | 測試結果摘要（幾個 pass / skip / fail）|
| `resolution.verified_by` | bundle 逐條結果（Pass: ..., Skip: ..., Fail: ...）|
| `related_cases` | 對應的主調查票（`issuelinks` 中的 ADQA 票號）|
| `volatile.specific_values` | bundle ID、bidobjid、recording URL |
| `volatile.ticket_ids` | 本票號 + related_cases |
| `volatile.dates` | 測試執行日期 |

**必填**（缺少 → 跳過）：
- `symptom.signature`
- `root_cause.summary`
- `root_cause.confidence`
- `status`
- `provenance.thread_refs`（至少 Jira URL）
- `provenance.as_of`

### TC-4：生成 pattern_id

同 Step 8，`source_id` 用 Jira ticket key。

`domain` 取 SSP 名稱（如 `pangle-jp-ios`）。

### TC-5：Upsert 到 cases.jsonl

同 Step 10 Atomic write 規則。

---

## Step 3.2：識別 Jira-Only 票

Test ticket 判斷為否後，檢查是否為「Jira 有完整記錄但 Slack 無討論」的票：

**識別條件（兩者都要）：**
1. Jira description 或 comments 包含下列任一結構性內容：
   - 明確的 root cause 關鍵字：`root cause`、`結論`、`原因`、`confirmed`、`因為`、`fix`、`resolved`
   - description 超過 200 字，且有背景說明段落
2. Slack 搜尋票號無實質討論：
   ```
   mcp__claude_ai_Slack__slack_search_public_and_private(query='ADQA-XXXX', limit=3)
   ```
   - 結果為空，或只有一則貼票號的通知訊息（無 replies）

若符合 → 進入下方 **Jira-Only 蒸餾路徑**。
若不符合 → 繼續走原有流程（Steps 4–9，以 Slack thread 為主）。

---

## Jira-Only 蒸餾路徑

適用：Jira 有完整前因後果，但 Slack 沒有對應討論。

### JO-1：深讀 Jira 內容

以 Jira description + 所有 comments 作為唯一知識來源：
- description：背景、症狀、影響範圍
- comments：調查過程、root cause 確認、resolution、驗證方式
- 展開所有外部連結（同 Step 4 規則）
- 讀附件（同 Step 4.1 規則）

### JO-2：Confluence 交叉驗證

同 Step 6，搜尋相關 Confluence 頁面確認行為基準。

### JO-3：Schema 填法

所有欄位從 Jira 萃取，填法與調查票相同（Step 9），但：

| 欄位 | 填法 |
|---|---|
| `provenance.source` | `"jira"` |
| `provenance.thread_refs` | 只有 Jira URL，無 Slack URL |
| `notes` | 標注 `"Jira-only：無對應 Slack 討論"` |

信心校準：
- description + comments 都有完整記錄 → `confidence: "confirmed"`
- 只有 description 有說明，comments 無結論 → `confidence: "likely"`
- 只能推斷，沒有明確結論關鍵字 → `confidence: "unverified"`

**若 Jira 內容不足以推斷 root_cause** → 不走此路徑，改走 Fallback Chain（Step 3 原有邏輯）。

### JO-4：生成 pattern_id 與 Upsert

同 Step 8 與 Step 10。

---

## Step 4：展開 Jira 內所有外部連結

對 Jira **description** 和每則 **comment** 中的所有 `https://` 連結，依類型處理：

### Google Sheet / Doc / Slides

URL 特徵：`docs.google.com/spreadsheets/d/{FILE_ID}`、`/document/d/{FILE_ID}`、`/presentation/d/{FILE_ID}`

從 URL 提取 FILE_ID（`/d/` 和下一個 `/` 之間的字串）。

用 `mcp__claude_ai_Google_Drive__read_file_content(file_id='{FILE_ID}')`；截斷至 800 字。

**重要：Google Sheet / Doc / Slides 不能用 WebFetch，必須走 Google Drive MCP。**

| 狀況 | 標記 |
|---|---|
| 未共享此帳號 | `[auth_required：{url}]` |
| 已刪除或無效 | `[link_dead：{url}]` |

### Confluence 頁面

URL 特徵：`atlassian.net/wiki/`

從 URL 擷取 page ID（`.../pages/123456789/...` → `123456789`）。

優先用 `mcp__claude_ai_Atlassian_Rovo__getConfluencePage(pageId='123456789')`；
無法取得 page ID 時改用 `mcp__claude_ai_Atlassian_Rovo__fetch(url='{原始 URL}')`。

取得：標題、space name、正文純文字（截斷至 800 字）、author、last_updated、labels。

頁面正文 < 100 字時標注 `[索引頁：正文極短，可能為目錄頁]`。

取頁尾留言：`mcp__claude_ai_Atlassian_Rovo__getConfluencePageFooterComments`（最新 3 則）。
取子頁面清單：`mcp__claude_ai_Atlassian_Rovo__getConfluencePageDescendants`（只取一層標題）。

頁面附件與正文內外部連結，處理規則同 Step 4.1 附件規則與各連結類型規則。

### GitHub

URL 特徵：`github.com/`

| URL 型態 | 處理方式 |
|---|---|
| repo 首頁（`/owner/repo`）| WebFetch 取 README |
| 特定檔案（`/blob/branch/path`）| 轉成 raw URL 後 WebFetch |
| Issue / PR | WebFetch 取標題 + 描述 |
| 私有 repo（403）| `[auth_required：{url}]` |

raw URL 轉換：`github.com/owner/repo/blob/branch/path` → `raw.githubusercontent.com/owner/repo/branch/path`

截斷至 600 字。

### YouTube

URL 特徵：`youtube.com` 或 `youtu.be`

用 oEmbed 取標題 + 頻道：
```
https://www.youtube.com/oembed?url={encoded_url}&format=json
```
輸出：`[YouTube] {title} — {author_name}`

### Google Meet / Google Forms

- **Meet**（`meet.google.com`）：標記 `[Google Meet 連結 — 無法取得錄影或會議內容]`
- **Forms**（`forms.gle` 或 `docs.google.com/forms`）：WebFetch 嘗試取表單標題；失敗則標記 `[Google Forms：{url}]`

### Slack Thread（巢狀）

URL 特徵：`slack.com/archives/`

thread_ts 轉換：URL 末段 `p1778656424797079` → `1778656424.797079`（倒數第六位插入 `.`）

用 `mcp__claude_ai_Slack__slack_read_thread` 取內容，**只展開一層**（不遞迴）；輸出訊息條數 + 摘要。

### 其他 `https://` 連結

URL 指向圖片（副檔名為 `.png`、`.jpg`、`.jpeg`、`.gif`、`.webp` 之一）時，改用 `Read` tool 載入並以 vision 分析，規則同 Step 4.1「圖片」行。

其餘 `https://` 連結用 `WebFetch` 取純文字；截斷至 600 字。

| 狀況 | 標記 |
|---|---|
| 正常取得 | 截斷純文字 |
| JS bundle / SPA | `[content_unreadable：{url}]` |
| Cloudflare 等封鎖（403）| `[fetch_blocked：{url}]` |
| 需要登入（401）| `[auth_required：{url}]` |
| 頁面不存在（404）| `[link_dead：{url}]` |
| 其他錯誤 | `[fetch_failed：{url}]` |

JS bundle 判斷信號（出現任一 → `content_unreadable`）：
`window.WIZ_global_data`、`__NEXT_DATA__`、`webpackChunk`、`__webpack_require__`、`window.__INITIAL_STATE__`

---

## Step 4.1：讀 Jira 附件

若 Jira ticket 有 `fields.attachment`，逐一用 `mcp__claude_ai_Atlassian_Rovo__fetch` 取得，依 mimeType 處理：

| 類型 | 處理方式 |
|---|---|
| 圖片（`image/*`）| 用 `Read` tool 載入後以 vision 分析：① 描述畫面內容與版面，② OCR 所有可見文字（逐字保留）；一般上限 200 字。**圖片含數據**（表格、圖表、數值、指標）時不受字數限制，所有數字與欄位須完整保留。失敗時標記 `[圖片附件：{filename}（vision 失敗：{原因}）]`，原因填「格式不支援」、「檔案過大」或「無法取得」 |
| PDF（文字版）| 擷取純文字；截斷至 600 字 |
| PDF（掃描版）| 標記 `[掃描版 PDF：{filename}]` |
| Excel / Word / PPT | 擷取純文字；截斷至 600 字 |
| 程式碼 snippet / 文字 / CSV / JSON / log | 直接讀取；截斷至 600 字 |
| Jupyter Notebook `.ipynb` | cell + output 一起萃取；截斷至 600 字 |
| 影片 / 壓縮檔 | `[無法萃取：{filename}（{mimeType}）]` |

---

## Step 4.2：提取 Jira issuelinks（用於 related_cases）

讀取 Jira 的 `issuelinks` 欄位，收集有明確連結的相關票號。
只收錄 Jira 上明確設定的 issuelinks，不推斷相關性。

**儲存格式：** `related_cases` 一律存 `{key, url}` object，不存純字串：
```json
"related_cases": [
  {"key": "ADQA-1277", "url": "https://appier.atlassian.net/browse/ADQA-1277"}
]
```
Jira 以外的 ticket（BT-XXXX、CR-XXXX 等）同樣格式，URL 一律用 `https://appier.atlassian.net/browse/{KEY}`。

---

## Step 5：讀 Slack thread

對結案票，在 Step 1 掃描到的訊息中找對應 thread（用 `detailed` format 取得的精確 `message_ts`）。

用 `slack_read_thread(channel_id, message_ts, response_format=concise)` 讀完整討論。

### Slack 訊息附件

若 thread 訊息 `files` 欄位有附件，用 `mcp__claude_ai_Slack__slack_read_file` 取得，處理規則同 Step 4.1 附件處理規則。

### Slack 訊息內的外部連結

對**每則訊息**（含 replies）掃描以下格式，去重後依 Step 4 各類型規則展開：
- Slack 格式：`<https://...>` 或 `<https://...|顯示文字>`
- 裸 URL：`https://...`（遇到空白或 `>` 為止）

**例外：** 已在 Step 3 處理過的 Jira ticket URL 跳過，避免重複讀取。

---

## Step 6：查 Confluence

根據案件的 domain / SSP / 問題類型，搜尋相關 Confluence 頁面：
```
mcp__claude_ai_Atlassian_Rovo__search(query='<關鍵字>', limit=3)
```

找到相關頁面後用 `getConfluencePage` 讀取，確認是否與案件觀察到的行為一致。

判斷 `confluence_status`：
- **aligned**：Confluence 有記載，且內容與觀察一致
- **conflicts**：Confluence 有記載，但與觀察不符
- **silent**：Confluence 無相關記載

取得真實 Confluence URL 填入 `provenance.confluence.urls`。

---

## Step 7：查 last_mentioned

對每個票號搜尋全部 Slack 頻道：
```
mcp__claude_ai_Slack__slack_search_public_and_private(
  query='ADQA-XXXX',
  sort='timestamp',
  sort_dir='desc',
  limit=1
)
```
取最近一條訊息的日期，格式 YYYY-MM。

找不到 → `last_mentioned: null`。

---

## Step 8：生成 pattern_id

```python
import hashlib

def make_pattern_id(channel_name, funnel_stage, domain, source_id):
    hash6 = hashlib.sha256(source_id.encode()).hexdigest()[:6]
    stage = funnel_stage[0].lower().replace('-', '')  # 取陣列第一個
    domain_slug = domain.lower().replace(' ', '-').replace('/', '-')[:20]
    return f"{channel_name}-{stage}-{domain_slug}-{hash6}"
```

`source_id`：Jira ticket key（例如 `ADQA-1664`）或 Slack thread_ts。

---

## Step 9：轉成 schema

依 `schema.json` 輸出 JSON。

**蒸餾原則：**
- 以 Slack thread 內容為主要來源
- Jira description / comments 作為補充和交叉驗證
- 欄位找不到直接答案時，**比對上下文做出合理推斷**，並在 `notes` 或 `volatile` 標注「推斷自：{來源}」
- 只有真的無法推斷才填 null，不要輕易放棄

**必填**（缺少 → 跳過這張票）：
- `pattern_id`
- `symptom.signature`
- `symptom.funnel_stage`（陣列，第一個是根源）
- `root_cause.summary`
- `root_cause.confidence`
- `status`
- `provenance.thread_refs`（含完整 URL）
- `provenance.as_of`

**盡力填**（找不到填 null，但必須試）：
- `symptom.scope_tags.ssp`
- `symptom.observable_signals`
- `symptom.metric`
- `root_cause.category`
- `resolution.fix`（by-design → `null` + `note`）
- `resolution.verified_by`
- `recurrence.count`
- `provenance.confluence.status`
- `last_mentioned`

**真的選填**（有才填）：
- `symptom.pipeline_layer`
- `root_cause.linked_change`
- `resolution.note`
- `has_workaround`
- `related_cases`（只有 Jira issuelinks 才填）
- `notes`
- `volatile`

---

## Step 10：Upsert 到 cases.jsonl

**新案件：** 直接 append。

**已存在的案件（有更新）：** Claude 智慧合併：
- 輸入：舊的 case JSON + 新的來源內容 + 新蒸餾的 case
- 保留 `pattern_id`
- 更新 `root_cause`、`resolution`、`status`、`recurrence`、`provenance.as_of`

**Atomic write（防止讀寫衝突）：**
```
1. 載入全部 cases.jsonl 到記憶體
2. 找到目標 case（透過 pattern_id 或 provenance.thread_refs）
3. 合併
4. 寫到 cases.jsonl.tmp
5. os.replace(cases.jsonl.tmp → cases.jsonl)
```

---

## Step 11：補完確認

寫入前確認：
- 每個必填欄位都有值（或明確無法取得）
- `provenance.thread_refs` 包含至少一個完整 URL
- 無法取得的資料已標記原因代碼，不留空白缺口

---

## Step 12：更新 index.json

```json
{
  "last_distilled_at": "{現在時間 ISO8601 UTC}",
  "total_cases": "{cases.jsonl 的總行數}",
  "processed": {
    "jira": {
      "ADQA-XXXX": "{處理時間}"
    },
    "slack_threads": {
      "{thread_ts}": "{處理時間}"
    }
  }
}
```

---

## 無法取得的通用代碼

| 代碼 | 意義 |
|---|---|
| `auth_required` | 需要登入 / 權限不足 |
| `link_dead` | 頁面已刪除或連結失效 |
| `fetch_failed` | 網路或伺服器錯誤 |
| `fetch_blocked` | Cloudflare 等 bot 封鎖 |
| `content_unreadable` | HTTP 200 但頁面為 JS bundle，無可讀文字 |
| `binary_content` | 影片 / 壓縮檔等無法萃取文字的格式 |
| `not_applicable` | 此類型由其他流程處理（如 Google Meet）|

---

## 輸出格式規則

每次印出 case（brew 摘要列印或 `/ask` 查詢結果）時，所有引用都必須附上可點擊連結：

| 引用類型 | 出現位置 | 連結格式 |
|---|---|---|
| Jira ticket（ADQA-XXXX、BT-XXXX、CR-XXXX 等）| provenance.thread_refs、related_cases、volatile.ticket_ids、notes | `[ADQA-XXXX](https://appier.atlassian.net/browse/ADQA-XXXX)` |
| Confluence 頁面 | provenance.confluence.urls | `[頁面標題](URL)` |

**規則：** 凡是在輸出中出現的票號或 Confluence 頁面，一律渲染為 Markdown 連結。純文字票號（無連結）視為不完整輸出。

---

## 完成後輸出摘要

```
brew 完成
  新增：N 條
  更新：N 條
  跳過：N 條（無 root cause）
  cases.jsonl 現有：N 條
  last_distilled_at：{時間}
```
