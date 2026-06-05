import os
import re
from dotenv import load_dotenv
import streamlit as st
from openai import OpenAI
from bs4 import BeautifulSoup
import requests
from urllib.parse import urljoin, urlparse
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, PageBreak)
from reportlab.lib.styles import getSampleStyleSheet
from io import BytesIO

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/137.0.0.0 Safari/537.36"
    )
}


# To fetch contact information before sending to AI

def extract_contact_info(soup):
    contacts = {
        "emails": set(),
        "phones": set(),
        "social_links": set()
    }

    # Extract Emails
    emails = re.findall(
        r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}',
        soup.get_text()
    )
    
    contacts["emails"].update(emails)
    # extract phone numbers
    raw_phones = re.findall(
        r'(?:\+\d{1,4}[\s\-]?)?(?:\(?\d{2,5}\)?[\s\-]?)?\d[\d\s\-\(\)]{7,}\d',
        soup.get_text()
    )

    phones = set()

    for p in raw_phones:

        p = p.strip()

        # Skip year ranges
        if re.match(r'^\d{4}\s*-\s*\d{4}$', p):
            continue

        digits_only = re.sub(r'\D', '', p)

        if 8 <= len(digits_only) <= 15:
            phones.add(p)

    contacts["phones"].update(phones)

    # Social Media Links
    social_domains = [
        "linkedin.com",
        "facebook.com",
        "instagram.com",
        "twitter.com",
        "x.com",
        "youtube.com",
        "tiktok.com",
        "pinterest.com"
    ]

    for a in soup.find_all("a", href=True):
        href = a["href"]

        for domain in social_domains:
            if domain in href:
                contacts["social_links"].add(href)

    return contacts


# To fetch data from the website
def fetch_website_and_product_pages(url: str):

    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()

    soup = BeautifulSoup(response.content, "html.parser")

# Extract contact info
    contact_info = extract_contact_info(soup)                          

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
            page_contacts = extract_contact_info(page_soup)

            contact_info["emails"].update(page_contacts["emails"])
            contact_info["phones"].update(page_contacts["phones"])
            contact_info["social_links"].update(page_contacts["social_links"])


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
    combined_content = f"""
    EXTRACTED CONTACT INFO

    Emails:
    {list(contact_info['emails'])}

    Phones:
    {list(contact_info['phones'])}

    Social Links:
    {list(contact_info['social_links'])}

    ==================================================

    """ + combined_content

    return combined_content[:15000], contact_info
            

# To get the API key
load_dotenv()
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
google_api_key = os.getenv("GEMINI_API_KEY")
client = OpenAI(base_url=GEMINI_BASE_URL, api_key=google_api_key)
MODEL = "gemini-2.5-flash"

# Calling Gemini

system_prompt = """
You are an expert business analyst.

Analyze website content and provide a structured report.

If information is not available, write 'Not Found'.
"""

chat_system_prompt = """
You are an AI business analyst.

Answer questions ONLY using the website content provided.

If information is unavailable, say:

'This information was not found in the website.'

Do not make assumptions.
"""

user_prompt_prefix = """
Analyze the website content thoroughly.

First determine what type of website it is. Possible categories include:
- Company / Business
- E-commerce
- Blog
- News
- Educational
- Government
- Nonprofit
- Personal Portfolio
- Documentation
- Community / Forum
- Other

# Industry

Identify the primary industry or domain of the website.

Examples:
- Automotive
- Banking & Finance
- Insurance
- Healthcare
- Education
- Information Technology
- E-commerce
- Manufacturing
- Real Estate
- Travel & Hospitality
- Media & Entertainment
- Government
- Nonprofit
- Telecommunications
- Consulting
- Energy & Utilities
- Logistics & Supply Chain
- Other

Then generate a structured report tailored to the website type.

Include the following sections:

# Website Type
Identify the most likely category of the website.

# Industry
Identify the primary industry or business domain the website belongs to.

# Purpose
Explain the primary purpose and goals of the website.

# Target Audience
Who is this website intended for?

# Key Topics
List the main topics, products, services, categories, or content areas covered.

# Important Information
Summarize the most important information a visitor should know.

# Navigation Insights
Describe the major sections, pages, products, services, or resources discovered from the website content.

# Key Features
Highlight unique capabilities, offerings, strengths, or differentiators.

# Products and Services
If applicable, list products, services, plans, solutions, or offerings with short descriptions.
If not applicable, state "Not Applicable".

# Contact Information

- Contact information will be displayed separately by the application.
- Do not create a Contact Information section in your response.

# Business Insights
If this is a company/business website, provide:
- Value proposition
- Customer segments
- Competitive advantages

Otherwise state "Not Applicable".

# Content Insights
If this is a blog, news, educational, documentation, or content-focused website, provide:
- Main themes
- Content focus
- Noteworthy resources
-Do not display sections that are not relevant to the website type.

# Executive Summary
Provide a concise summary in 5-10 bullet points.

# Analysis Confidence
High / Medium / Low

Explain briefly how much information was available on the website.

Important:
- Be factual and avoid assumptions.
- Clearly indicate when information is not available.
- Use clean markdown formatting.
- Base the analysis only on the provided website content.
- Use markdown headings exactly as provided.
- Do not skip any section.
- If information is unavailable, write "Not Found".
- Only include sections that contain meaningful information.
- Do not create empty sections.
- Do not display sections that are not relevant to the website type.

Website Content:

"""

# summarize the content
def summarize(url: str) -> str:
    website, contact_info = fetch_website_and_product_pages(url)
    response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt_prefix + "\n\nEXTRACTED CONTACT INFO:\n" +
                f"Emails: {list(contact_info['emails'])}\n" +
                f"Phones: {list(contact_info['phones'])}\n" +
                f"Social Links: {list(contact_info['social_links'])}\n\n" + website}])
    return (response.choices[0].message.content, contact_info, website)



# For chatbot
def chat_with_website(question, website_content):

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": chat_system_prompt
            },
            {
                "role": "user",
                "content":
                f"""
Website Content:

{website_content}

Question:

{question}
"""
            }
        ]
    )

    return response.choices[0].message.content

# Function to generate pdf report
def create_pdf(summary, contact_info):

    buffer = BytesIO()

    doc = SimpleDocTemplate(buffer)

    styles = getSampleStyleSheet()

    story = []

    # Title
    story.append(Paragraph("Website Intelligence Report", styles["Title"]))
    story.append(Spacer(1, 20))

    # Summary Section
    story.append(Paragraph("Analysis Report", styles["Heading1"]))
    story.append(Spacer(1, 10))
    for line in summary.split("\n"):

        if line.startswith("#"):
            heading = line.replace("#", "").strip()
            story.append(Paragraph(heading, styles["Heading2"]))

        elif line.strip():
            story.append(Paragraph(line, styles["BodyText"]))
    
    # Contact Information
    story.append(Spacer(1, 20))

    story.append(
        Paragraph("Contact Information", styles["Heading1"]))

    # Emails
    story.append(Paragraph("Emails", styles["Heading2"]))
    for email in contact_info["emails"]:
        story.append(Paragraph(email, styles["BodyText"]))

    # Phones
    story.append(Paragraph("Phone Numbers", styles["Heading2"]))
    for phone in contact_info["phones"]:
        story.append(Paragraph(phone, styles["BodyText"]))  

    # Social Links
    story.append(Paragraph("Social Links", styles["Heading2"]))
    for link in contact_info["social_links"]:
        story.append(Paragraph(link, styles["BodyText"]))  

    # Footer
    story.append(Spacer(1, 30))
    story.append(Paragraph("Generated by AI Website Intelligence Analyzer", styles["Italic"]))

    # Finish
    doc.build(story)

    buffer.seek(0)

    return buffer



# Streamlit APP

st.set_page_config(page_title="Website Analyzer", page_icon="🌐", layout="wide")

st.markdown("""
<style>

.stTextInput input {
    border: 2px solid #3B82F6 !important;
    border-radius: 12px !important;
    padding: 12px !important;
    background-color: white !important;
}

</style>
""", unsafe_allow_html=True)

st.markdown("""
<style>

.stApp {
    background: linear-gradient(
        135deg,
        #f8fbff 0%,
        #eef4ff 40%,
        #fdfdff 100%
    );
}

</style>
""", unsafe_allow_html=True)

st.markdown("""
<style>

.stButton button {
    background-color: #2563EB;
    color: white;
    border-radius: 10px;
    font-weight: bold;
    padding: 10px 20px;
}

</style>
""", unsafe_allow_html=True)

st.markdown("""
# 🌐 Website Intelligence Analyzer

### Transform any website into actionable business intelligence

Analyze industries, extract contacts, discover products & services, and generate AI-powered reports.
""")

st.write("Enter a website URL to generate an AI-powered intelligence report.")

url = st.text_input("Enter Website URL")

# Analyze Button
if st.button("🔍 Analyze Website"):

    if not google_api_key:
        st.error(
            "Google API not found. Please set the GEMINI_API_KEY environment variable."
        )

    elif url:

        with st.spinner("Analyzing website and generating report..."):

            try:

                summary, contact_info, website_content = summarize(url)

                st.session_state["website_content"] = website_content
                st.session_state["summary"] = summary
                st.session_state["contact_info"] = contact_info
                st.session_state["analysis_complete"] = True

            except Exception as e:

                if "429" in str(e):
                    st.error(
                        "Daily Gemini API quota exceeded. Please try again later."
                    )
                else:
                    st.error(f"An error occurred: {e}")

    else:
        st.error("Please enter a valid URL.")


# ==========================================
# SHOW RESULTS FROM SESSION STATE
# ==========================================

if st.session_state.get("analysis_complete", False):

    summary = st.session_state["summary"]
    contact_info = st.session_state["contact_info"]

    emails = "\n".join(contact_info["emails"])
    phones = "\n".join(contact_info["phones"])
    socials = "\n".join(contact_info["social_links"])

    full_report = f"""
{summary}

========================================

EXTRACTED CONTACT INFORMATION

Emails:
{emails}

Phones:
{phones}

Social Links:
{socials}
"""

    pdf_file = create_pdf(summary, contact_info)

    # Dashboard Metrics
    col1, col2, col3 = st.columns(3)

    with col1:
        st.info("🏢 Industry Detection")

    with col2:
        st.info("📞 Contact Extraction")

    with col3:
        st.info("📄 AI Reports")

    st.divider()

    # Download Buttons
    col1, col2 = st.columns(2)

    with col1:
        st.download_button(
            label="📥 Download TXT Report",
            data=full_report,
            file_name="website_analysis.txt",
            mime="text/plain"
        )

    with col2:
        st.download_button(
            label="📄 Download PDF Report",
            data=pdf_file,
            file_name="website_analysis.pdf",
            mime="application/pdf"
        )

    st.divider()

    tab1, tab2 = st.tabs(
        [
            "📊 Analysis Report",
            "📞 Contact Information"
        ]
    )

    # =====================
    # TAB 1
    # =====================

    with tab1:

        st.markdown(summary)

        st.divider()

        st.subheader("💡 Ask AI About This Website")

        suggestions = [
            "Who are the likely competitors?",
            "What growth opportunities exist?",
            "What business risks can be identified?",
            "Summarize this company for an investor.",
            "What products and services generate revenue?"
        ]

        for i, q in enumerate(suggestions):

            if st.button(q, key=f"suggestion_{i}"):

                answer = chat_with_website(
                    q,
                    st.session_state["website_content"]
                )

                st.session_state["selected_answer"] = answer
                st.session_state["selected_question"] = q

        st.divider()

        st.subheader("💬 Ask Your Own Question")

        custom_question = st.text_input(
            "Ask anything about this website",
            key="custom_question"
        )

        if st.button("Ask AI", key="ask_ai_button"):

            if custom_question:

                answer = chat_with_website(
                    custom_question,
                    st.session_state["website_content"]
                )

                st.session_state["selected_answer"] = answer
                st.session_state["selected_question"] = custom_question

        if "selected_answer" in st.session_state:

            st.divider()

            st.markdown(
                f"### ❓ {st.session_state['selected_question']}"
            )

            st.write(
                st.session_state["selected_answer"]
            )

    # =====================
    # TAB 2
    # =====================

    with tab2:

        st.subheader("Emails")

        if contact_info["emails"]:
            for email in contact_info["emails"]:
                st.info(email)
        else:
            st.warning("No emails found.")

        st.subheader("Phone Numbers")

        if contact_info["phones"]:
            for phone in contact_info["phones"]:
                st.success(phone)
        else:
            st.warning("No phone numbers found.")

        st.subheader("Social Links")

        if contact_info["social_links"]:
            for link in contact_info["social_links"]:
                st.markdown(f"- [{link}]({link})")
        else:
            st.warning("No social links found.")   
                


