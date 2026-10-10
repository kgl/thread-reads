# thread-reads

把 X 上的長推串整理成易讀的單檔 HTML 閱讀版（台灣繁體中文）。

線上閱讀：<https://kgl.github.io/thread-reads/>

## 已發布文章

| 文章 | 作者 | 原推串 |
| --- | --- | --- |
| [Inigo the Dragon：讓 LLM 寫出一隻 27KB 的「純程式碼」小龍](https://kgl.github.io/thread-reads/dragon/) | Keenan Crane（@keenanisalive） | [x.com/i/status/2108708523236602056](https://x.com/i/status/2108708523236602056) |

## 特色

- 左側目錄：列出各段落與每則推文，捲動時自動高亮目前位置
- 單一檔案：圖片以 base64 內嵌，下載後可離線閱讀
- 深色模式：依系統設定自動切換
- 手機版：寬度小於 800px 時目錄收成頂部抽屜
- 連結展開：t.co 短網址換成實際網址，外部連結開新分頁

## Repo 結構

```text
thread-reads/
├── index.html          # 文章列表首頁
├── dragon/
│   └── index.html      # 單檔文章頁
└── tools/
    ├── thread2html.py  # 產生與發布工具
    ├── template_style.css
    ├── template_script.js
    ├── README.md       # 工具詳細說明
    └── test/           # Puppeteer 測試
```

## 快速開始

需要 Python 3.9 以上、`curl`；測試需要 Node.js 與 Chrome；發布需要已登入的 `gh`。

```bash
python3 tools/thread2html.py fetch <推文網址>
python3 tools/thread2html.py translate --template   # 填好 work/translate_template.json 後：
python3 tools/thread2html.py translate --apply work/translate_template.json
python3 tools/thread2html.py build work/translated.json
python3 tools/thread2html.py test work/index.html
python3 tools/thread2html.py publish <slug> --html work/index.html
```

詳細說明見 [tools/README.md](tools/README.md)。

## 流程

`fetch`（抓推串與圖片）→ `translate`（翻譯）→ `build`（產生 HTML）→ `test`（瀏覽器測試）→ `publish`（放到 `<slug>/index.html`、更新首頁、commit 並 push）

## 環境變數

| 變數 | 用途 | 不設定時 |
| --- | --- | --- |
| `X_BEARER_TOKEN` | `fetch` 直接呼叫 X API v2 | 改用 `--from-json` 讀取已取得的 API 回應 |
| `OPENAI_API_KEY` | `translate` 自動翻譯（OpenAI 相容 API） | 改用 `--template`／`--apply` 人工或 agent 填寫 |
| `OPENAI_BASE_URL` | 自訂 API 端點 | 預設 `https://api.openai.com/v1` |
| `OPENAI_MODEL` | 模型名稱 | 預設 `gpt-4o-mini` |
| `CHROME_PATH` | `test` 使用的 Chrome | 自動尋找 |

**金鑰只放在環境變數，不要 commit 進 repo。** `work/` 工作資料夾已列入 `.gitignore`。

## 版權說明

文章內容的著作權屬於原推串作者。這裡的翻譯與整理僅供個人閱讀，連結皆指回原推串。
