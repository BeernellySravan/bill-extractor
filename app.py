from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import traceback

from src.ocr import load_document_images
from src.lineitem_extractor import extract_pagewise_line_items
from src.reconciler import reconcile_totals
from src.utils import token_usage_stub

app = FastAPI(title="Bill Extraction API")

class ExtractRequest(BaseModel):
    document: str


@app.post("/extract-bill-data")
async def extract_bill_data(req: ExtractRequest):
    try:
        # Load all pages as images
        pages = load_document_images(req.document)

        pagewise_results = []
        total_items = 0

        # Extract line items from each page
        for index, img in enumerate(pages, start=1):
            page_result = extract_pagewise_line_items(img, str(index))
            pagewise_results.append(page_result)
            total_items += len(page_result["bill_items"])

        # Reconcile totals from all pages
        totals = reconcile_totals(pagewise_results)

        return {
            "is_success": True,
            "token_usage": token_usage_stub(),
            "data": {
                "pagewise_line_items": pagewise_results,
                "total_item_count": total_items,
                **totals
            }
        }

    except Exception as e:
        # Print full traceback to console
        tb = traceback.format_exc()
        print("\n===== INTERNAL SERVER ERROR TRACEBACK =====")
        print(tb)
        print("===========================================\n")

        # Return full traceback in response (for debugging)
        return JSONResponse(
            status_code=500,
            content={
                "error": str(e),
                "trace": tb
            }
        )
