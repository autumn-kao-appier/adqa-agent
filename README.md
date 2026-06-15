# adqa-agent

ADQA 知識庫。從 Slack 與 Jira 蒸餾的調查案例，用自然語言查詢。

---

## 使用者：連上 MCP Server

> 需要先掛 **Appier VPN**。

在 Claude Code 的 `settings.json` 加一段：

```json
{
  "mcpServers": {
    "adqa-agent": {
      "type": "http",
      "url": "http://10.112.211.17:8080/mcp/"
    }
  }
}
```

設定完重啟 Claude Code，之後直接問 Claude 就好：

```
Pangle KR auto-click 是什麼問題？
InMobi endcard 亂碼怎麼發生的？
Mintegral attribution 為什麼收不到？
```

Claude 會自動呼叫知識庫回答，不需要下任何指令。

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
