import os
from dotenv import load_dotenv
import streamlit as st
from openai import OpenAI
from bs4 import BeautifulSoup
import requests
from urllib.parse import urljoin, urlparse

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/137.0.0.0 Safari/537.36"
    )
}

# To fetch data from the website
def fetch_website_and_product_pages(url: str) -> str:

    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()

    soup = BeautifulSoup(response.content, "html.parser")

    title = soup.title.string if soup.title else "No Title Found"

    # Homepage content
    for tag in soup(["script", "style", "img", "input"]):
        tag.decompose()

    homepage_text = (
        soup.body.get_text(separator="\n", strip=True)
        if soup.body
        else ""
    )

    combined_content = f"HOME PAGE\n\n{title}\n\n{homepage_text}"

    # Extract internal links
    relevant_links = []

    for a in soup.find_all("a", href=True):

        full_url = urljoin(url, a["href"])

        # Only crawl same domain
        if urlparse(full_url).netloc != urlparse(url).netloc:
            continue

        lower_url = full_url.lower()

        if any(keyword in lower_url for keyword in [
            "product",
            "products",
            "service",
            "services",
            "solution",
            "solutions"
        ]):
            relevant_links.append(full_url)

    # Remove duplicates
    relevant_links = list(set(relevant_links))

    # Limit pages to avoid huge prompts
    relevant_links = relevant_links[:5]

    # Scrape product/service pages
    for link in relevant_links:

        try:
            page_response = requests.get(
                link,
                headers=headers,
                timeout=10
            )

            page_response.raise_for_status()

            page_soup = BeautifulSoup(
                page_response.content,
                "html.parser"
            )

            for tag in page_soup(["script", "style", "img", "input"]):
                tag.decompose()

            page_title = (
                page_soup.title.string
                if page_soup.title
                else link
            )

            page_text = (
                page_soup.body.get_text(
                    separator="\n",
                    strip=True
                )
                if page_soup.body
                else ""
            )

            combined_content += (
                f"\n\n{'='*50}\n"
                f"PAGE: {page_title}\n"
                f"URL: {link}\n\n"
                f"{page_text[:3000]}"
            )

        except Exception as e:
            print(f"Failed to scrape {link}: {e}")

    return combined_content[:15000]
            

# To get the API key
load_dotenv()
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
google_api_key = os.getenv("GEMINI_API_KEY")
client = OpenAI(base_url=GEMINI_BASE_URL, api_key=google_api_key)
MODEL = "gemini-2.5-flash"

# Calling Gemini

system_prompt = """
You are helpful assistant that summarizes website content based on user queries and you keep it concise and in formated way.
"""

user_prompt_prefix = """
Analyze the company website and all discovered product/service pages.

Provide:

1. Company Overview
2. Products
3. Services
4. Key Features
5. Target Customers
6. Important Insights

Website Content:
"""

# summarize the content

def summarize(url: str) -> str:
    website = fetch_website_and_product_pages(url)
    response = client.chat.completions.create(model= MODEL, messages= [
        {"role":"system", "content":system_prompt},
        {"role":"user", "content":user_prompt_prefix + website}
    ])
    return response.choices[0].message.content

# Streamlit APP
st.set_page_config(
    page_title="Website Summarizer",
    page_icon="🌐"
)
st.title("AI Website Summarizer")
st.write("Please paste any website URL & get a clean summary.")

url = st.text_input("Enter website URL")

if st.button("Summarize"):
    if not google_api_key:
        st.error("Google API not found. Please set the GEMINI_API_KEY environtment variable.")
    elif url:
        with st.spinner("Summarizing...."):
            try:
                summary = summarize(url)
                st.markdown(summary)
            except Exception as e:
                st.error(f"An error occurred: {e}")
    else:
        st.error("Please enter a valid URL.")
