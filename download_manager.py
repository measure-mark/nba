from .request_throttle import RequestThrottle
from .helper_functions import link_to_file_name
import os
import requests

class DownloadManager:
    def __init__(self):
        self.counter=RequestThrottle()
    
    def download_if_new(self, base_url: str, link: str, verbose=False):
        """returns True, webpage if freshly downloaded,
        return False, webpage is cached
        """

        assert base_url.endswith("/") or link.startswith("/")

        fn = link_to_file_name(link)
        if os.path.exists(fn):
            if verbose: print(f"Returning cached version of: {fn}")
            with open(fn, "rb") as reader:
                return False, reader.read()

        url=(f"{base_url}{link}")

        self.counter.throttle()
        response = requests.get(url)
        self.counter.add()
        if response.status_code!=200:
            self.response=response
            raise Exception("bad status code")

        with open(fn, "wb") as writer:
            writer.write(response.content)

        return True, response.content
