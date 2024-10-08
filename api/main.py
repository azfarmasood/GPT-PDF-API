from io import BytesIO
from fastapi import FastAPI, HTTPException, Query, Request
from pdf2image import convert_from_path
from sqlmodel import SQLModel, Field, select
from fastapi.responses import JSONResponse, StreamingResponse
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path
from Database.db import create_tables
from Database.setting import DB_SESSION, sendername, senderemail, SMTP_PASSWORD
from fastapi.middleware.cors import CORSMiddleware
from typing import Deque, Optional, Dict, Any
from collections import deque
import logging
import os
import fitz  # type: ignore
import smtplib
# Configure logging
import pytesseract # type: ignore
import concurrent.futures

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    username: str
    email: str
    pdf_sent: str | None = None  # Field to store the PDF file name sent to the user


app = FastAPI(lifespan=create_tables)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust this to your frontend's domain for better security
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PDF_PATH = Path(__file__).parent / "pdfs" / "MANAPRODUCTLIST.pdf"  # Path to the PDF
in_memory_images: dict = {}


async def send_email_with_pdf(to_email: str, username: str):
    try:
        if not PDF_PATH.exists():
            raise HTTPException(status_code=404, detail="PDF file not found.")
        
        pdf_file_name = PDF_PATH.name
        
        msg = EmailMessage()
        msg['Subject'] = f'Your PDF file {pdf_file_name}'
        msg['From'] = formataddr((sendername, senderemail))
        msg['To'] = to_email
        msg.set_content(f"Hello {username},\n\nPlease find the requested PDF attached.")
        
        with open(PDF_PATH, 'rb') as f:
            pdf_data = f.read()
        msg.add_attachment(pdf_data, maintype='application', subtype='pdf', filename=pdf_file_name)

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(senderemail, SMTP_PASSWORD)
            smtp.send_message(msg)

        logger.info(f"Email sent successfully to {to_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    


@app.post("/send-pdf/")
async def send_pdf(username: str, email: str, session: DB_SESSION):
    result = User(username=username, email=email, pdf_sent=PDF_PATH.name)
    session.add(result)
    session.commit()
    session.refresh(result)
    
    email_sent = await send_email_with_pdf(email, username)
    if email_sent:
        return JSONResponse(content={"message": f"PDF file sent successfully to {email}"}, status_code=200)
    else:
        raise HTTPException(status_code=500, detail="Failed to send email")
    
MAX_IMAGES: int = 100 

image_ids: Deque[str] = deque(maxlen=MAX_IMAGES)

@app.get("/read-pdf-steps/", response_class=JSONResponse)
async def search_keyword(request: Request, keyword: str = Query(..., description="Keyword to search in the PDF")):
    if not os.path.exists(PDF_PATH):
        raise HTTPException(status_code=404, detail="PDF file not found.")

    try:
        doc = fitz.open(PDF_PATH)
        total_pages = len(doc)
        found_pages = []

        # Optimize by increasing the worker pool dynamically based on page count
        max_workers = min(8, total_pages // 2 + 1)  # Allow more workers for larger PDFs

        # Process each page concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(process_page, doc, page_num, keyword, request) for page_num in range(total_pages)]
            
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                if result:
                    found_pages.append(result)

        if found_pages:
            return JSONResponse(content=found_pages, status_code=200)
        else:
            raise HTTPException(status_code=404, detail="Keyword not found in the PDF.")
    
    except Exception as e:
        logger.error(f"Failed to search keyword in PDF: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to search keyword in PDF: {e}")


def process_page(doc, page_num: int, keyword: str, request: Request) -> Optional[Dict[str, Any]]:
    response_data: Dict[str, Any] = {"page_number": page_num + 1}
    page = doc.load_page(page_num)
    text = page.get_text("text").strip()

    # Process text on the page first
    if keyword.lower() in text.lower():
        response_data["text"] = text
        logger.info(f"Keyword found in text on page {page_num + 1}")

    # Process images and extract text from images
    images = convert_from_path(PDF_PATH, first_page=page_num + 1, last_page=page_num + 1)
    if images:
        img = images[0]
        img_io = BytesIO()
        img.save(img_io, format="PNG")
        img_io.seek(0)

        extracted_text_from_image = pytesseract.image_to_string(img)

        # Check if keyword exists in the extracted text from the image
        if keyword.lower() in extracted_text_from_image.lower():
            image_id = f"page_{page_num + 1}_image"
            in_memory_images[image_id] = {"image_io": img_io, "extension": "png"}
            image_ids.append(image_id)  # Track the order of image storage

            image_url: str = str(request.url_for("get_image", image_id=image_id))
            logger.info(f"Generated image_url: {image_url} (type: {type(image_url)})")

            response_data["image_url"] = image_url
            response_data["image_text"] = extracted_text_from_image
        else:
            logger.info(f"Keyword not found in image on page {page_num + 1}")
    else:
        logger.info(f"No images found on page {page_num + 1}")

    # Manage the memory to prevent overflow with too many images
    while len(image_ids) > MAX_IMAGES:
        oldest_id = image_ids.popleft()
        in_memory_images.pop(oldest_id, None)

    if "text" in response_data or "image_url" in response_data:
        return response_data

    return None



@app.get("/get-image/{image_id}", name="get_image")
async def get_image(image_id: str):
    image_info = in_memory_images.get(image_id)
    if image_info:
        image_io = image_info["image_io"]
        image_extension = image_info["extension"]
        image_io.seek(0)
        return StreamingResponse(image_io, media_type=f"image/{image_extension}")
    else:
        raise HTTPException(status_code=404, detail="Image not found.")


@app.get("/get-emails/")
def get_emails(session: DB_SESSION):
    return session.exec(select(User)).all()







# from io import BytesIO
# from fastapi import FastAPI, HTTPException, Query, Request
# from pdf2image import convert_from_bytes
# from sqlmodel import SQLModel, Field, select
# from fastapi.responses import JSONResponse, StreamingResponse
# from email.message import EmailMessage
# from email.utils import formataddr
# from pathlib import Path
# from Database.db import create_tables
# from Database.setting import DB_SESSION, sendername, senderemail, SMTP_PASSWORD
# from fastapi.middleware.cors import CORSMiddleware
# from typing import Deque, Optional, Dict, Any
# from collections import deque
# import logging
# import os
# import fitz  # type: ignore
# from smtplib import SMTP_SSL
# import pytesseract  # type: ignore
# import concurrent.futures
# import aiofiles # type: ignore
# import asyncio

# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)

# class User(SQLModel, table=True):
#     id: int | None = Field(default=None, primary_key=True)
#     username: str
#     email: str
#     pdf_sent: str | None = None

# app = FastAPI(lifespan=create_tables)

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# PDF_PATH = Path(__file__).parent / "pdfs" / "MANAPRODUCTLIST.pdf"
# in_memory_images: dict = {}

# async def send_email_with_pdf(to_email: str, username: str):
#     try:
#         if not PDF_PATH.exists():
#             raise HTTPException(status_code=404, detail="PDF file not found.")
        
#         pdf_file_name = PDF_PATH.name
        
#         msg = EmailMessage()
#         msg['Subject'] = f'Your PDF file {pdf_file_name}'
#         msg['From'] = formataddr((sendername, senderemail))
#         msg['To'] = to_email
#         msg.set_content(f"Hello {username},\n\nPlease find the requested PDF attached.")
        
#         async with aiofiles.open(PDF_PATH, 'rb') as f:
#             pdf_data = await f.read()
#         msg.add_attachment(pdf_data, maintype='application', subtype='pdf', filename=pdf_file_name)

#         with SMTP_SSL('smtp.gmail.com', 465) as smtp:
#              smtp.login(senderemail, SMTP_PASSWORD)
#              smtp.send_message(msg)

#         logger.info(f"Email sent successfully to {to_email}")
#         return True
#     except Exception as e:
#         logger.error(f"Failed to send email: {e}")
#         raise HTTPException(status_code=500, detail=str(e))

# @app.post("/send-pdf/")
# async def send_pdf(username: str, email: str, session: DB_SESSION):
#     result = User(username=username, email=email, pdf_sent=PDF_PATH.name)
#     session.add(result)
#     session.commit()
#     session.refresh(result)
    
#     email_sent = await send_email_with_pdf(email, username)
#     if email_sent:
#         return JSONResponse(content={"message": f"PDF file sent successfully to {email}"}, status_code=200)
#     else:
#         raise HTTPException(status_code=500, detail="Failed to send email")

# MAX_IMAGES: int = 100 
# image_ids: Deque[str] = deque(maxlen=MAX_IMAGES)

# @app.get("/read-pdf-steps/", response_class=JSONResponse)
# async def search_keyword(request: Request, keyword: str = Query(..., description="Keyword to search in the PDF")):
#     if not os.path.exists(PDF_PATH):
#         raise HTTPException(status_code=404, detail="PDF file not found.")

#     try:
#         async with aiofiles.open(PDF_PATH, 'rb') as f:
#             pdf_data = await f.read()
        
#         doc = fitz.open(stream=pdf_data, filetype="pdf")
#         total_pages = len(doc)
#         found_pages = []

#         max_workers = min(8, total_pages // 2 + 1)

#         with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
#             futures = [executor.submit(process_page, doc, page_num, keyword, request) for page_num in range(total_pages)]
            
#             for future in concurrent.futures.as_completed(futures):
#                 result = future.result()
#                 if result:
#                     found_pages.append(result)

#         if found_pages:
#             return JSONResponse(content=found_pages, status_code=200)
#         else:
#             raise HTTPException(status_code=404, detail="Keyword not found in the PDF.")
    
#     except Exception as e:
#         logger.error(f"Failed to search keyword in PDF: {e}")
#         raise HTTPException(status_code=500, detail=f"Failed to search keyword in PDF: {e}")

# def process_page(doc, page_num: int, keyword: str, request: Request) -> Optional[Dict[str, Any]]:
#     response_data: Dict[str, Any] = {"page_number": page_num + 1}
#     page = doc.load_page(page_num)
#     text = page.get_text("text").strip()

#     if keyword.lower() in text.lower():
#         response_data["text"] = text
#         logger.info(f"Keyword found in text on page {page_num + 1}")

#     images = convert_from_bytes(doc.write(), first_page=page_num + 1, last_page=page_num + 1)
#     if images:
#         img = images[0]
#         img_io = BytesIO()
#         img.save(img_io, format="PNG")
#         img_io.seek(0)

#         extracted_text_from_image = pytesseract.image_to_string(img)

#         if keyword.lower() in extracted_text_from_image.lower():
#             image_id = f"page_{page_num + 1}_image"
#             in_memory_images[image_id] = {"image_io": img_io, "extension": "png"}
#             image_ids.append(image_id)

#             image_url: str = str(request.url_for("get_image", image_id=image_id))
#             logger.info(f"Generated image_url: {image_url} (type: {type(image_url)})")

#             response_data["image_url"] = image_url
#             response_data["image_text"] = extracted_text_from_image
#         else:
#             logger.info(f"Keyword not found in image on page {page_num + 1}")
#     else:
#         logger.info(f"No images found on page {page_num + 1}")

#     while len(image_ids) > MAX_IMAGES:
#         oldest_id = image_ids.popleft()
#         in_memory_images.pop(oldest_id, None)

#     if "text" in response_data or "image_url" in response_data:
#         return response_data

#     return None

# @app.get("/get-image/{image_id}", name="get_image")
# async def get_image(image_id: str):
#     image_info = in_memory_images.get(image_id)
#     if image_info:
#         image_io = image_info["image_io"]
#         image_extension = image_info["extension"]
#         image_io.seek(0)
#         return StreamingResponse(image_io, media_type=f"image/{image_extension}")
#     else:
#         raise HTTPException(status_code=404, detail="Image not found.")

# @app.get("/get-emails/")
# def get_emails(session: DB_SESSION):
#     return session.exec(select(User)).all()
