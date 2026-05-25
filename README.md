# 課程推薦 LINE Bot
### RAG-Based Course Recommendation Chatbot for LINE

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-async-green)
![LINE Bot](https://img.shields.io/badge/Platform-LINE%20Bot-brightgreen)
![OpenAI](https://img.shields.io/badge/LLM-GPT--4o--mini-orange)

基於 RAG（檢索增強生成）技術的 LINE Bot，使用者輸入學習目標或職涯方向，機器人自動從課程資料庫中挑選最相關的 3 門課程並說明推薦原因。

---

## 功能特色

- **意圖識別**：自動判斷訊息為課程詢問、打招呼或無關內容，分流處理
- **關鍵字萃取**：從使用者問題中抽出職業角色、技能與領域關鍵字
- **語意向量搜尋**：以 FAISS + MMR 演算法從課程向量庫中召回最相關文件，兼顧相關性與多樣性
- **LLM 課程推薦**：由 GPT-4o-mini 根據召回內容生成結構化的課程推薦（名稱、推薦理由、可學技能）
- **非同步架構**：全流程 async/await，搭配 FastAPI 處理高併發 Webhook 請求

---

## 系統需求

- Python 3.10+
- OpenAI API 帳號（需支援 `gpt-4o-mini` 與 `text-embedding-3-small`）
- LINE Developers 帳號（Messaging API Channel）
- 可對外的 HTTPS Webhook 端點（本機開發可用 [ngrok](https://ngrok.com/)）
- 預先建立的 FAISS 向量索引資料夾 `faiss_index_recommand/`

---

## 安裝步驟

### 1. 複製專案

```bash
git clone https://github.com/<your-username>/課程推薦聊天機器人.git
cd 課程推薦聊天機器人
```

### 2. 建立虛擬環境

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate
```

### 3. 安裝套件

```bash
pip install -r requirements.txt
```

### 4. 設定環境變數

```bash
cp .env.example .env
# 以文字編輯器開啟 .env 並填入真實金鑰
```

---

## 環境變數設定說明

請參考 `.env.example`，複製為 `.env` 後填入以下三個值：

| 變數名稱 | 說明 | 取得位置 |
|---------|------|---------|
| `OPENAI_API_KEY` | OpenAI API 金鑰，用於 LLM 推理與向量嵌入 | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| `LINE_CHANNEL_SECRET` | 驗證 LINE Webhook 請求簽名 | LINE Developers Console > Basic settings |
| `LINE_ACCESS_TOKEN` | 呼叫 Messaging API 回覆訊息 | LINE Developers Console > Messaging API |

---

## 使用方式

### 啟動伺服器

```bash
python course_recommend.py
# 或使用 uvicorn
uvicorn course_recommend:app --host 0.0.0.0 --port 8000 --reload
```

### 設定 LINE Webhook

1. 使用 ngrok 或其他工具建立 HTTPS 隧道：
   ```bash
   ngrok http 8000
   ```
2. 將取得的網址填入 LINE Developers Console 的 Webhook URL：
   ```
   https://<your-ngrok-domain>/callback
   ```
3. 點選「Verify」確認連線成功。

### 確認服務狀態

```bash
curl http://localhost:8000/status
# 回傳 {"message": "running"} 表示正常
```

### 對話範例

| 使用者輸入 | 機器人回應 |
|-----------|-----------|
| 「你好」 | 功能說明與使用引導 |
| 「我想成為資料分析師」 | 推薦 3 門相關課程，含推薦理由與可學技能 |
| 「今天天氣如何？」 | 告知僅提供課程推薦服務 |

---

## 專案結構

```
課程推薦聊天機器人/
├── course_recommend.py    # 主程式：FastAPI 應用、LINE Bot 處理、RAG 推薦邏輯
├── faiss_index_recommand/ # FAISS 向量索引（本機建立，不納入版本控制）
├── .env                   # 真實環境變數（不納入版本控制）
├── .env.example           # 環境變數範本
├── .gitignore             # Git 忽略規則
├── requirements.txt       # Python 套件相依清單
└── README.md              # 本文件
```

---

## 注意事項與已知限制

- **FAISS 索引須自行建立**：`faiss_index_recommand/` 不包含於此 repo，需自行準備課程資料並執行向量化腳本建立索引後才能運行。
- **課程資料格式**：每筆文件的 metadata 應包含 `教學目標` 與 `課程內容` 欄位，`source` 欄位作為課程名稱來源（參見 `rag_retrieve` 函式）。
- **推薦數量固定為 3 門**：Prompt 設計固定輸出 3 筆，若向量庫課程數量不足可能影響品質。
- **LINE 訊息長度限制**：LINE 單則文字訊息上限為 5000 字元，若 LLM 輸出過長可能遭截斷。
- **僅支援文字訊息**：目前不處理圖片、貼圖、位置等其他訊息類型。
- **費用**：每次對話約呼叫 OpenAI API 3 次（意圖判斷 + 關鍵字萃取 + 課程推薦），請留意用量與費用。
