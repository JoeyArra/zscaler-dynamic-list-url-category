import requests
from urllib.parse import urlparse
import json
import csv
import io
import warnings
import datetime
import os
import sys
from dotenv import load_dotenv

# Load environment variables from a .env file
load_dotenv()

# --- Configuration and Credentials (Loaded from Environment) ---
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
VANITY_DOMAIN = os.getenv("VANITY_DOMAIN")
ZIA_BASE_URL = os.getenv("ZIA_BASE_URL", "https://api.zsapi.net/zia/api/v1")
CATEGORY_NAME = os.getenv("CATEGORY_NAME")
SUPER_CATEGORY = os.getenv("SUPER_CATEGORY", "USER_DEFINED")

# --- SOURCE CONFIGURATION (Loaded from Environment) ---
URL_LIST_SOURCE = os.getenv("URL_LIST_SOURCE")
SOURCE_FORMAT = os.getenv("SOURCE_FORMAT", "auto")
JSON_URL_KEY = os.getenv("JSON_URL_KEY", "url")
# Load CSV_URL_COLUMN and cast to integer with a default
try:
    CSV_URL_COLUMN = int(os.getenv("CSV_URL_COLUMN", "0"))
except ValueError:
    print("Error: Invalid CSV_URL_COLUMN in .env file. It must be a number. Using default 0.")
    CSV_URL_COLUMN = 0

# --- Validate that critical environment variables are set ---
CRITICAL_VARS = ["CLIENT_ID", "CLIENT_SECRET", "VANITY_DOMAIN", "CATEGORY_NAME", "URL_LIST_SOURCE"]
missing_vars = [var for var in CRITICAL_VARS if not globals()[var]]
if missing_vars:
    print(f"Error: Missing critical environment variables: {', '.join(missing_vars)}")
    print("Please ensure they are set in your .env file or system environment.")
    sys.exit(1)


# --- URL Processing and Formatting Functions ---

def is_valid_for_api(url):
    """Validates if a string is a domain, IP, or full URL."""
    try:
        url_str = str(url)
        if '://' not in url_str:
            url_str = '//' + url_str
        parsed = urlparse(url_str)
        if parsed.netloc and '.' in parsed.netloc:
            return True
        return False
    except (ValueError, AttributeError):
        return False

def format_url_for_api(url):
    """Strips the scheme and returns the clean URL for the Zscaler API."""
    url_str = str(url)
    if '://' not in url_str:
        url_str = '//' + url_str
    parsed = urlparse(url_str)
    clean_url = parsed.netloc
    if parsed.path and parsed.path != '/':
        clean_url += parsed.path
    if parsed.query:
        clean_url += '?' + parsed.query
    if parsed.fragment:
        clean_url += '#' + parsed.fragment
    return clean_url


# --- Zscaler API Functions ---

def get_access_token(vanity_domain, client_id, client_secret):
    token_url = f"https://{vanity_domain}.zslogin.net/oauth2/v1/token"
    payload = {"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret, "audience": "https://api.zscaler.com"}
    response = requests.post(token_url, data=payload)
    if response.status_code == 200:
        print("Access Token successfully retrieved.")
        return response.json()["access_token"]
    else:
        print(f"Failed to fetch token: {response.status_code} - {response.text}")
        return None

# --- NEW DATA PARSING FUNCTIONS ---

def _parse_txt(response_text):
    """Parses a plain text response, one URL per line."""
    return [url.strip() for url in response_text.splitlines() if url.strip()]

def _parse_json(response, target_key='url'):
    """
    Parses any JSON structure to find all values associated with a specific target key.
    This version can handle:
    1. A simple list of URL strings.
    2. A key pointing to a single URL string (e.g., {"url": "..."}).
    3. A key pointing to a list of URL strings (e.g., {"prefixes": [...]}).
    """
    try:
        data = response.json()
    except json.JSONDecodeError:
        print(f"Error: Failed to decode JSON from the response.")
        return []

    if isinstance(data, list) and all(isinstance(item, str) for item in data):
        print("Detected simple list of URLs in JSON.")
        return data

    urls_found = []
    def _find_urls_recursively(json_part):
        if isinstance(json_part, dict):
            for key, value in json_part.items():
                if key == target_key:
                    if isinstance(value, str):
                        urls_found.append(value)
                    elif isinstance(value, list) and all(isinstance(i, str) for i in value):
                        urls_found.extend(value)
                    else:
                        _find_urls_recursively(value)
                else:
                    _find_urls_recursively(value)
        elif isinstance(json_part, list):
            for item in json_part:
                _find_urls_recursively(item)

    _find_urls_recursively(data)
    return list(dict.fromkeys(urls_found))

def _parse_csv(response_text, column_index):
    """Parses a CSV response to extract URLs from a specific column, ignoring commented lines."""
    urls = []
    filtered_lines = [line for line in response_text.splitlines() if not line.strip().startswith('#')]
    
    if not filtered_lines:
        print("Warning: CSV file contained only header/comment lines or was empty.")
        return []

    csv_file_data = "\n".join(filtered_lines)
    csv_file = io.StringIO(csv_file_data)
    reader = csv.reader(csv_file)
    
    for row_num, row in enumerate(reader, 1):
        if not row: continue
        try:
            urls.append(row[column_index].strip())
        except IndexError:
            print(f"Warning: Skipping row {row_num}. Column index {column_index} is out of bounds for row: {row}")
    return urls

def fetch_url_list(url_source, source_format='auto', json_key='url', csv_column=0):
    """
    Fetches and parses a list of URLs from a given source based on the specified format.
    """
    try:
        response = requests.get(url_source)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Failed to fetch URL list: {e}")
        return []

    if source_format == 'auto':
        content_type = response.headers.get('Content-Type', '').lower()
        if 'json' in content_type:
            detected_format = 'json'
        elif 'csv' in content_type or url_source.lower().endswith('.csv'):
            detected_format = 'csv'
        else:
            detected_format = 'txt'
        print(f"Auto-detected source format as: '{detected_format}'")
    else:
        detected_format = source_format

    if detected_format == 'json':
        url_list = _parse_json(response, target_key=json_key)
    elif detected_format == 'csv':
        url_list = _parse_csv(response.text, csv_column)
    elif detected_format == 'txt':
        url_list = _parse_txt(response.text)
    else:
        print(f"Error: Unsupported source format '{detected_format}'.")
        return []

    print(f"Successfully fetched and parsed {len(url_list)} URLs from the external list.")
    return url_list

# --- Category Management Functions ---

def get_category_details(base_url, access_token, category_name):
    print(f"Searching for existing URL Category: '{category_name}'...")
    endpoint = f"{base_url}/urlCategories"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    params = {'search': category_name}

    response = requests.get(endpoint, headers=headers, params=params)
    if response.status_code != 200:
        print(f"Warning: Could not search for categories. Status: {response.status_code} - {response.text}")
        return None
        
    categories = response.json()
    for category in categories:
        if category.get("configuredName") == category_name:
            print(f"Found existing category with ID: {category['id']}")
            return category
            
    print("No existing category found with that name.")
    return None

def update_url_category(base_url, access_token, category_id, category_name, urls, super_category):
    endpoint = f"{base_url}/urlCategories/{category_id}"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    payload = {"configuredName": category_name, "superCategory": super_category, "urls": urls, "customCategory": True}
    response = requests.put(endpoint, headers=headers, data=json.dumps(payload))
    
    if response.status_code == 200:
        print(f"API call successful. Category '{category_name}' has been updated.")
    else:
        print(f"Failed to update URL Category: {response.status_code} - {response.text}")

def create_url_category(base_url, access_token, category_name, urls, super_category):
    endpoint = f"{base_url}/urlCategories"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    payload = {"configuredName": category_name, "superCategory": super_category, "urls": urls, "customCategory": True}
    response = requests.post(endpoint, headers=headers, data=json.dumps(payload))
    if response.status_code in [200, 201]:
        print(f"API call successful. Category '{category_name}' has been created.")
    else:
        print(f"Failed to create URL Category: {response.status_code} - {response.text}")

def activate_changes(base_url, access_token):
    endpoint = f"{base_url}/status/activate"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    response = requests.post(endpoint, headers=headers)
    if response.status_code == 200:
        print("Activation successfully completed.")
    else:
        print(f"Failed to activate changes: {response.status_code} - {response.text}")


def main():
    run_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"Starting ZScaler URL Category Configuration at: {run_time}")
    
    access_token = get_access_token(VANITY_DOMAIN, CLIENT_ID, CLIENT_SECRET)
    if not access_token: return
    
    url_list = fetch_url_list(
        URL_LIST_SOURCE, 
        SOURCE_FORMAT, 
        json_key=JSON_URL_KEY,
        csv_column=CSV_URL_COLUMN
    )
    if not url_list: return
    
    new_formatted_urls = [format_url_for_api(url) for url in url_list if is_valid_for_api(url)]
    
    print(f"{len(new_formatted_urls)} valid and formatted URLs prepared from {len(url_list)} total entries.")
    if not new_formatted_urls:
        print("No valid URLs to process. Aborting.")
        return
    
    needs_activation = False
    category_details = get_category_details(ZIA_BASE_URL, access_token, CATEGORY_NAME)
    
    if category_details:
        print("Comparing remote list with the current Zscaler category list...")
        current_urls_in_zscaler = set(category_details.get('urls', []))
        new_urls_from_source = set(new_formatted_urls)

        if current_urls_in_zscaler == new_urls_from_source:
            print("No changes detected. The URL category is already up-to-date.")
        else:
            added_urls = new_urls_from_source - current_urls_in_zscaler
            removed_urls = current_urls_in_zscaler - new_urls_from_source
            print(f"Differences found: Adding {len(added_urls)} new URL(s), removing {len(removed_urls)} old one(s).")
            update_url_category(ZIA_BASE_URL, access_token, category_details['id'], CATEGORY_NAME, list(new_urls_from_source), SUPER_CATEGORY)
            needs_activation = True
    else:
        print(f"Creating a new URL category with {len(new_formatted_urls)} URL(s).")
        create_url_category(ZIA_BASE_URL, access_token, CATEGORY_NAME, new_formatted_urls, SUPER_CATEGORY)
        needs_activation = True
    
    if needs_activation:
        print("Activating configuration changes...")
        activate_changes(ZIA_BASE_URL, access_token)
    else:
        print("No activation needed.")
    
    print("Process completed.")


if __name__ == "__main__":
    main()