# 股票 LINE 分析機器人

在 LINE 聊天室打股票代號或名稱，機器人就即時查股價、外資買賣超與最新新聞，
簡短回覆文字並附上一張走勢圖——不限於固定清單，任何上市櫃股票都能查。

同一個服務也有一個**網站版**（依產業分類點選查股票，不用打字），
兩邊資料來源共用，各自獨立運作。全部用免費額度架設。

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

## 怎麼用：LINE 聊天室即時查股票

現在**沒有自動推播**了（原本的盤前/盤中/盤後定時分析已經關閉），改成你自己在聊天室打字查：

1. 打**股票代號**（例如 `2330`、`00895`）或**公司名稱**（例如 `台積電`、`欣興`）
2. 機器人查即時股價、三大法人（外資／投信／自營商）買賣超、最近新聞
3. 幾秒內回你一則簡短文字（現價、外資買賣超）＋一張近一月股價走勢圖
4. **不限於你原本追蹤的 24 檔**，任何上市櫃股票代號或名稱都可以查

打的內容如果不是股票代號或名稱（機器人判斷不出來），會回你使用說明，不會亂猜。

### 資料來源（老實說的限制）

股價、三大法人買賣超、走勢圖都是直接抓證交所／櫃買中心的公開資料 API，**不是 AI 查證
整理的**，所以數字準確、也不會像之前那版一樣偶爾抓錯或逾時；只有「你打的文字對應哪個
股票代號」這一步還是用 Gemini 判斷（很快，不用等即時搜尋）。

- 三大法人買賣超通常是「前一個交易日」的資料，因為要收盤後證交所才會公布當天數字
- 新聞是 Google 新聞搜尋結果，標題本身沒有經過 AI 加工篩選
- Gemini 免費額度有速率限制，短時間內查太多檔可能會被限流，等一下再查即可

如果想手動測試整批分析（原本的盤前/盤中/盤後推播功能還在，只是不會自動觸發）：
GitHub repo 頁面 →「Actions」→「stock-bot keepalive」→「Run workflow」，slot 欄位打
`premarket` / `midday` / `afterhours`，按下去即可補推一次。

---

## 怎麼用：網站點選查股票

直接開 `https://lucien-stock-bot.onrender.com/`（跟 LINE 機器人同一個服務），
不用打字，點一點就能看：

1. **首頁**：上面是你的持股快速連結，下面是依證交所官方「產業別」分類的格子牆
   （水泥、半導體、金融保險…35 類），格子大小＝該產業掛牌公司數量，也有搜尋欄可以
   直接打代號或名稱
2. **點進某個產業**：顯示底下所有個股，每檔用一個圓圈呈現——**圓圈大小＝外資買賣超力道，
   紅色＝買超、綠色＝賣超**，圈越大代表買/賣得越兇，一眼就看得出哪些股票資金在流動
3. **點進個股頁面**：股價、外資買賣超／三大法人合計、近一個月互動走勢圖（滑鼠移上去可以
   看細節，不是靜態圖片），最下面是新聞——**點標題會就地展開，不用跳到新分頁**

### 新聞「就地展開」的老實話

Google 新聞的 RSS 只給標題、來源、時間，沒有提供文章摘要或全文（這是 Google 那邊
資料源本身的限制），所以點開展開的是「來源＋時間」，看完整內容還是要點「看原文」
連結去對方網站——這點跟你確認過，先說明清楚。

### 產業分類資料來源

用的是證交所公開 API（`t187ap03_L`，上市）跟櫃買中心公開 API
（`mopsfin_t187ap03_O`，上櫃），涵蓋約 2,000 家公司，第一次讀取要花幾秒鐘抓資料，
之後同一個服務執行期間都會快取著用，不用每次都重新抓。

---

## 之後要調整的地方

- **增減追蹤股票**：改 `config.py` 裡的 `HOLDINGS` 或 `WATCHLIST_SECTORS`，存檔後在 GitHub Desktop
  裡 commit + push，Render 會自動重新部署
- **加碼／減碼、成本價有變動**：改 `config.py` 的 `HOLDINGS`，每一筆是
  `(代號, 名稱, 股數, 成本價)`，改完股數或成本，報告卡片圖跟 AI 評論就會用新數字算損益
- **想恢復定時推播**：把 `.github/workflows/schedule.yml` 裡 `schedule:` 底下加回
  `premarket`/`midday`/`afterhours` 那三個 cron（可以參考 git 歷史紀錄），時間記得是 UTC，
  要減 8 小時換算
- **Gemini 免費額度用完 / 想換更強的分析**：把環境變數 `GEMINI_API_KEY` 換成 Anthropic 的付費 API，
  這部分程式邏輯是獨立的（`ai_analysis.py`），之後要換不用動其他檔案

## 已知限制（老實說）

- Render 免費方案閒置一段時間會「休眠」，喚醒需要幾十秒，已經用 GitHub Actions **全天候
  24 小時**每 10 分鐘 ping 一次來降低這個狀況（之前只設定平日白天，結果晚上/假日問股票
  會因為伺服器睡著逾時失敗，已經修正），但 GitHub Actions 排程本身偶爾會有幾分鐘誤差，
  不保證 100% 隨問隨答零延遲
- Gemini 免費額度有速率限制，短時間內查太多檔可能會被限流（只影響「代號/名稱判斷」
  這一步，不影響股價／法人／新聞這些真實資料），稍等一下再問即可
- 持股的損益是用 `config.py` 裡填的成本價／股數計算，**不會自動同步券商帳戶**，
  加碼、減碼、換股都要自己手動更新這個檔案，不然損益數字會跟實際不符
- 已經把 `ai_analysis.py` 換成新版 `google-genai` 套件（原本的 `google-generativeai`
  官方已經棄用）
- 上櫃（OTC）股票的歷史日線資料來源目前只支援上市（TSE），查上櫃股票可能只有文字
  （股價／法人／新聞），沒有走勢圖

## 個股即時查詢圖表

聊天室打股票代號或名稱時，會畫一張乾淨的近一月股價走勢圖（單一折線＋現價標記），
刻意用大字體、高解析度，避免在手機上看起來模糊或字太小；LINE 打開就能直接看到，
不用點連結。

- 走勢圖的畫圖邏輯在 `charts.py` 的 `generate_price_trend_chart()`（Matplotlib）
- 想調整版面、配色，改這支檔案裡的顏色常數跟畫圖邏輯即可
- 中文字型放在 `fonts/NotoSansTC-Variable.ttf`（Google Noto Sans TC，開源可商用），
  這個檔案有點大（約 12MB），是必要的，因為 Render 的 Linux 伺服器沒有內建中文字型，
  沒有這個檔案畫出來的中文會變成空白方框
