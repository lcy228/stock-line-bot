# 股票 LINE 分析機器人

在 LINE 聊天室打股票代號或名稱，機器人就即時查即時行情、財報重點與最新新聞，
畫一張分析卡片圖回覆——不限於固定清單，任何上市櫃股票都能查。全部用免費額度架設。

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
2. 機器人會即時上網查這檔股票最新的財報重點、新聞消息，並抓即時報價
3. 大約 10～30 秒後（要等即時搜尋＋畫圖），回你一則文字＋一張跟這次幫你做的報告一樣風格的
   分析卡片圖（財報／新聞／位階／買點四個區塊＋價位區間圖）
4. **不限於你原本追蹤的 24 檔**，任何上市櫃股票代號或名稱都可以查

打的內容如果不是股票代號或名稱（機器人判斷不出來），會回你使用說明，不會亂猜。

### 老實說的限制

這是即時用 Gemini + Google 搜尋現查現答，跟我在對話裡幫你反覆查證好幾個來源做出來的報告
比，準確度會低一些：
- 財報數字、新聞內容偶爾可能抓錯或抓到舊資料，重大決策前建議跟我在對話裡再確認一次
- 免費額度下即時搜尋有次數限制，短時間內查太多檔可能會被限流，等一下再查即可
- 回覆需要現查現算，不會秒回，屬正常現象

如果想手動測試整批分析（原本的盤前/盤中/盤後推播功能還在，只是不會自動觸發）：
GitHub repo 頁面 →「Actions」→「stock-bot keepalive」→「Run workflow」，slot 欄位打
`premarket` / `midday` / `afterhours`，按下去即可補推一次。

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
- Gemini 免費額度有速率限制，短時間內問很多問題（尤其即時搜尋更耗額度）可能會被限流，
  稍等一下再問即可
- 「觀察買點」是 AI 即時搜尋＋技術面推估出的參考觀察，不是投資建議
- 持股的損益是用 `config.py` 裡填的成本價／股數計算，**不會自動同步券商帳戶**，
  加碼、減碼、換股都要自己手動更新這個檔案，不然損益數字會跟實際不符
- 聊天室即時查詢的財報、新聞分析是 Gemini 自己上網查證整理，**準確度不會跟我在對話裡
  幫你反覆核對多個來源做出來的報告一樣高**，數字偶爾可能有誤差，重大決策前建議直接在
  對話裡跟我確認一次
- 已經把 `ai_analysis.py` 換成新版 `google-genai` 套件（原本的 `google-generativeai`
  官方已經棄用），並加上 Google 搜尋 grounding 讓它能真的即時查資料

## 個股即時分析卡片圖

聊天室打股票代號或名稱時，會即時畫一張排版好看的分析卡片圖
（風格跟「股市戰情室」一樣：統計條＋財報／新聞／位階／買點四區塊＋價位區間圖），
LINE 打開就能直接看到，不用點連結。

- 卡片圖的排版邏輯在 `report_image.py`（用 Pillow 手繪，不是網頁截圖 —— 截圖
  需要開一個完整瀏覽器，在 Render 免費方案的記憶體上太吃緊，容易把服務弄掛）
- 想調整版面、配色，改這支檔案裡的顏色常數跟畫圖邏輯即可
- 內容資料來自 `ai_analysis.py` 的 `deep_dive_report()`，即時用 Gemini + Google 搜尋
  查證整理，不是固定不變的資料
- 中文字型放在 `fonts/NotoSansTC-Variable.ttf`（Google Noto Sans TC，開源可商用），
  這個檔案有點大（約 12MB），是必要的，因為 Render 的 Linux 伺服器沒有內建中文字型，
  沒有這個檔案畫出來的中文會變成空白方框
