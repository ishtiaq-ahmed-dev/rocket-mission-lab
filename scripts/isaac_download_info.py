"""Inspect NVIDIA's published workstation download without guessing URLs."""
from html.parser import HTMLParser
import json
import urllib.request


class Links(HTMLParser):
    def handle_starttag(self,tag,attrs):
        if tag=='a':
            url=dict(attrs).get('href','')
            if 'downloads.isaacsim.nvidia.com' in url and ('win' in url.lower()):
                print(url,flush=True)
                try:
                    with urllib.request.urlopen(urllib.request.Request(url,method='HEAD'),timeout=30) as response:
                        print(json.dumps(dict(status=response.status,bytes=response.headers.get('Content-Length'))),flush=True)
                except Exception as error:print(str(error),flush=True)


if __name__=='__main__':
    with urllib.request.urlopen('https://docs.isaacsim.omniverse.nvidia.com/latest/installation/download.html',timeout=30) as response:
        Links().feed(response.read().decode())
