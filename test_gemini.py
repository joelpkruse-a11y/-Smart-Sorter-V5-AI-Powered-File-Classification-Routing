import os
import sys
import traceback

print("=======================================")
print("   GEMINI 2.5 PRO CONNECTIVITY TEST")
print("=======================================\n")

# 1. Check environment variable
api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    print("[FAIL] GEMINI_API_KEY is NOT set.")
    sys.exit(1)
else:
    print("[OK] GEMINI_API_KEY detected (length:", len(api_key), ")")

# 2. Import correct SDK
try:
    import google.genai as genai
    print("[OK] google.genai imported.")
except Exception as e:
    print("[FAIL] Could not import google.genai.")
    print(e)
    sys.exit(1)

# 3. Configure client
try:
    client = genai.Client(api_key=api_key)
    print("[OK] Gemini client configured.")
except Exception as e:
    print("[FAIL] Could not configure Gemini client.")
    print(e)
    sys.exit(1)

# 4. Test call using gemini‑2.5‑pro
try:
    response = client.models.generate_content(
        model="gemini-2.5-pro",
        contents="Respond with a short greeting."
    )
    print("[OK] Gemini 2.5 Pro responded.\n")
    print("Gemini Output:")
    print("---------------------------------------")
    print(response.text)
    print("---------------------------------------")

except Exception as e:
    print("[FAIL] Gemini 2.5 Pro API call failed.")
    print("Error:", e)
    traceback.print_exc()
    sys.exit(1)

print("\n=======================================")
print("   GEMINI 2.5 PRO TEST SUCCESSFUL")
print("=======================================")