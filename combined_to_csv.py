import requests
import csv
import os
import sys
import csv
import asyncio
import aiohttp

API_TOKEN = '{YOUR API TOKEN}'
BASE_URL = 'https://api.bigcommerce.com/stores/l85bzww3lo'
HEADERS = {
    'X-Auth-Token': API_TOKEN,
    'Content-Type': 'application/json'
}

def fetch_product_ids():
    product_ids = []
    page = 1
    limit = 250
    base_endpoint = f"{BASE_URL}/v3/catalog/products?limit={limit}&is_visible=true"
    excluded_keywords = ["i agree to the terms and conditions", "yes, send me information to book a tasker", "test", "tests", "delete", "discontinued", "bundle", "copy"]

    while True:
        response = requests.get(base_endpoint + f"&page={page}", headers=HEADERS)
        if response.status_code == 200:
            data = response.json()
            products = data.get('data', [])
            for product in products:
                product_name_lower = product['name'].lower()
                if product['is_visible'] and not any(keyword in product_name_lower for keyword in excluded_keywords):
                    product_ids.append({
                        'id': product['id'],
                        'name': product['name'],
                        'url': product['custom_url']['url'], 
                        'sku': product['sku'],
                        'type': 'product'
                    })
            
            # Check if we have more pages
            pagination = data.get('meta', {}).get('pagination', {})
            total_pages = pagination.get('total_pages', 0)
            print(f"Page {page} of {total_pages} filtered")
            if page >= total_pages:
                break
            page += 1
        else:
            print(f"Failed to fetch products: {response.status_code}")
            break

    return product_ids
  
async def fetch_custom_fields_for_product(session, product_id):
    """Fetch specific custom fields for a single product, focusing on 'builder_type' or 'Desk Builder'."""
    url = f"{BASE_URL}/v3/catalog/products/{product_id}/custom-fields"
    try:
        async with session.get(url, headers=HEADERS) as response:
            if response.status == 200:
                response_data = await response.json()
                custom_fields = response_data.get('data', [])
                
                # Looking for specific custom fields by name
                for field in custom_fields:
                    if field['name'] in ['builder_type', 'Desk Builder']:
                        # Return the first matching custom field
                        return product_id, {field['name']: field['value']}
                
                # If no matching custom fields are found, return a default message
                return product_id, {"builder_type": "BUILDER NOT FOUND"}
                
            elif response.status == 429:
                retry_after = int(response.headers.get("Retry-After", 1))
                await asyncio.sleep(retry_after)
                return await fetch_custom_fields_for_product(session, product_id)
            else:
                return product_id, {"builder_type": "BUILDER NOT FOUND"}
    except Exception as e:
        return product_id, {"builder_type": "BUILDER NOT FOUND"}


async def fetch_custom_fields_for_chunk(session, chunk):
    #Fetch custom fields for a chunk of products.
    tasks = [fetch_custom_fields_for_product(session, product['id']) for product in chunk]
    return await asyncio.gather(*tasks, return_exceptions=True)

async def fetch_custom_fields_for_products(product_ids, chunk_size=20):
    #Fetch custom fields for a list of products asynchronously, in batches.
    async with aiohttp.ClientSession() as session:
        # chunk them out or else you get lots of 429s
        chunks = [product_ids[i:i + chunk_size] for i in range(0, len(product_ids), chunk_size)]
        custom_fields_dict = {}
        total_chunks = len(chunks)
        for i, chunk in enumerate(chunks, start=1):
            print(f"Calling API for Custom Fields: Chunk {i} of {total_chunks}")
            results = await fetch_custom_fields_for_chunk(session, chunk)
            for product_id, custom_fields in results:
                if not isinstance(custom_fields, Exception):
                    custom_fields_dict[product_id] = custom_fields
        return custom_fields_dict
           
def fetch_page_ids():
    page_ids = []
    page = 1
    limit = 250 
    endpoint = f"{BASE_URL}/v3/content/pages?limit={limit}"

    while True:
        response = requests.get(f"{endpoint}&page={page}", headers=HEADERS)
        if response.status_code == 200:
            data = response.json()
            website_pages = data.get('data', [])
            for website_page in website_pages:
                if website_page['is_visible'] and (website_page['type'] == 'page'):
                    page_ids.append({
                        'id': website_page['id'],
                        'name': website_page['name'],
                        'url': website_page['url'],
                        'type': 'page'
                    })

            # Pagination handling
            pagination = data.get('meta', {}).get('pagination', {})
            total_pages = pagination.get('total_pages', 0)
            print(f"Page {page} of {total_pages} filtered")
            if page >= total_pages:
                break
            page += 1
        else:
            print(f"Error fetching pages: {response.status_code}")
            break

    return page_ids            
            
def fetch_custom_template_associations():
    custom_templates = []
    page = 1
    limit = 250
    endpoint = f"{BASE_URL}/v3/storefront/custom-template-associations?limit={limit}"

    while True:
        response = requests.get(f"{endpoint}&page={page}", headers=HEADERS)
        if response.status_code == 200:
            data = response.json()
            associations = data.get('data', [])
            for association in associations:
                custom_templates.append({
                    'type': association['entity_type'],
                    'id': association['entity_id'],
                    'file_name': association['file_name']
                })

            # Pagination handling
            pagination = data.get('meta', {}).get('pagination', {})
            total_pages = pagination.get('total_pages', 0)
            print(f"Page {page} of {total_pages} filtered")
            if page >= total_pages:
                break
            page += 1
        else:
            print(f"Error fetchin' custom template associations: {response.status_code}")
            break

    return custom_templates

async def integrate_custom_fields():
    print(f"Grabbin' product_ids")
    product_ids = fetch_product_ids()
    print(f"Grabbin' custom fields")
    custom_fields = await fetch_custom_fields_for_products(product_ids)
    print(f"Grabbin' page_ids")
    page_ids = fetch_page_ids()
    print(f"Grabbin' custom_templates")
    custom_templates = fetch_custom_template_associations()

    combined_ids = product_ids + page_ids

    
    print(f"Finding custom fields for each product type. . .")
    for item in combined_ids:
        item_id = item['id']
        item_type = item.get('type', 'unknown')
        item['custom_fields'] = custom_fields.get(item_id, "No custom field")

        matching_templates = [template for template in custom_templates if template['id'] == item_id and template['type'] == item_type]
        if matching_templates:
            template = matching_templates[0]
            item['template_file_name'] = template['file_name']
        else:
            item['template_file_name'] = "No template found"

    return combined_ids

def get_downloads_path():
    """Returns the default downloads path for Linux, macOS, and Windows."""
    if sys.platform == "win32":
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders") as key:
            downloads_path = winreg.QueryValueEx(key, "{374DE290-123F-4565-9164-39C4925E467B}")[0]
    elif sys.platform == "darwin":
        downloads_path = os.path.join(os.path.expanduser('~'), 'Downloads')
    else:
        downloads_path = os.path.join(os.path.expanduser('~'), 'Downloads')
    return downloads_path

def write_to_csv(data, filename, fieldnames):
    """Write data to a CSV file in the user's downloads directory."""
    downloads_path = get_downloads_path()
    full_path = os.path.join(downloads_path, filename)
    print(f"Printing {filename} to {downloads_path}")

    with open(full_path, mode='w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for row in data:
            writer.writerow(row)


async def main():
    integrated_data = await integrate_custom_fields()

    # Define fieldnames for the CSV
    fieldnames = ['id', 'name', 'url', 'sku', 'type', 'custom_fields', 'template_file_name']

    # Write the integrated data to a single CSV
    write_to_csv(integrated_data, 'combined_products_and_pages.csv', fieldnames)

if __name__ == "__main__":
    asyncio.run(main())


