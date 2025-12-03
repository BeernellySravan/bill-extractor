# run_all_samples.py
import traceback
from src.ocr import load_document_images
from src.lineitem_extractor import extract_pagewise_line_items
from src.reconciler import reconcile_totals

documents = [
    r"file:///C:/Users/srava/Downloads/bill-extractor/sample_docs/Sample Document 1.pdf",
    r"file:///C:/Users/srava/Downloads/bill-extractor/sample_docs/Sample Document 2.pdf",
    r"file:///C:/Users/srava/Downloads/bill-extractor/sample_docs/Sample Document 3.pdf",
]

for doc in documents:
    print("\n===================================================")
    print("PROCESSING:", doc)
    print("===================================================\n")

    try:
        # 1) Load PDF pages
        pages = load_document_images(doc)
        print(f"Loaded {len(pages)} pages")

        page_items = []

        # 2) Extract line items page-wise
        for i, img in enumerate(pages, start=1):
            try:
                result = extract_pagewise_line_items(img, page_no=str(i))
                print(f" Page {i}: {len(result['bill_items'])} items extracted")
                page_items.append(result)
            except Exception as e:
                print(f" ❌ ERROR extracting page {i}")
                traceback.print_exc()

        # 3) Reconcile totals
        try:
            totals = reconcile_totals(page_items)
            print("\nFinal reconciled amount:", totals["reconciled_amount"])
        except Exception as e:
            print("❌ Error during reconcile_totals()")
            traceback.print_exc()

    except Exception as e:
        print("❌ ERROR processing document:", doc)
        traceback.print_exc()

print("\n\nALL DOCUMENTS PROCESSED.") 