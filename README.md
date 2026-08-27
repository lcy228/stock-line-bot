# 股票 LINE 分析機器人

幫 Lucien 在盤前 / 盤中 / 盤後自動整理持股與追蹤股的即時行情、技術指標與新聞，
推播到 LINE，也能在聊天室裡直接問問題。全部用免費額度架設。

程式碼寫好了，接下來是部署三步驟：**上傳到 GitHub → 部署到 Render → 設定 LINE Webhook**。
每一步都附操作畫面該按什麼，照著做就好。

---

## 步驟一：把程式碼放上 GitHub

推薦用 **GitHub Desktop**（一般的 Mac App，不用打指令）：

1. 到 `https://desktop.github.com/` 下載安裝，打開後用你剛申請的 GitHub 帳號登入
2. 左上角「File」→「Add Local Repository」，選擇資料夾：
   `/Users/cy/Downloads/cy-agent/stock-line-bot`
3. 它會說這個資料夾還不是 repository（其實已經是了，忽略提示直接加入即可）
4. 左下角寫上一句 commit 訊息（例如「初版」），點「Commit to main」
5. 上方點「Publish repository」，**取消勾選「Keep this code private」**（保持 Public，
   這樣 GitHub Actions 的排程分鐘數才完全免費不受限），按「Publish Repository」

完成後你的程式碼就在 GitHub 上了，記得留意網址列上的 repo 網址（等等會用到）。

> 為什麼可以公開？因為金鑰（LINE token、Gemini key）都不會寫進程式碼裡，
> 是等一下分別設定在 Render 和 GitHub 的「密鑰」欄位，程式碼本身沒有任何機密資訊。

---

## 步驟二：部署到 Render

1. 到 `https://render.com/`，點右上角「Get Started」，選「GitHub」登入（用剛剛同一組 GitHub 帳號）
2. 進入後台，點「New +」→「Web Service」
3. 選擇你剛剛 Publish 的 `stock-line-bot` repository
4. 設定：
   - **Name**：隨意取，例如 `lucien-stock-bot`
   - **Region**：選 Singapore（離台灣最近）
   - **Build Command**：`pip install -r requirements.txt`
   - **Start Command**：`gunicorn app:app`
   - **Instance Type**：選 **Free**
5. 往下拉到「Environment Variables」，新增這幾組（值就是你之前申請好、收在自己那邊的金鑰）：
   | Key | Value |
   |---|---|
   | `LINE_CHANNEL_ACCESS_TOKEN` | 你的 LINE Channel access token |
   | `LINE_CHANNEL_SECRET` | 你的 LINE Channel secret |
   | `GEMINI_API_KEY` | 你的 Gemini API key |
   | `TRIGGER_SECRET` | 自己隨便打一串英數字（例如 `lucien20260824xyz`），當作排程觸發的密碼 |
   | `PUBLIC_BASE_URL` | 先留空，部署完成拿到網址後回來補上（見下一步） |
6. 點「Create Web Service」，等它跑完部署（第一次大概 2～5 分鐘）
7. 部署完成後，畫面最上面會有一個網址，長得像 `https://lucien-stock-bot.onrender.com`，
   複製起來，回到「Environment」分頁，把 `PUBLIC_BASE_URL` 填上這個網址，存檔（會自動重新部署一次）

---

## 步驟三：設定 LINE Webhook

1. 回到 LINE Developers Console（你申請 Messaging API 的地方），進入你的 Channel
2. 找到「Messaging API」分頁，「Webhook URL」欄位填：
   `https://你的render網址/webhook`（例如 `https://lucien-stock-bot.onrender.com/webhook`）
3. 點「Verify」測試連線成功（如果剛部署完 Render 還在啟動，可能要等個 30 秒再試）
4. 把「Use webhook」打開（啟用）
5. 如果 LINE 官方帳號預設有「自動回應訊息」「加入好友歡迎訊息」等功能，建議都關掉，
   避免跟我們自己的機器人回覆互相干擾（這些設定在 LINE Official Account Manager 後台）
6. 拿手機掃 Channel 頁面上的 QR Code，把這個官方帳號加為好友

---

## 步驟四：設定 GitHub Actions 排程密鑰

1. 回到 GitHub 上你的 repo 頁面，點「Settings」→ 左側「Secrets and variables」→「Actions」
2. 點「New repository secret」，新增兩組：
   | Name | Secret |
   |---|---|
   | `RENDER_APP_URL` | 你的 Render 網址，例如 `https://lucien-stock-bot.onrender.com` |
   | `TRIGGER_SECRET` | 跟步驟二填在 Render 的 `TRIGGER_SECRET` **完全一樣** 的那串字 |

排程已經寫在 `.github/workflows/schedule.yml` 裡了，設定完密鑰後就會自動生效，
每天週一到週五 08:30 / 11:30 / 14:00（台北時間）各推播一次。

---

## 測試方式

不想等到明天排程時間，可以手動測試：

1. GitHub repo 頁面 →「Actions」分頁 → 左側選「stock-bot schedule」
2. 右邊「Run workflow」，slot 欄位打 `premarket`（或 `midday` / `afterhours`），按「Run workflow」
3. 等半分鐘左右，看 LINE 有沒有收到推播

也可以直接在 LINE 聊天室打「2330」或「台積電最近怎麼樣」測試問答功能。

---

## 之後要調整的地方

- **增減追蹤股票**：改 `config.py` 裡的 `HOLDINGS` 或 `WATCHLIST_SECTORS`，存檔後在 GitHub Desktop
  裡 commit + push，Render 會自動重新部署
- **調整推播時間**：改 `.github/workflows/schedule.yml` 裡的 cron 時間（記得是 UTC，要減 8 小時換算）
- **Gemini 免費額度用完 / 想換更強的分析**：把環境變數 `GEMINI_API_KEY` 換成 Anthropic 的付費 API，
  這部分程式邏輯是獨立的（`ai_analysis.py`），之後要換不用動其他檔案

## 已知限制（老實說）

- Render 免費方案閒置一段時間會「休眠」，喚醒需要幾十秒，已經用 GitHub Actions 每 10 分鐘
  ping 一次來降低這個狀況，但不保證 100% 隨問隨答零延遲
- Gemini 免費額度有速率限制，短時間內問很多問題可能會被限流，稍等一下再問即可
- 「最佳買進時間」是技術指標＋新聞整理出的參考觀察，不是投資建議
- 目前用的 `google-generativeai` 套件官方已經標示停止維護，建議之後找時間換成新版
  `google-genai` 套件（`ai_analysis.py` 這支檔案要重寫，其他檔案不受影響），
  現在還能正常運作，不是急件

## 每次推播的報告卡片圖

`/trigger` 觸發時，除了文字訊息，還會直接畫一張排版好看的報告卡片圖
（風格參考「股市戰情室」，統計條＋ AI 評論＋分產業股價列表），
LINE 打開就能直接看到，不用點連結。

- 卡片圖的排版邏輯在 `report_image.py`（用 Pillow 手繪，不是網頁截圖 —— 截圖
  需要開一個完整瀏覽器，在 Render 免費方案的記憶體上太吃緊，容易把服務弄掛）
- 想調整版面、配色，改這支檔案裡的顏色常數跟畫圖邏輯即可
- 中文字型放在 `fonts/NotoSansTC-Variable.ttf`（Google Noto Sans TC，開源可商用），
  這個檔案有點大（約 12MB），是必要的，因為 Render 的 Linux 伺服器沒有內建中文字型，
  沒有這個檔案畫出來的中文會變成空白方框
