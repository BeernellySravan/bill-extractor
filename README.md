# BILL EXTRACTOR API (HackRx)

This project extracts item-level information from **PDF bills/invoices**, including:
- item names  
- item rates  
- item quantities  
- item amounts  
- total item count  
- reconciled totals  

# Install Poppler (PDF → Image)

pdf2image requires Poppler binaries (pdfinfo, pdftoppm) to convert PDF pages into images.

A. Download & extract

Go to the Poppler Windows releases:
https://github.com/oschwartz10612/poppler-windows/releases

Download the latest zip (e.g. poppler-xx.zip) and extract it.

Recommended location (simple path, no spaces):

C:\poppler


After extraction you must have:

C:\poppler\Library\bin\pdfinfo.exe
C:\poppler\Library\bin\pdftoppm.exe

B. Add Poppler to PATH (so pdf2image can find it)

PowerShell (recommended):

$poppler = "C:\poppler\Library\bin"
$old = [Environment]::GetEnvironmentVariable("PATH","User")
if ($old -notlike "*$poppler*") {
  [Environment]::SetEnvironmentVariable("PATH", "$old;$poppler", "User")
  Write-Host "Added Poppler to PATH (User). Close & re-open terminal to apply."
} else {
  Write-Host "Poppler path already in PATH."
}


After running: close and re-open your terminal (or VS Code) so changes take effect.

Verify:

pdfinfo --version
pdftoppm -v
# or use the full path if commands are not recognized:
& "C:\poppler\Library\bin\pdfinfo.exe" --version


If these print version information, Poppler is ready.

Prepare Python virtual environment

Open PowerShell and run (from project root):

cd "C:\Users\srava\Downloads\bill-extractor"

# create venv
python -m venv .venv

# activate (PowerShell)
. .\.venv\Scripts\Activate.ps1


You should now see (.venv) in your prompt.

Install Python dependencies

If you have a requirements.txt file, run:

pip install --upgrade pip
pip install -r requirements.txt


If you don't have requirements.txt, install the common packages used in this project:

pip install fastapi uvicorn pdf2image pillow pytesseract opencv-python-headless python-multipart


Note: If using pytesseract, you also need Tesseract OCR binary installed (https://github.com/tesseract-ocr/tesseract
). If you rely on an external OCR provider you may not need pytesseract.

Configure environment variables (optional)

If you prefer to give the Poppler path explicitly to the app, set an environment variable:

PowerShell (session-only):

$env:POPPLER_PATH = "C:\poppler\Library\bin"


In Python you can pick it up:

import os
poppler_path = os.getenv("POPPLER_PATH", r"C:\poppler\Library\bin")
pages = convert_from_path("sample.pdf", poppler_path=poppler_path)

Run the FastAPI server locally

From the project root (and with .venv activated):

uvicorn app:app --reload --port 8000


Then open:

http://127.0.0.1:8000/docs


to see interactive Swagger UI.

Test the API

PowerShell / Windows NOTE: curl in PowerShell maps to Invoke-WebRequest. Use the following PowerShell-friendly curl:

curl -Method POST -Uri "http://127.0.0.1:8000/extract-bill-data" `
     -Body '{"document":"C:\\Users\\srava\\Downloads\\sample.pdf"}' `
     -ContentType "application/json"


Alternatively use Invoke-RestMethod or a GUI client such as Postman.

Example response (JSON):

{
  "is_success": true,
  "token_usage": {...},
  "data": {
    "pagewise_line_items": [ ... ],
    "total_item_count": 30,
    "reconciled_amount": 21800
  }
}

