import json
import logging
import os
import re
import sys
import unicodedata
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from flask import Flask, jsonify, request, render_template, send_from_directory
from flask_bootstrap import Bootstrap
from openai import AzureOpenAI

load_dotenv()
# Bing Maps API endpoint and token for geocoding
BING_MAPS_API_ENDPOINT = os.getenv("APPSETTING_BING_MAPS_API_ENDPOINT")
BING_MAPS_API_KEY = os.getenv("APPSETTING_BING_MAPS_API_KEY")
# Azure OpenAI endpoint and key for address extraction
AZURE_OPENAI_ENDPOINT = os.getenv("APPSETTING_AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_DEPLOYMENT = os.getenv("APPSETTING_AZURE_OPENAI_DEPLOYMENT")
AZURE_OPENAI_KEY = os.getenv("APPSETTING_AZURE_OPENAI_KEY")

app = Flask(__name__, static_url_path="/static")
app.config["SECRET_KEY"] = os.environ.get("APPSETTING_FLASK_SECRET_KEY")
bootstrap = Bootstrap(app)

stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
app.logger.handlers = [stream_handler]
app.logger.setLevel(logging.INFO)
app.logger.info("========== Starting app ==========")


@app.route("/")
def index():
    return render_template("index.html", BING_MAPS_API_KEY=BING_MAPS_API_KEY)


@app.route("/get_locations", methods=["GET"])
def get_locations():
    url = request.args.get("url")
    app.logger.info(f"Requested URL: {url}")

    text, next_url = scrape_text(url)
    addresses = extract_addresses(text)

    address_list = []
    location_list = []
    for a in addresses:
        lat_lon = get_lat_lon(a["address"])
        if lat_lon:
            address_list.append(a["address"])
            lat_lon["title"] = a["title"]
            location_list.append(lat_lon)

    app.logger.info(f"Found {len(address_list)} addresses")
    app.logger.info(f"Next URL: {next_url}")
    return jsonify({"addresses": address_list, "locations": location_list, "nextUrl": next_url})


@app.route("/favicon.ico")
def favicon():
    return send_from_directory(
        os.path.join(app.root_path, "static"), "favicon.ico", mimetype="image/vnd.microsoft.icon"
    )


def scrape_text(url):
    response = requests.get(url)
    if response.status_code != 200:
        return None
    soup = BeautifulSoup(response.text, "lxml")
    text = soup.get_text()
    text = re.sub(r"\n\s*\n", r"\n\n", text.strip(), flags=re.M)

    next_button = soup.find("a", string=re.compile(r"next|>")) or soup.select_one("li.next > a")
    try:
        next_url = urljoin(url, next_button.get("href"))
    except AttributeError:
        next_url = None
    return text, next_url


def extract_addresses(text):
    client = AzureOpenAI(
        api_key=AZURE_OPENAI_KEY,
        api_version="2023-05-15",
        azure_endpoint=AZURE_OPENAI_ENDPOINT,
    )

    prompt = (
        """Extract all addresses from the text between >>> and <<<
and return them as a comma-separated JSON list without line breaks:
[{"title": "Place Name", "address": "Streetname 12, City"}]
The title should be descriptive of the address.
Keep going until you have found all addresses.
If no addresses are found, return [].
The output must be valid JSON.
>>>
"""
        + text[:8000]  # truncate to avoid exceeding 4k tokens for prompt + response
        + """
<<<
Remember: you must find all addresses and the output must be valid JSON!
"""
    )

    response = client.chat.completions.create(
        model=AZURE_OPENAI_DEPLOYMENT,
        messages=[{"role": "user", "content": prompt}],
        stop="]",
        temperature=0.3,
    )
    content = response.choices[0].message.content + "]"
    app.logger.info(response.usage)
    content = repair_json(content)
    addresses = json.loads(content)

    return addresses


def repair_json(content):
    # try to close brackets if the the response is truncated
    if not (content == "[]" or content.endswith("}]")):
        app.logger.warning("Attempting to repair JSON string")
        last_bracket_index = content.rfind("}")
        content = content[: last_bracket_index + 1] + "]" if last_bracket_index != -1 else "[]"
    return content


def get_lat_lon(address):
    # The search had issues with accented characters, so we remove them
    address = strip_accents(address)
    # Make a request to Bing Maps API
    params = {"query": address, "key": BING_MAPS_API_KEY, "maxResults": 1}
    response = requests.get(BING_MAPS_API_ENDPOINT, params=params)
    # Parse the response to get lat-lon
    data = response.json()

    if (
        "resourceSets" in data
        and data["resourceSets"]
        and "resources" in data["resourceSets"][0]
        and data["resourceSets"][0]["resources"]
    ):
        location = data["resourceSets"][0]["resources"][0]["point"]["coordinates"]
        lat_lon = {"lat": location[0], "lon": location[1]}

        return lat_lon
    else:
        return None


def strip_accents(text):
    text = unicodedata.normalize("NFD", text).encode("ascii", "ignore").decode("utf-8")
    return str(text)


if __name__ == "__main__":
    app.run(debug=True)
