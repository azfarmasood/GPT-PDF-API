from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from pathlib import Path

def generate_pdf(username: str, product_list: list) -> str:
    pdf_dir = Path("./pdfs/")
    pdf_dir.mkdir(parents=True, exist_ok=True)

    pdf_path = pdf_dir / "Translated_copy_of_translatework123.pdf"
    c = canvas.Canvas(str(pdf_path), pagesize=letter)
    
    # Title
    c.setFont("Helvetica", 20)
    c.drawString(100, 750, f"Hello {username}, Here is your Product List")

    # Product List
    y_position = 720
    c.setFont("Helvetica", 12)
    for product in product_list:
        c.drawString(100, y_position, f"- {product}")
        y_position -= 20  # Move down for the next product

    c.save()

    return str(pdf_path)
