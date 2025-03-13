import re

def link_to_file_name(link: str):
    assert link.endswith(".html")
    if link.startswith("/"):
        link=link[1:]
    return link.replace("/", "_")

def validate_date(date:str):
    # Just check that it is 8 digits.
    # add in value checking for months and days as needed
    assert re.match(r'\d{8}$', date)