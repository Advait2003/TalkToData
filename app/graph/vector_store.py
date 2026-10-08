import os
from langchain_core.documents import Document
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_chroma import Chroma

CHROMA_PATH = "./chroma_db"

def get_vector_store():
    """Initializes and returns the Chroma vector store with Google embeddings."""
    embeddings = GoogleGenerativeAIEmbeddings(model="models/text-embedding-004")
    return Chroma(persist_directory=CHROMA_PATH, embedding_function=embeddings)

def init_schema_db():
    tables_metadata = [
        Document(
            page_content="Table: customer. Columns: customer_id, first_name, last_name, company, address, city, state, country, postal_code, phone, fax, email, support_rep_id. Contains buyer account details.",
            metadata={"table_name": "customer"}
        ),
        Document(
            page_content="Table: invoice. Columns: invoice_id, customer_id, invoice_date, billing_address, billing_city, billing_state, billing_country, billing_postal_code, total. Tracks purchases made by customers.",
            metadata={"table_name": "invoice"}
        ),
        Document(
            page_content="Table: track. Columns: track_id, name, album_id, media_type_id, genre_id, composer, milliseconds, bytes, unit_price. Contains details about individual songs and audio tracks.",
            metadata={"table_name": "track"}
        ),
        Document(
            page_content="Table: employee. Columns: employee_id, last_name, first_name, title, reports_to, birth_date, hire_date, address, city, state, country, postal_code, phone, fax, email. Company internal staff hierarchy and support reps.",
            metadata={"table_name": "employee"}
        )
    ]
    
    embeddings = GoogleGenerativeAIEmbeddings(model="models/text-embedding-004")
    vectorstore = Chroma.from_documents(
        documents=tables_metadata,
        embedding=embeddings,
        persist_directory=CHROMA_PATH
    )
    print("Schema vector database initialized successfully with Google embeddings.")

if __name__ == "__main__":
    init_schema_db()