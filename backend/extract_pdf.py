from langchain_core.messages import HumanMessage, BaseMessage
from langchain_core.runnables import RunnableLambda
import base64
from docx2pdf import convert # For converting .docx to .pdf
import os
from dotenv import load_dotenv
from langchain_openai import AzureChatOpenAI
import json
import json
import os
import fitz  # PyMuPDF for PDF handling
from PIL import Image # For image processing





load_dotenv()

os.environ["AZURE_OPENAI_API_KEY"] = os.getenv("AZURE_OPENAI_API_KEY")
os.environ["AZURE_OPENAI_ENDPOINT"] = os.getenv("AZURE_OPENAI_ENDPOINT")
os.environ["AZURE_OPENAI_API_TYPE"] = os.getenv("AZURE_OPENAI_API_TYPE")
os.environ["OPENAI_API_Version"] = os.getenv("OPENAI_API_Version")


# Function to convert PDF to images for text extraction
def pdf_to_image(pdf_path, output_folder, quality=85, dpi=150):
    doc_list = []
    pdf_file = fitz.open(pdf_path)

    # Precompute zoom for better quality image conversion
    zoom = dpi / 72
    mat = fitz.Matrix(zoom, zoom)

    # Loop through each page in the PDF file using the length of the PDF document as the range
    for page_num in range(len(pdf_file)):
        # Load the current page from the PDF using its number
        page = pdf_file.load_page(page_num)
        # Get the pixmap (raster image) of the page with a predefined matrix for zoom level
        # This matrix (mat) was set outside of this loop for efficiency
        pix = page.get_pixmap(matrix=mat)
        # Convert the pixmap into a PIL Image object
        # "RGB" indicates that the image will be in color, pix.width and pix.height get the image dimensions
        # pix.samples is the raw pixel data from the pixmap
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        # Construct the file path where the image of the page will be saved
        # os.path.basename(pdf_path).split('.pdf')[0] extracts the PDF filename without extension
        # Adding _page_{page_num+1} to indicate which page from the PDF this image represents
        output_path = os.path.join(output_folder, f"{os.path.basename(pdf_path).split('.pdf')[0]}_page_{page_num+1}.jpg")
        # Save the image to the specified path as a JPEG file
        # "JPEG" specifies the file format, quality=quality sets the image quality (set earlier)
        # optimize=True compresses the image further for storage efficiency
        img.save(output_path, "JPEG", quality=quality, optimize=True)
        # Add the path of the saved image to a list, so we can keep track of or further process these images
        doc_list.append(output_path)

    pdf_file.close()
    print("PDF to image conversion complete.")
    return doc_list

llm=AzureChatOpenAI(temperature=0,deployment_name=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),model_name=os.getenv("MODEL_NAME"))

prompt = """"
Extract the text from the image below and return the entire text alone in a json format without ```json or \n.
Do not prefix any numbers used as serial number. If the key is multiple words, use underscore to separate the words.
If the key is a checkbox, use the key as the key and the value as yes if checked and no if not checked.
If the key is a radio button, use the key as the key and the value as the selected option.
Tricare and Champus are 2 different checkboxes.
Extract all keys and values from the image. If a value is not present, use an empty string as the value.
dates_of_service_from, dates_of_service_to, place_of_service, emg, cpt_hcpcs, modifier, diagnosis_pointer, charges, days_in_units, id_qual and rendering_provider_id should be within a single nested json called service. It should include all other values in that row.
Extract Service facility location information and Billing provider Info & ph# as Nested JSON
If a checkbox is not checked use empty string as the value.
If a radio button is not selected, use empty string as the value.
All dates should be in the format MM-DD-YYYY. They include insured_date_of_birth, patient_date_of_birth, dates_of_service_from, dates_of_service_to.
patient_relationship_to_insured should be either self, spouse, child or other.
patient_sex should be either M or F.
insured_policy_grp_feca_no can be in format digit-digit
Insured City, state, zip code, and telephone should be separate from patient City, state, zip code, and telephone information.
The checkbox for insurance providers are below them preceeding the text. Mark yes only if the checkbox is checked.
Mandatorily add insurance_plan_name_or_program_name key in JSON.
For example

Example 1:

    MEDICARE      MEDICAID     TRICARE      CHAPUS        GROUP          FECA       OTHER
                                                          HEALTH PLAN    BILLING
  ☐(Medicare#) ☐(Medicare#) ☐(ID#/DOD##) ☐(MemberID#) ☒(ID#)        ☐(ID#)    ☐(ID#)

which means 

'insurance_provider': {'medicare': '', 'medicaid': '', 'tricare': '', 'champus': '', 'group_health_plan': 'yes', 'feca': '', 'other': ''}

Also add the procedure details for the CPT/HCPCS code extracted from the document in services section. Do not leave the procedure details empty.
For example:
"service": [
        {"dates_of_service_from": "01-01-2022", "dates_of_service_to": "01-01-2022", "place_of_service": "01", "emg": "no", "cpt_hcpcs": "99213", "modifier": "25", "diagnosis_pointer": "A", "charges": "100", "days_in_units": "1", "id_qual": "DN", "rendering_provider_id": "1234567890", "procedure_details": "Office or other outpatient visit for the evaluation and management of an established patient, which requires at least 2 of these 3 key components: An expanded problem focused history; An expanded problem focused examination; Medical decision making of low complexity."}
        {"dates_of_service_from": "01-01-2022", "dates_of_service_to": "01-01-2022", "place_of_service": "01", "emg": "no", "cpt_hcpcs": "99214", "modifier": "25", "diagnosis_pointer": "A", "charges": "100", "days_in_units": "1", "id_qual": "DN", "rendering_provider_id": "1234567890", "procedure_details": "Office or other outpatient visit for the evaluation and management of an established patient, which requires at least 2 of these 3 key components: A detailed history; A detailed examination; Medical decision making of moderate complexity."}
        {"dates_of_service_from": "01-01-2022", "dates_of_service_to": "01-01-2022", "place_of_service": "01", "emg": "no", "cpt_hcpcs": "66984", "modifier": "LT", "diagnosis_pointer": "A", "charges": "100", "days_in_units": "1", "id_qual": "DN", "rendering_provider_id": "1234567890", "procedure_details": "Cataract surgery with intraocular lens prosthesis insertion."}
    ]
For diagnosis_or_nature_of_illness_or_injury add the description as well in text format. 
The nested json should look like this:
"diagnosis_or_nature_of_illness_or_injury": [
        {"Code":"E66.01", "desc":"Morbid (severe) obesity due to excess calories"},
        {"Code":"E66.9", "desc":"Obesity, unspecified"},
        {"Code":"Z68.30", "desc":"Body mass index (BMI) 19 or less, adult"}
    ],

"""
# Function to encode image to base64 for embedding in message
def encode_image(path):
    with open(path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

# Function to create message with image URL for LLM
def _get_message_url(url: str) -> list[BaseMessage]:
    return [
        HumanMessage(
            content=[
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encode_image(url)}"}},
            ],
        ),
    ]

def extract_pdf_agent(pdf_path):
    chain = RunnableLambda(_get_message_url) | llm
    # File path for the PDF document
    path = pdf_path
    output_folder = ""  # Folder to store images, left empty for current directory
    # Convert .doc or .docx to PDF if necessary
    if "doc" in path:
        convert(path)
        path = path.split(".doc")[0] + ".pdf"
    markdown_text = ""  # Will store all extracted text
    doc_list = pdf_to_image(path, output_folder, quality=50, dpi=100)  # Lower quality for speed
    counter = 0
    for doc in doc_list:
        counter += 1
        if counter == 1:  # Process only the 6th page for this example, adjust as needed
            response = chain.invoke(doc)
            if response:
                # Prepend page number to the extracted content
                #page_header = f"## Page Number {counter}\n"
                content = response.content
                #markdown_text += page_header + content + "\n"
                claim_with_proc = json.loads(content)
                
    return claim_with_proc

# Example usage
if __name__ == "__main__":
    pdf_path = "..\BariatricSurgeryClaims.pdf"  # Replace with the path to your PDF file
    fields = extract_pdf_agent(pdf_path)

    # Print extracted fields
    print(json.dumps(fields, indent=4))