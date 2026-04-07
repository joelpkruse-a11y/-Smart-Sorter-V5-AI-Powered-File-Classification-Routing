<p align="center">
  <img src="https://img.shields.io/badge/Smart%20Sorter%20V5-AI%20Powered%20File%20Automation-4B9CD3?style=for-the-badge&logo=google&logoColor=white" alt="Smart Sorter V5 Banner">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Gemini%202.5%20Pro-Structured%20AI%20Classification-7A42F4?style=for-the-badge&logo=google&logoColor=white" alt="Gemini Badge">
  <img src="https://img.shields.io/badge/Google%20Vision-OCR%20Enabled-34A853?style=for-the-badge&logo=google&logoColor=white" alt="Vision Badge">
  <img src="https://img.shields.io/badge/Smart%20Mode%20V2-Deterministic%20Refinement-FBBC05?style=for-the-badge" alt="Smart Mode Badge">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/OneDrive%20Safe-Watcher%20Optimized-0078D4?style=for-the-badge&logo=microsoft&logoColor=white" alt="OneDrive Badge">
  <img src="https://img.shields.io/badge/Dynamic%20Routing-Auto%20Folder%20Creation-FF6F61?style=for-the-badge" alt="Dynamic Routing Badge">
  <img src="https://img.shields.io/badge/Photos%20%2F%20Videos-Date%20Based%20Sorting-4285F4?style=for-the-badge" alt="Date Routing Badge">
</p>

# Smart Sorter V5  
AI‑Powered Document, Photo, and Video Classification & Routing System  
Author: Joel Kruse

---

## 📌 Overview

Smart Sorter V5 is an intelligent, automated file‑sorting system designed to classify, rename, and route documents, photos, and videos into a clean, self‑organizing folder structure.

It uses:

- **Gemini 2.5 Pro** for strict, structured document understanding  
- **Smart Mode V2** for deterministic category refinement  
- **Google Vision OCR** for document‑photo detection  
- **Dynamic routing** for new categories  
- **Date‑based routing** for photos and videos  
- **OneDrive‑safe file watching**  
- **A real‑time debug dashboard**  

Smart Sorter V5 is built for reliability, clarity, and long‑term maintainability.

---

## 🚀 Key Features

### **1. AI‑Powered Classification**
- Gemini 2.5 Pro performs structured extraction:
  - Category  
  - Confidence  
  - Metadata  
  - Tables  
  - Reasoning  
  - Clean filename suggestion  

### **2. Smart Mode V2**
A deterministic refinement layer that:
- Normalizes categories  
- Corrects ambiguous classifications  
- Forces review when confidence is low  

### **3. Clean Filename Rules**
Smart Sorter V5 applies strict, predictable filename rules:

| Category Type | Filename Format |
|---------------|-----------------|
| **Photos** | `YYYY-MM-DD BaseName.ext` |
| **Videos** | `BaseName.ext` |
| **Other** | `BaseName.ext` |
| **Meaningful Categories** | `Category - BaseName.ext` |

No double extensions.  
No category pollution for photos/videos/other.  
No dates except for photos.

### **4. Dynamic Folder Creation**
If a category is **not** predefined in config.json, Smart Sorter creates:

```
Sorted/<NewCategory>/
```

Example:
```
Sorted/Personal credentials/
Sorted/Identity documents/
Sorted/Eyecare/
```

### **5. Date‑Based Routing for Photos & Videos**
Photos and videos are routed to:

```
Photos/YYYY/MM/
Videos/YYYY/MM/
```

### **6. OneDrive‑Safe File Handling**
- Waits for file stability  
- Retries locked files  
- Avoids race conditions  

### **7. Real‑Time Debug Dashboard**
Runs on:
```
http://localhost:8765
```

Shows:
- Original filename  
- AI category  
- Smart Mode category  
- Final filename  
- Metadata  
- Reasoning  
- Routing destination  

---

## 📁 Folder Structure

Example final structure:

```
Sorted/
│
├── Finance/
├── Insurance/
├── Medical/
├── Legal/
├── Taxes/
├── Personal/
│   ├── Subscriptions/
│   └── Warranties/
│
├── Photos/
│   └── 2024/
│       └── 02/
│
├── Videos/
│   └── 2024/
│       └── 02/
│
├── Review/
│
└── <New Dynamic Categories Created Automatically>
    ├── Personal credentials/
    ├── Identity documents/
    ├── Auto insurance/
    └── Eyecare/
```

---

## ⚙️ Configuration (config.json)

Key sections:

### **destinations**
Defines:
- Predefined category folders  
- Photos/videos roots  
- Review folder  
- Dynamic category root (`sorted_root`)  

### **classification**
Defines file extensions for:
- Photos  
- Videos  
- Documents  

### **ai_classification**
Controls:
- Gemini model  
- Google Vision OCR  
- Ollama fallback  

### **observer_groups**
Defines watched folders:
- Downloads  
- Scans  
- PhoneLink  
- OneDrive Camera  
- Meta AI folder  

### **initial_scan_groups**
Folders scanned once at startup.

---

## 🔄 Processing Pipeline

1. **File detected** by OneDrive‑safe watcher  
2. **File readiness check** (size stability)  
3. **Document‑photo detection** (OCR + heuristics)  
4. **Gemini structured classification**  
5. **Smart Mode V2 refinement**  
6. **Filename generation** (strict rules)  
7. **Routing** (predefined or dynamic)  
8. **Move with retry**  
9. **Dashboard event logged**  

---

## 🧠 Filename Rules (Detailed)

### **Photos**
- Extract date from:
  1. EXIF  
  2. Metadata  
  3. Filesystem timestamp  
- Format:
```
YYYY-MM-DD BaseName.ext
```

### **Videos**
```
BaseName.ext
```

### **Other**
```
BaseName.ext
```

### **Meaningful Categories**
```
Category - BaseName.ext
```

---

## 🗂 Dynamic Category Creation

If Gemini returns a category not listed in config.json:

```
Sorted_root/<CategoryName>/
```

Example:
```
Sorted/Employment verification/
Sorted/Identity documents/
Sorted/Medical forms/
```

---

## 🛠 Requirements

- Python 3.10+  
- fitz (PyMuPDF)  
- python-docx  
- Pillow  
- numpy  
- OpenCV (optional)  
- Google Vision API (optional)  
- Gemini API key  
- OneDrive installed (optional but recommended)  

---

## ▶️ Running Smart Sorter V5

Run:

```
python smart_sorter_v5.py
```

Dashboard starts automatically at:

```
http://localhost:8765
```

---

## 🧪 Testing

Drop files into any watched folder:

- Downloads  
- Scans  
- PhoneLink  
- OneDrive Camera  
- Meta AI  

Watch them appear in:

```
Sorted/<Category>/
```

With clean filenames and correct routing.

---

## 🧩 Troubleshooting

### File stuck in place  
Likely OneDrive lock → sorter retries automatically.

### Wrong category  
Check dashboard reasoning.  
Adjust Smart Mode V2 rules if needed.

### New category created unexpectedly  
Add it to config.json if you want it predefined.

---

## 📜 License

Internal personal project — no license required.

---

## ✨ Author

**Joel Kruse**  
Creator of Smart Sorter V5  
Automation engineer & workflow architect 
