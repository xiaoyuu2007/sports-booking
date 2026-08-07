import sys
sys.path.insert(0, ".")
from api_client import VenueClient
import config

with open('webapp.py', 'r') as f:
    content = f.read()

# Modify /api/slots endpoint
old_endpoint = """            elif path=="/api/slots":
                nid=qs.get("nodeid",[""])[0]; dt=qs.get("date",[""])[0]
                d=get_client().get_available_times(nid,dt)
                self.ok_json({"success":True,"timeList":d.get("timeList",[]),"nodeList":d.get("nodeList",[]),"price":d.get("price",0)})"""

new_endpoint = """            elif path=="/api/slots":
                nid=qs.get("nodeid",[""])[0]; dt=qs.get("date",[""])[0]
                d=get_client().get_available_times(nid,dt)
                self.ok_json({"success":True,
                              "timeList":d.get("timeList",[]),
                              "nodeList":d.get("nodeList",[]),
                              "priceList":d.get("priceList",[]),
                              "conflictList":d.get("conflictList",[])})"""

if old_endpoint in content:
    content = content.replace(old_endpoint, new_endpoint)
    with open('webapp.py', 'w') as f:
        f.write(content)
    print("Patched backend successfully")
else:
    print("Could not find old endpoint")
