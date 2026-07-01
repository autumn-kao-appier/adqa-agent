# adqa-agent

這個 repo 是 ADQA 知識庫的 MCP server。

## 工具使用規則

當使用者問任何廣告相關問題（SSP、CTR、deeplink、attribution、endcard、campaign 等）：

**必須用 adqa-agent MCP tools，禁止用其他方式查：**
- ❌ 不能用 Bash、grep、Read 去讀 `knowledge/` 底下的 `.jsonl` 檔
- ❌ 不能自己去搜 Jira 或 Confluence
- ✅ 只能呼叫下面這三個 MCP tools：

| Tool | 用途 |
|---|---|
| `search_knowledge` | ADQA 調查案例（SSP 問題、指標異常、creative bug） |
| `search_frontline` | CM frontline ops 快速處理紀錄 |
| `list_cases` | 列出特定 SSP 或狀態的案例清單 |

## Persona

呼叫 `search_knowledge` 或 `search_frontline` 時，預設帶 `persona: "aiden_chen"`。  
使用者明確指定其他人（andy_yu、kochi_chuang、pineapple_wu、howard_cheng）時才換。

## 輸出規則

**MCP tool 回傳的文字直接輸出給使用者，不要改寫、不要重新整理、不要加自己的前言。**  
Tool 回傳的內容已經是 persona 語氣，你改寫就會洗掉他的風格。

## 流程

1. 收到廣告相關問題 → 直接 call `search_knowledge(query=..., persona="aiden_chen")`
2. 如果找不到 → 用 `search_frontline` 再試一次
3. 都沒有 → 告知知識庫沒有這條案例，建議聯絡 Autumn 補充
