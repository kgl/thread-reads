# thread2html：把 X 推串整理成單檔 HTML

把一串 X 長推串抓下來、翻成台灣繁體中文，產生一個離線可讀的單檔 HTML（左側目錄、圖片內嵌），再發布到這個 repo 的 GitHub Pages。範例：[dragon/](https://kgl.github.io/thread-reads/dragon/)。

## 需求

- Python 3.9 以上（只用標準函式庫）
- `curl`；影片截圖需要 `ffmpeg`（沒有時改用影片縮圖）
- 測試需要 Node.js 與 Chrome／Chromium（`CHROME_PATH` 可指定路徑）；第一次執行 `test` 會在 `tools/test/` 安裝 `puppeteer-core`
- 發布需要已登入的 `gh`（`gh auth login`，再執行 `gh auth setup-git`）

## 環境變數

| 變數 | 用途 | 必要性 |
| --- | --- | --- |
| `X_BEARER_TOKEN` | X API v2 的 Bearer Token，`fetch` 直接呼叫 API 時使用 | 用 `--from-json` 時不需要 |
| `OPENAI_API_KEY` | OpenAI 相容 API 的金鑰，`translate` 自動翻譯時使用 | 用範本模式時不需要 |
| `OPENAI_BASE_URL` | OpenAI 相容端點，預設 `https://api.openai.com/v1` | 選用 |
| `OPENAI_MODEL` | 模型名稱，預設 `gpt-4o-mini` | 選用 |
| `CHROME_PATH` | Chrome 執行檔路徑 | 選用 |

**不要把任何金鑰寫進 repo。**

## 流程

所有指令在 repo 根目錄執行，工作檔預設放在 `work/`（已列入 `.gitignore`）。每個步驟都可以單獨重跑。

```bash
# 1. 抓推串 → work/thread.json、work/media/
python3 tools/thread2html.py fetch https://x.com/i/status/2108708523236602056
#    沒有 X token 時：把 agent 用自己的 X 工具取得的原始 API 回應存成 JSON（一個或多個 {data, includes} 的陣列）
python3 tools/thread2html.py fetch 2108708523236602056 --from-json pages.json

# 2a. 翻譯（有 OPENAI_API_KEY）→ work/translated.json
python3 tools/thread2html.py translate
# 2b. 翻譯（agent 填寫）：先產生範本，填好後套用
python3 tools/thread2html.py translate --template
python3 tools/thread2html.py translate --apply work/translate_template.json

# 3. 產生 HTML → work/index.html
python3 tools/thread2html.py build work/translated.json

# 4. 測試（sandboxed iframe、桌機＋手機）
python3 tools/thread2html.py test work/index.html --shots work

# 5. 發布 → <slug>/index.html，更新根目錄列表，commit 並 push
python3 tools/thread2html.py publish my-thread --html work/index.html --note "作者，日期"

# 一次跑完（沒有 OPENAI_API_KEY 時會停在範本，填完後加 --apply 再跑）
python3 tools/thread2html.py all <推文網址> --slug my-thread
python3 tools/thread2html.py all <推文網址> --slug my-thread --from-json pages.json --apply work/translate_template.json
```

## 各步驟做了什麼

- **fetch**：只保留作者回覆自己的推文，從根推文沿著回覆鏈排序（作者回覆別人的留言不收）。長文用 `note_tweet.text`；Unicode 花式字母用 NFKC 轉回一般字元。指向推文自己圖片或影片的 t.co 會刪掉，其他 t.co 優先用 `entities.urls[].expanded_url` 展開，沒有時用 curl 跟轉址。圖片下載到 `media/`；影片與 GIF 用 ffmpeg 擷取第 `--frame-sec` 秒（預設 3 秒）的畫面，並記下最高畫質 MP4 的網址。預設用 `search/recent`（只涵蓋 7 天內）；較舊的推串加 `--archive` 改用 `search/all`（需要完整存取權限）。
- **translate**：範本含每則原文 `source_text`，要填 `zh`（純文字；程式碼或 prompt 用 ``` 包起來並保留原文）。另外要填標題、資訊列、摘要、學習要點、段落分組（`sections`），以及網址的可讀標籤（`link_labels`）。`hero.from_post` 指定哪一則的第一張圖當 hero。有缺翻譯的編號時會停下來。
- **build**：用 `template_style.css` 與 `template_script.js` 產生 HTML。圖片轉 base64，並帶真實寬高、不用 lazy 載入。外部連結開新分頁。目錄的 scroll-spy 用固定基準線，點擊時先鎖住，捲動停下再解鎖。支援深色模式與手機抽屜。
- **test**：在 `sandbox="allow-scripts"` 的 iframe 裡，桌機 1280 × 800 與手機 390 × 844 各點過每個目錄項目，檢查高亮與位置。再用滾輪捲動檢查高亮；最後檢查外部連結、lazy 圖、缺寬高的圖。任一項失敗時結束碼為 1。
- **publish**：slug 只能用小寫英數與連字號。根目錄 `index.html` 的 `<!-- LIST:START -->`／`<!-- LIST:END -->` 之間會加入新項目（同 slug 會取代）。git 沒有設定身分時，用 `gh` 帳號的 noreply 信箱提交。

## translated.json 格式

`build` 只讀這個檔，也可以手寫：`title`、`meta_html`、`hero {file, alt, caption_html}`、`summary_html`、`takeaways_html[]`、`footer_note_html`、`sections[{title, posts[{n, html, images[], note_html}]}]`。圖片路徑相對於 translated.json 所在資料夾。
