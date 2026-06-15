---
name: askagent
description: 查詢 skill — 用自然語言問 ADQA 知識庫，Claude 語意搜尋 threads.jsonl 回答。
---

# askagent — 查詢 Skill

使用者問問題時啟動。對話方式與 adqa-claude-kit 完全相同。

---

## Step 0：載入語氣 persona

1. 讀取 `__ADQA_AGENT_DIR__/personas/aiden_chen/persona.md`（預設）
2. 使用者可用 `--as <name>` 切換，例如 `--as jiaxiu`，對應 `__ADQA_AGENT_DIR__/personas/<name>/persona.md`
3. Persona 只影響「怎麼說」，不影響知識庫內容
4. 找不到指定 persona 時，繼續用 aiden_chen

---

## Step 1：載入知識庫

讀取 `__ADQA_AGENT_DIR__/knowledge/threads.jsonl`，載入所有 cases。

**時效過濾（載入時先過濾）：**
以今天日期計算每條 case 的 `last_mentioned` 距今月數：
- 距今 > 12 個月 → 跳過，不載入（視為過期）
- 距今 6–12 個月，`knowledge_type: behavior` 或 `phenomenon` → 載入但標記為低可信
- 距今 6–12 個月，`knowledge_type: fact` → 維持原始 confidence
- 距今 < 6 個月 → 高可信，維持原始 confidence

每條 case 的 `volatile` 欄位預設不放進 context，只在使用者要求細節時展開。

---

## Step 2：語意搜尋

用載入的 cases 內容回答使用者的問題。

搜尋時優先考慮：
- `symptom.signature`：症狀描述
- `symptom.funnel_stage`：問題發生的 funnel 階段
- `symptom.scope_tags.ssp`：涉及的 SSP
- `root_cause.summary`：根本原因
- `status`：問題目前的狀態
- `last_mentioned`：知識新鮮度

---

## Step 3：回答

**套用 persona 語氣**：按 Step 0 載入的 persona.md 裡的「核心語氣」規則，決定回答的說話方式（直接/委婉、分步驟/摘要、中英混搭程度）。知識內容不變，只調整表達風格。

**信心校準：**

先套用時效層：
| 距今 | knowledge_type | 顯示信心 |
|---|---|---|
| < 6 個月 | 任何 | 高可信，沿用原始 confidence |
| 6–12 個月 | `fact` | 維持原始 confidence，標注「事實類，時效不衰減」 |
| 6–12 個月 | `behavior` / `phenomenon` | 低可信，標注「⚠️ 行為/現象類，距今 N 個月，建議補驗」 |
| > 12 個月 | 任何 | 已在 Step 1 過濾，不會到這裡 |

再套用原始 confidence 層（僅在時效判定為「維持原始」時）：
- `confidence: confirmed` + `confluence: aligned` → 「有案可查，可信度高」
- `confidence: confirmed` + `confluence: silent` → 「來源為 Slack/Jira，無 Confluence 對照」
- `confidence: unverified` → 「此條根因未完全確認，謹慎參考」

**回答格式：**
- 直接回答問題
- 引用 `pattern_id` 讓使用者知道依據哪條 case
- 附上 `provenance.thread_refs` 的 URL 讓使用者可以追溯原始討論
- 如果有多條相關 case，逐條說明差異
- **所有引用的 Jira ticket（related_cases、volatile.ticket_ids、notes 中出現的票號）一律附上連結：`[KEY](https://appier.atlassian.net/browse/KEY)`**
- **Confluence 頁面（provenance.confluence.urls 有值時）一律附上連結**
- 純文字票號（無連結）視為不完整輸出

**Volatile 資料：**
預設不顯示，使用者問「有具體數字嗎」或「有 ticket 號嗎」時才展開。

---

## Step 4：找不到相關案例時

說明：
```
目前知識庫沒有關於「{問題}」的案例。
上次蒸餾：{last_distilled_at}

你可以：
1. 執行 /brew 更新知識庫
2. 直接搜尋 Slack：/too-long-too-read + 相關 thread URL
```

---

## 使用範例

```
使用者：最近 Pangle endcard 有什麼問題？

ask 回答：
根據知識庫，Pangle endcard 有以下兩條相關案例：

1. [qa-crossx-newcomer-win-show-pangle-endcard-blank-b2c1]
   症狀：Pangle 第一方 HTML endcard 顯示全白
   根因：Pangle server 尚未完成修復（2025-10，confirmed）
   狀態：resolved — SSP 修復後驗證通過
   最後提及：2025-11
   來源：https://appier.atlassian.net/browse/ADQA-1659

2. [qa-crossx-newcomer-win-show-pangle-ios-gesture-c3d2]
   症狀：Pangle iOS 引導手勢 overlay 導致 campaign 暫停
   根因：Pangle 引導手勢設計（2025-10，confirmed）
   狀態：resolved — 手勢已移除，第三方 mintegral 仍殘留
   最後提及：2025-10
   來源：https://appier.atlassian.net/browse/ADQA-1654
```
