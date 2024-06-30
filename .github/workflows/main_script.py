import subprocess
import sys
import os
import json
import requests
from requests_html import AsyncHTMLSession
from notion_client import Client
from urllib.parse import urlparse
import asyncio
import nest_asyncio
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Imgur credentials
IMGUR_CLIENT_ID = '326b12ff922fa0b'

# Notion credentials
NOTION_TOKEN = 'secret_8sdnrAKx6tCdNwDhu6fjmBmaZf23vaRbGbMGdnyKm5q'
DATABASE_ID = '32109f9347b041aa963712d943f572aa'

# Google Drive credentials
SERVICE_ACCOUNT_JSON = os.getenv('SERVICE_ACCOUNT_JSON')
FOLDER_ID = '1l4PKOPz-auCi1z0GZOa4Ok7DQ09pXoGv'  # Update this with your folder ID

# Write the service account JSON to a file
SERVICE_ACCOUNT_FILE = '/tmp/service_account.json'
with open(SERVICE_ACCOUNT_FILE, 'w') as f:
    f.write(SERVICE_ACCOUNT_JSON)

# Scopes for Google Drive API
SCOPES = ['https://www.googleapis.com/auth/drive.file']

nest_asyncio.apply()

print("Script started")

# Authenticate and create the Google Drive service
credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES)
drive_service = build('drive', 'v3', credentials=credentials)

# Notion client
notion = Client(auth=NOTION_TOKEN)

async def scrape_x_link(x_link):
    print(f"Scraping link: {x_link}")

    session = AsyncHTMLSession()
    response = await session.get(x_link)
    await response.html.arender(sleep=5)  # Render the JavaScript

    # Extract post text
    post_text = ''
    try:
        tweet_content = response.html.find('div[data-testid="tweetText"]', first=True)
        post_text = tweet_content.text if tweet_content else 'No description available'
    except Exception as e:
        print(f"Failed to extract post text: {e}")

    # Extract author
    author = ''
    try:
        author_tag = response.html.find('div[data-testid="User-Name"] span', first=True)
        author = author_tag.text if author_tag else 'Unknown author'
    except Exception as e:
        print(f"Failed to extract author: {e}")

    # Extract images
    images = []
    try:
        image_tags = response.html.find('img[alt="Image"]')
        images = [img.attrs['src'] for img in image_tags]
    except Exception as e:
        print(f"Failed to extract images: {e}")

    post_image = images[0] if images else 'https://via.placeholder.com/150'

    return post_text, post_image, author, images

def upload_image_to_imgur(image_url):
    headers = {"Authorization": f"Client-ID {IMGUR_CLIENT_ID}"}
    response = requests.post("https://api.imgur.com/3/upload", headers=headers, data={"image": image_url})
    if response.status_code == 200:
        return response.json()["data"]["link"]
    else:
        print(f"Failed to upload image to Imgur: {response.status_code}, {response.text}")
        return None

def upload_image_to_google_drive(image_url, filename):
    try:
        # Download the image
        image_data = requests.get(image_url).content
        with open('/tmp/temp_image.jpg', 'wb') as f:
            f.write(image_data)

        # Upload to Google Drive with dynamic filename
        file_metadata = {
            'name': filename,
            'parents': [FOLDER_ID]
        }
        media = MediaFileUpload('/tmp/temp_image.jpg', mimetype='image/jpeg')
        file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id,webContentLink'
        ).execute()

        # Make the file public
        file_id = file.get('id')
        drive_service.permissions().create(
            fileId=file_id,
            body={'role': 'reader', 'type': 'anyone'}
        ).execute()

        # Get the direct download link
        shareable_link = file['webContentLink']
        return shareable_link
    except Exception as e:
        print(f"Failed to upload image to Google Drive: {e}")
    return None

def generate_filename_from_link(link):
    # Replace invalid filename characters with underscores
    filename = link.replace('https://', '').replace('/', '_').replace('?', '_').replace('=', '_').replace('&', '_')
    return filename

def save_to_notion(post_text, post_image, author, category, link):
    platform = urlparse(link).netloc
    filename = generate_filename_from_link(link)
    uploaded_image_url = upload_image_to_imgur(post_image) if post_image != 'https://via.placeholder.com/150' else None

    # Save the image to Google Drive as well
    google_drive_link = upload_image_to_google_drive(post_image, filename)

    data = {
        "parent": {"database_id": DATABASE_ID},
        "properties": {
            "Title": {"title": [{"text": {"content": author}}]},
            "Content": {"rich_text": [{"text": {"content": post_text}}]},
            "Platform": {"rich_text": [{"text": {"content": platform}}]},
            "Category": {"select": {"name": category}},
            "Link": {"url": link}
        }
    }

    if uploaded_image_url:
        data['properties']['Preview'] = {
            "files": [{"name": "image", "external": {"url": uploaded_image_url}}]
        }

    print("Data to be sent to Notion:", data)
    try:
        notion.pages.create(**data)
        print("Data saved to Notion successfully!")
        print(f"Image also saved to Google Drive: {google_drive_link}")
    except Exception as e:
        print(f"Failed to save data to Notion: {e}")

async def main():
    print("Main function started")
    x_link = 'https://x.com/aisolopreneur/status/1806116065866584489?s=52&t=5HGYPwHEzZYlYwwa8QPw9Q'  # Replace with an actual X link for testing
    category = 'Test Category'  # Ensure this is a valid select option in your Notion database
    print(f"Scraping link: {x_link} with category: {category}")
    post_text, post_image, author, images = await scrape_x_link(x_link)
    print(f"Scraped data - Text: {post_text}, Image: {post_image}, Author: {author}, Images: {images}")
    save_to_notion(post_text, post_image, author, category, x_link)
    print("Saved to Notion!")

if __name__ == "__main__":
    print("Executing main function")
    asyncio.run(main())
    print("Main function executed")
