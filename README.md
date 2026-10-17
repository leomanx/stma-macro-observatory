# STMA Macro Signal Observatory

Local Quant dashboard สำหรับ `data/sentiment.db` โดยไม่เรียก OpenRouter, model หรือ API ใด ๆ
ระหว่างเปิดดู กรองข้อมูล หรือ export CSV

## เปิดใช้งาน

จาก PowerShell ที่โฟลเดอร์ `STMA`:

```powershell
python stma.py dashboard
```

ตัว launcher จะ:

1. เปิด `data/sentiment.db` แบบ SQLite read-only
2. ตรวจ integrity และกฎ canonical 10 themes/day
3. สร้าง presentation snapshot ที่ `public/data/dashboard.json`
4. เปิด Dashboard ใน browser
5. ตรวจเวลาของฐานทุก 5 วินาทีและ refresh snapshot เมื่อไฟล์เปลี่ยน

หยุดด้วย `Ctrl+C` ข้อมูลต้นทางจะไม่ถูกแก้ไข

Linux/RPi:

```bash
python3 stma.py dashboard --no-browser --host 0.0.0.0
```

ต้องมี Python 3 และ Node.js 22.13+ พร้อมติดตั้ง package ด้วย `npm install`
ภายใน `quant/dashboard/` หนึ่งครั้ง

## สิ่งที่วิเคราะห์

- daily macro breadth และ trailing 5-publication-day average
- theme heatmap แบบ Auto/Daily/Weekly; Auto เปลี่ยนเป็น weekly เมื่อเกิน 45 publication days
- theme explorer แสดง observed scores, ค่าเฉลี่ย 5 mentions ล่าสุด และ 10-session mention coverage
- จุดใน theme explorer ขยายตาม evidence count เพื่อไม่ให้น้ำหนักทางสายตาเท่ากันทุกวัน
- scoreboard แสดง Mean, Median, volatility (`σ`), Coverage, `n`, Positive/Negative และ Evidence/observation
- pairwise Pearson correlation พร้อม overlapping sample size (`n`)
- extraction quality ledger และ lineage ของ taxonomy/prompt/model
- daily narrative สำหรับ context
- date-filtered CSV export

## Guardrails

- `not_mentioned` คือ `NULL` เสมอ ไม่แปลงเป็น 0 และไม่ forward-fill
- event-time rolling ใช้เฉพาะครั้งที่ theme ถูกกล่าวถึง และแสดง mention coverage ประกอบ
- weekly heatmap เฉลี่ยเฉพาะ non-null observations พร้อมบอก observed/available ใน tooltip
- correlation เป็น exploratory descriptive statistic ไม่ใช่ causality
- daily breadth เป็น unweighted mean เฉพาะ themes ที่กล่าวถึง พร้อม coverage
- ตาราง `signals` ไม่ถูกอ่านหรือส่งขึ้น Dashboard และไม่ใช่ canonical Quant input
- snapshot เป็นไฟล์ disposable; แหล่งจริงยังเป็น `sentiment.db`

## ตรวจสอบงานพัฒนา

```powershell
npm run refresh
npm run test:data
npm test
```

`npm test` จะ build production bundle และตรวจ rendered page กับ dataset contract
