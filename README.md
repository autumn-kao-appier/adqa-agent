# adqa-agent

ADQA 知識庫。從 Slack 與 Jira 蒸餾的調查案例，用自然語言查詢。

---

## 使用者：連上 MCP Server

> 需要先掛 **Appier VPN**。

**Step 1 — 加 MCP server（只需做一次）**

在 Claude Code input box 最前面打 `!` 執行：

```
! claude mcp add adqa-agent --transport http http://10.112.211.17:8080/mcp
```

**Step 2 — 確認有沒有加進去**

```
! claude mcp list
```

看到 `adqa-agent  http://10.112.211.17:8080/mcp` 就對了。

**Step 3 — 開新的 Claude Code 視窗**

MCP 是 session 啟動時載入，目前這個視窗不會生效。開新 terminal 跑 `claude`，或 desktop app 開新視窗。

**Step 4 — 開問**

直接用自然語言問，Claude 會自動呼叫知識庫：

```
Pangle KR auto-click 是什麼問題？
InMobi endcard 亂碼怎麼發生的？
Mintegral attribution 為什麼收不到？
```

加一句「用 Aiden 口氣回答」可以切換回答風格（也支援 andy_yu、kochi_chuang、pineapple_wu、howard_cheng）。

---

## 可以查什麼

| 維度 | 範例 |
|---|---|
| SSP | Vungle、Pangle、InMobi、Mintegral、Kakao、Aseal... |
| 問題類型 | CTR 異常、open rate 下降、endcard 渲染、attribution 認列失敗 |
| 漏斗階段 | Traffic / Win-Show / Click / Action |
| 客戶 / 市場 | Coupang KR、Rakuten JP、Coupang TW... |
| 關鍵字 | auto-click、deeplink、parallel ping、endcard、HTML entity |

---

## 回答格式說明

| 欄位 | 說明 |
|---|---|
| `root_cause.confidence` | `confirmed`（有實刷驗證）/ `likely`（推斷）/ `unverified` |
| `status` | `resolved` / `known-degradation` / `by-design` |
| `last_mentioned` | 最後在 Slack 出現的時間，超過 6 個月會提醒補驗 |

---

## 知識庫維護者

知識庫由 Autumn 維護，定期從 Slack 與 Jira 蒸餾新案例。

如果查不到你想要的案例，聯絡 Autumn 補充。
