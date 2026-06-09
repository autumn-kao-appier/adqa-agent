# adqa-knowledge-mcp

ADQA 知識庫 — 從 Slack 與 Jira 蒸餾的調查案例，可對話查詢。

和 adqa-claude-kit 一樣的操作方式：呼叫 skill，Claude 直接回答。不需要 Python server。

---

## 結構

```
adqa-knowledge-base/
  ├── playbook/
  │   ├── cases.jsonl       ← 知識庫（每行一個案例）
  │   └── index.json        ← 狀態（上次蒸餾時間、已處理來源）
  ├── skills/
  │   ├── ask/SKILL.md      ← 對話查詢
  │   └── brew/SKILL.md     ← 蒸餾（too-long-to-read 上層）
  ├── config/
  │   └── channels.yaml     ← 監控的 Slack channel
  ├── schema.json           ← Case schema（source of truth）
  └── README.md
```

---

## 使用

**查詢：**
```
/ask 最近 Pangle endcard 有什麼問題？
```

**手動蒸餾：**
```
/brew
```

**Scheduler：** 每天 09:00 自動跑 `/brew`。

---

## Schema 設計原則

- 包含 Pineapple Wu 的完整 schema，額外加上 `last_mentioned`
- `funnel_stage` 為陣列，第一個是根源階段（Traffic / Bid / Win-Show / Click / Action）
- `volatile` 欄位隔離具體數字/日期/ticket 號，不進 prompt cache 穩定層
- `provenance.thread_refs` 含完整 URL（Jira + Slack），可追溯原始討論
- 三層欄位：必填 / 盡力填（找不到填 null）/ 真的選填

詳見 `schema.json`。

---

## 知識新鮮度

- Slack 是主要來源（Jira 上的票常常開了就放著）
- `last_mentioned` 追蹤最近在 Slack 被提及的時間，判斷知識是否仍被使用
- Brew 每天更新，確保知識庫同步最新已結案案例

---

## 目前監控的 channel

- `#qa-crossx-newcomer`（C02UBHUKBPW）
