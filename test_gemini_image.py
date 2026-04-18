import os
from google.cloud import aiplatform
import vertexai
from vertexai.preview.generative_models import GenerativeModel, Image

# ------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------

PROJECT_ID = "cloud-sorter"          # your project ID
LOCATION = "us-central1"             # required for Gemini 3.x
IMAGE_PATH = r"C:\SmartInboxLocal\Photos\8567e57d-8398-4ebd-91de-f52e2b3775e5-1_all_2006.jpg"

# Model Garden ID (correct for Vertex AI SDK)
MODEL_NAME = "gemini-3.1-flash-image-preview"

# Full resource name (optional alternative)
# MODEL_NAME = (
#     "projects/cloud-sorter/locations/us-central1/"
#     "publishers/google/models/gemini-3.1-flash-image-preview"
# )

# ------------------------------------------------------------
# MAIN TEST HARNESS
# ------------------------------------------------------------

def main():
    print("\n=== Gemini 3.x Image Preview Test Harness ===\n")

    # --------------------------------------------------------
    # 1. Validate credentials
    # --------------------------------------------------------
    creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not creds:
        print("ERROR: GOOGLE_APPLICATION_CREDENTIALS is not set.")
        return
    if not os.path.exists(creds):
        print(f"ERROR: Credential file not found: {creds}")
        return

    print(f"Using credentials: {creds}")
    print(f"Testing model: {MODEL_NAME}")
    print(f"Loading image: {IMAGE_PATH}")

    # --------------------------------------------------------
    # 2. Initialize Vertex AI
    # --------------------------------------------------------
    try:
        vertexai.init(project=PROJECT_ID, location=LOCATION)
        print("Vertex AI initialized successfully.")
    except Exception as e:
        print(f"ERROR initializing Vertex AI: {e}")
        return

    # --------------------------------------------------------
    # 3. Load model
    # --------------------------------------------------------
    try:
        model = GenerativeModel(MODEL_NAME)
        print("Model loaded successfully.")
    except Exception as e:
        print(f"ERROR loading model: {e}")
        return

    # --------------------------------------------------------
    # 4. Load image
    # --------------------------------------------------------
    try:
        img = Image.load_from_file(IMAGE_PATH)
        print("Image loaded successfully.")
    except Exception as e:
        print(f"ERROR loading image: {e}")
        return

    # --------------------------------------------------------
    # 5. Run inference
    # --------------------------------------------------------
    print("\nSending request to Gemini...\n")
    try:
        response = model.generate_content(
            [
                img,
                "Describe this image and tell me if it appears to be a document photo."
            ]
        )
        print("=== MODEL RESPONSE ===")
        print(response.text)
        print("======================")
    except Exception as e:
        print(f"ERROR during model inference: {e}")


if __name__ == "__main__":
    main()