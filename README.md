# adqa-agent

ADQA 知識庫。從 Slack 與 Jira 蒸餾的調查案例，用自然語言查詢。

---

## 快速開始

在 Claude Code 輸入：

```
/ask 最近 InMobi endcard 有什麼問題？
```

不需要開 server、不需要設定。

---

## `/ask` — 查詢

直接問問題，Claude 搜尋知識庫回答。

```
/ask Vungle deeplink 為什麼 open rate 突然掉？
/ask Pangle KR auto-click 怎麼確認？
/ask parallel ping 在哪些 SSP 有問題？
```

**切換語氣 persona：**

```
/ask --as pineapple_wu InMobi 有沒有 endcard 亂碼的案例？
```

預設語氣是 Aiden Chen。可用的 persona：

| `--as` 參數 | 特點 |
|---|---|
| `aiden_chen`（預設）| 直接給結論、定責任 |
| `andy_yu` | 先背景再任務、分優先順序 |
| `kochi_chuang` | 分步指引、務實縮小範圍 |
| `howard_cheng` | pseudo-code 思維、numbered steps |
| `pineapple_wu` | 整理後再說、票號配齊 |

---

## 如何快速查找

知識庫的案例可以用以下維度搜尋，直接在問句裡提到就好：

- **SSP**：`Vungle`、`Pangle`、`InMobi`、`Bidmachine`、`Google`、`Naver`...
- **問題類型**：CTR 異常、open rate 下降、endcard 渲染、attribution 認列失敗...
- **漏斗階段**：Traffic / Bid / Win-Show / Click / Action
- **客戶 / 市場**：Coupang KR、Rakuten JP...
- **關鍵字**：auto-click、deeplink、parallel ping、endcard、HTML entity...

找不到答案時 `/ask` 會提示你執行 `/brew` 更新知識庫。

---

## 案例分類

每個案例標記了以下欄位，回答時會一併說明：

| 欄位 | 說明 |
|---|---|
| `root_cause.category` | `upstream-ssp` / `appier-creative` / `appier-pipeline` / `traffic-quality` 等 |
| `root_cause.confidence` | `confirmed`（有實刷驗證）/ `likely`（推斷）/ `unverified` |
| `status` | `resolved` / `known-degradation` / `recurring` |
| `last_mentioned` | 最後在 Slack 出現的時間，超過 6 個月會提醒補驗 |

---

## `/brew` — 更新知識庫

從 Slack 和 Jira 拉新案例進來。知識庫沒有答案時先跑一次：

```
/brew
```
