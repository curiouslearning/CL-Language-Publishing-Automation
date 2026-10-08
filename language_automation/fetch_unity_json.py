import requests
import json
import sys
import os

def fetch_and_save_json(url, output_path):
    """
    Fetch JSON from a URL, format it, and save to the specified path.
    
    Args:
        url (str): The Unity URL returning JSON.
        output_path (str): Path to save the formatted JSON.
    """
    # The URL comes from a sheet cell anyone with edit access can change
    if not str(url).lower().startswith("https://"):
        print(f"❌ Refusing non-https content URL: {url}")
        return False

    try:
        response = requests.get(url, timeout=(10, 300))
        response.raise_for_status()  # Raise exception for HTTP errors

        # Parse JSON
        data = response.json()

        # Pretty-print / format JSON
        formatted_json = json.dumps(data, indent=4, ensure_ascii=False)

        # Ensure the directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Save to file
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(formatted_json)

        print(f"✅ JSON fetched and saved to {output_path}")
        return data

    except requests.exceptions.RequestException as e:
        print(f"❌ Failed to fetch JSON: {e}")
        return False
    except json.JSONDecodeError as e:
        print(f"❌ Response is not valid JSON: {e}")
        return False


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python fetch_unity_json.py <UNITY_URL> <OUTPUT_PATH>")
        print("Example: python fetch_unity_json.py 'https://.../hello-world?sheet=XYZ' './output/data.json'")
        sys.exit(1)

    unity_url = sys.argv[1]
    output_file = sys.argv[2]

    fetch_and_save_json(unity_url, output_file)
