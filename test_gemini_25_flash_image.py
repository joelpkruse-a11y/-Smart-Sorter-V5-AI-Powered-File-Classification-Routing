import sys
from google import genai
from PIL import Image

def main():
    print("\n=== Gemini 2.5 Flash Image Test ===\n")

    try:
        client = genai.Client()

        model_name = "models/gemini-2.5-flash-image"
        print(f"Using model: {model_name}\n")

        image_path = "test.jpg"
        print(f"Loading image: {image_path}")

        # Load image as PIL.Image
        img = Image.open(image_path)

        print("\nSending request to Gemini 2.5 Flash Image...\n")

        response = client.models.generate_content(
            model=model_name,
            contents=[
                "Describe this image and tell me if it looks like a document or a photo.",
                img
            ]
        )

        print("=== MODEL RESPONSE ===\n")
        print(response.text)

    except Exception as e:
        print("\n=== ERROR ===")
        print(type(e).__name__, str(e))
        sys.exit(1)

    print("\n=== Test Completed Successfully ===\n")


if __name__ == "__main__":
    main()