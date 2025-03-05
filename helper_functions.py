def link_to_file_name(link: str):
    assert link.endswith(".html")
    if link.startswith("/"):
        link=link[1:]
    return link.replace("/", "_")
