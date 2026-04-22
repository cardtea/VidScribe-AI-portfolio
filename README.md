# 🎬 VidScribe AI

**Professional Video Analysis & Summarization Tool**

VidScribe AI 是一款強大的影片分析工具，結合了 AI 語音轉錄與智慧摘要功能，能夠快速將 YouTube 或 Bilibili 影片轉換為結構化的文字報告。

---

## ✨ 主要特色

- 🚀 **高速處理**：多執行緒下載 + GPU 加速轉錄
- 🤖 **AI 智慧摘要**：使用 Google Gemini 3.0/2.5 系列模型進行深度分析
- 🎨 **現代化介面**：Glassmorphism 毛玻璃設計 + 深色/淺色主題切換
- 📝 **雙模式處理**：
  - **僅轉錄模式**：快速獲取逐字稿
  - **完整分析模式**：AI 生成結構化報告
- 🌍 **多語言支援**：自動檢測影片語言（中文、英文、日文、韓文等）
- 💾 **自動備份**：逐字稿與報告自動保存至本地

---

## 🛠️ 技術架構

### 核心技術
- **前端框架**：[NiceGUI](https://nicegui.io/) (基於 Quasar/Vue.js)
- **語音轉錄**：[Faster Whisper](https://github.com/SYSTRAN/faster-whisper) (CUDA 加速)
- **AI 摘要**：Google Gemini API (2.5/3.0 系列)
- **影片下載**：yt-dlp

### 系統需求
- Python 3.8+
- NVIDIA GPU (支援 CUDA 12.1+) - 可選，用於加速轉錄
- 8GB+ RAM (建議 16GB)
- Windows / Linux / macOS

---

## 📦 安裝步驟

### 1. Clone 專案
```bash
git clone https://github.com/cardtea/<your-public-repo-name>.git
cd <your-public-repo-name>
```

將 `<your-public-repo-name>` 替換成你建立的公開 repository 名稱即可。

### 2. 建立虛擬環境
```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate
```

### 3. 安裝依賴
```bash
pip install -r requirements.txt
```

### 4. 設定 API Key
專案提供可提交的範本檔 `config/settings.example.json`，實際使用的 `config/settings.json` 已加入 `.gitignore`，不會被推上 GitHub。

在首次啟動後，於左側設定欄位輸入您的 **Google Gemini API Key**。

> 🔑 取得 API Key：https://aistudio.google.com/apikey

---

## 🚀 使用方式

### 啟動應用程式
```bash
python main.py
```

應用程式將在 `http://localhost:8080` 啟動。

### 基本操作流程
1. **貼上影片網址**：支援 YouTube 或 Bilibili
2. **選擇處理模式**：
   - 📝 **Transcript Only**：僅轉錄逐字稿
   - 🤖 **Full Analysis**：AI 完整分析
3. **等待處理**：查看即時進度與系統日誌
4. **查看報告**：自動顯示 Markdown 格式的分析結果

---

## ⚙️ 設定選項

### Gemini 模型選擇
- `gemini-3-pro-preview` - 最強大的多模態模型
- `gemini-2.5-flash` - 性價比最高，速度快
- `gemini-2.5-pro` - 進階思考模型

### 轉錄配置檔案
- **Fast / Eco** (Distil-Large-V3) - 快速、低資源消耗
- **Balanced** (Turbo) - 平衡速度與準確度
- **Accurate** (Large-V3) - 最高準確度

### Prompt 模板
可在 `config/prompts/` 目錄下自訂分析提示詞。

---

## 📁 專案結構

```
VidScribe-AI/
├── main.py                 # 主程式入口
├── core/                   # 核心模組
│   ├── downloader.py       # 影片下載器
│   ├── transcriber.py      # 語音轉錄
│   ├── summarizer.py       # AI 摘要
│   └── monitor.py          # 系統監控
├── utils/                  # 工具函式
│   ├── logger.py           # 日誌系統
│   ├── file_handler.py     # 檔案處理
│   └── text_cleaner.py     # 文字清理
├── config/                 # 設定檔
│   ├── settings.example.json # 可提交的設定範本
│   ├── settings.json       # 本機使用者設定（已忽略）
│   └── prompts/            # Prompt 模板
├── downloads/              # 輸出目錄
│   └── saved_transcripts/  # 逐字稿備份
└── requirements.txt        # Python 依賴
```

---

## 🎨 UI 預覽

- **現代化設計**：毛玻璃效果 + 漸層按鈕
- **深色/淺色主題**：一鍵切換
- **即時監控**：CPU、RAM、GPU、VRAM 使用率
- **進度追蹤**：整體進度 + 當前步驟細節

---

## 🐛 常見問題

### Q: 無法下載影片？
A: 請確認網址正確，並檢查 `yt-dlp` 是否為最新版本：
```bash
pip install --upgrade yt-dlp
```

### Q: GPU 加速無法使用？
A: 請確認：
1. 已安裝 NVIDIA CUDA Toolkit 12.1+
2. PyTorch 已正確安裝 CUDA 版本
3. 檢查 `torch.cuda.is_available()` 是否回傳 `True`

### Q: API 配額不足？
A: Gemini API 有免費額度限制，請前往 [Google AI Studio](https://aistudio.google.com/) 查看使用情況。

---

## 📝 授權條款

MIT License - 詳見 [LICENSE](LICENSE) 檔案
