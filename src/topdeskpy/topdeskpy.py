import base64
import os
from pathlib import Path

import requests


class Topdeskclient:
    """
    base_url = "https://servicedesk.brkint.dk/tas/api"
    username = "BATCH_API_USER"
    password = PAM
    client = Topdeskclient(base_url, username, password)

    try:
        incident = client.create_incident(request="")
        print(f"Incident created: {incident}")
    except requests.exceptions.RequestException as e:
        print(f"Error creating incident: {e}")
        if hasattr(e, "response") and e.response is not None:
            print(e.response.text)
    """

    def __init__(self, base_url, username, password):
        self.base_url = base_url
        self.auth_header = self._generate_auth_header(username, password)

    def _generate_auth_header(self, username, password):
        auth_string = f"{username}:{password}"
        auth_bytes = auth_string.encode()
        auth_base64 = base64.b64encode(auth_bytes).decode("utf-8")
        return f"Basic {auth_base64}"

    def create_incident(self, callType="Information", request=None):
        server = os.environ.get("COMPUTERNAME")
        project_dir = Path(os.path.dirname(os.path.abspath(__file__))).name
        brief_description = f"Problem med Automatik: {project_dir}, server: {server}"

        incident_data = {
            "caller": {
                "dynamicName": "Teknikalarm",
                "branch": {
                    "id": "7161b8cb-e61a-44c9-bce4-0a5faf2d3f6c",
                },
            },
            "entryType": {"name": "Automatik"},
            "status": "secondLine",
            "briefDescription": brief_description,
            "request": request,
            "callType": {"name": callType},
            "category": {
                "name": "Software og systemer",
            },
            "subcategory": {
                "name": "Udvikling",
            },
            "operator": {
                "id": "1ad3793e-b04a-4ad2-9854-8a4650e9b600",
            },
            "operatorGroup": {
                "id": "1ad3793e-b04a-4ad2-9854-8a4650e9b600",
            },
            "impact": {"name": "Person"},
            "urgency": {"name": "Kan arbejde"},
            "priority": {"name": "4. Lav"},
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": self.auth_header,
        }
        response = requests.post(
            f"{self.base_url}{'/incidents'}",
            headers=headers,
            json=incident_data,
            verify=False,
        )
        response.raise_for_status()
        return response.json()

    def get_topdesk_template_id_by_template_number(self, template_number: str):
        headers = {
            "Content-Type": "application/json",
            "Authorization": self.auth_header,
        }

        url = f"{self.base_url}/tas/api/applicableChangeTemplates"

        response = requests.get(url, headers=headers, verify=False)

        if response.status_code >= 200 and response.status_code < 300:
            # filter the response for the template number
            for template in response.json()["results"]:
                if template["number"] == template_number:
                    return template["id"]
        else:
            raise Exception(f"Error: {response.status_code}, message: {response.text}")

    def get_changes_by_template(self, template_id):
        headers = {
            "Content-Type": "application/json",
            "Authorization": self.auth_header,
        }

        query = f"query=template.id=={template_id}"
        url = f"{self.base_url}/operatorChanges?{query}"

        response = requests.get(url, headers=headers, verify=False)

        if response.status_code >= 200 and response.status_code < 300:
            return response.json()
        else:
            raise Exception(f"Error: {response.status_code}, message: {response.text}")
