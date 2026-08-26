# 中央大學商事法課程_實務案例集（company-law-cases）

![Profile views](https://komarev.com/ghpvc/?username=mjib007-company-law-cases&label=Profile%20views&color=4c8eda&style=flat)
[![License](https://img.shields.io/badge/License-CC%20BY--NC%204.0-lightgrey)](LICENSE)
![Status](https://img.shields.io/badge/status-active-success)

中央大學商事法課程用教學專案。以《圖解公司法》章節架構為骨幹，結合公司法、證券交易法相關實務案例，供課堂學習、案例討論與同學提交作業使用，同時作為本書未來改版的素材庫。

**總覽頁（GitHub Pages）**：https://mjib007.github.io/company-law-cases/

## 這個 repo 是什麼

- **章節骨架**：依《圖解公司法》目錄建立對應分類（見 `index.html` 中的 `CHAPTERS`），涵蓋公司法第一章至第九章
- **內容**：教師筆記與學生提交案例統一放在 `講義/` 資料夾（平面結構，不分子資料夾），透過 `index.html` 的分類標籤關聯到對應章節
- **課堂評分**：同學提交內容的完整度與品質，將作為課堂評分依據之一

## 如何參與（同學適用）

請參考 [CONTRIBUTING.md](./CONTRIBUTING.md) 了解案例提交方式。

## 目錄結構

```
company-law-cases/
├── index.html          # 總覽頁（分類地圖＋搜尋＋卡片牆，GitHub Pages 進入點）
├── 講義/                 # 教師筆記與學生案例（平面存放，分類靠 index.html 內的 metadata）
├── CONTRIBUTING.md
└── LICENSE
```

新增內容時，只需要：
1. 把 HTML 檔案放進 `講義/` 資料夾
2. 在 `index.html` 的 `LECTURES` 陣列裡新增一筆物件（條號、標題、日期、對應章節 key、檔案路徑、author 為 teacher 或 student）

## 授權

本專案採用 [CC BY-NC 4.0](./LICENSE) 授權，僅限非商業用途使用與轉載，並須標明出處。

## 免責聲明

本專案內容僅供教學討論使用，不構成法律意見。案例分析為教學目的整理，實際案件應以判決全文與專業法律諮詢為準。
