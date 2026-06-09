---
name: ask
description: 查詢 skill — 用自然語言問 ADQA 知識庫，Claude 語意搜尋 cases.jsonl 回答。
---

# ask — 查詢 Skill

使用者問問題時啟動。對話方式與 adqa-claude-kit 完全相同。

---

## Step 1：載入知識庫

讀取 `playbook/cases.jsonl`，載入所有 cases。

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

**信心校準：**
- `root_cause.confidence: confirmed` + `provenance.confluence.status: aligned` → 明確說「有案可查，可信度高」
- `root_cause.confidence: confirmed` + `confluence: silent` → 說「來源為 Slack/Jira，無 Confluence 對照」
- `root_cause.confidence: unverified` → 說「此條根因未完全確認，謹慎參考」
- `last_mentioned` 超過 6 個月 → 標注「知識較舊，建議補驗」

**回答格式：**
- 直接回答問題
- 引用 `pattern_id` 讓使用者知道依據哪條 case
- 附上 `provenance.thread_refs` 的 URL 讓使用者可以追溯原始討論
- 如果有多條相關 case，逐條說明差異

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
