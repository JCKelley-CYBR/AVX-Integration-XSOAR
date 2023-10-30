register_module_line('AVX-Integration', 'start', __line__())
#######################
# Description: AppViewX API Integration - for XSOAR
# Author: Joshua Kelley
# Creation: July 2023
#######################
 
#######################
#      Imports        #
#######################
import requests
import json
import base64
import urllib3
from datetime import datetime, timezone, timedelta
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
 
# https://helpcenter.appviewx.com/techdoc/index?GuideSearch%5Bversion_id%5D=48&GuideSearch%5Bproduct_id%5D=11&guide_html=2022.1.0_FP3/Platform/Platform%20Guides/webhelp-responsive/oxy_ex-1/Platform%20API%20Guide/output/retrieve_access_token_using_get_service_token_api.html&guide_pdf=2022.1.0_FP3/Platform/Platform%20Guides/platform_platform_guides.pdf
# Service Account Authentication
 
CLIENT_ID = demisto.params().get('credentials', {}).get('identifier') or demisto.params().get('client_id')
CLIENT_SECRET = demisto.params().get('credentials', {}).get('password') or demisto.params().get('secret')
URL_AUTH = 'https://<YOURINSTANCE>.appvx.com/avxapi/acctmgmt-get-service-token?gwsource=external'
URL_SEARCH = 'https://<YOURINSTANCE>.appvx.com/avxapi/certificate/search?gwsource=external'
URL_APPROVE = 'https://<YOURINSTANCE>.appvx.com/avxapi/certificate/workorder/update?gwsource=external'
URL_REQUEST = 'https://<YOURINSTANCE>.appvx.com/avxapi/visualworkflow-request-logs?gwsource=external&ids=REQUESTID'
 
######################
# Description: Test connection to AppViewX API
# Parameters: None
# Returns: 'ok' if successful, error message if not
######################
# replace the commonName keyword with a known certificate name in your AppViewX instance
def test_module():
    try:
        url = URL_SEARCH
        sessionId = authAVX()
        headers = {
            "Content-Type": "application/json",
            "Token": sessionId,
        }
        payload = {
            "input":{
                "category":"Server",
                "keywordSearch" : {
                    "commonName":"KEYWORDFORYOURTESTQUERY"
                }
            },
            "filter":{
                "max":"1",
                "start":"1",
                "sortColumn":"commonName",
                "sortOrder":"desc"
            }
        }
        response = requests.post(url, headers=headers, json=payload)
    except ValueError:
        return 'Connection Error: The URL or The API Credentials you entered are probably incorrect, please try again.'
    return 'ok'
 
######################
# Description: Create formatted token for AppViewX API authentication
# Parameters: None
# Returns: Formatted token
######################
def CreateToken():
    temp = CLIENT_ID + ':' + CLIENT_SECRET
    enc_creds = encode_base64(temp)
    token = "Basic " + enc_creds
    return token
 
######################
# Description: Encode string to base64
# Parameters: String
# Returns: Base64 encoded string
######################
def encode_base64(string):
    string_bytes = string.encode('utf-8')
    base64_bytes = base64.b64encode(string_bytes)
    encoded_string = base64_bytes.decode('utf-8')
    return encoded_string
 
######################
# Description: Authenticate to AppViewX API
# Parameters: None
# Returns: Session ID - returns 200 if successful
######################
def authAVX():
    url = URL_AUTH
    token = CreateToken()
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": token
    }
    payload = {
        'grant_type':'client_credentials'
    }
 
    response = requests.post(url, headers=headers, data=payload)
    if response.status_code == 200:
        token = json.loads(response.text)
        token = token['response']
        return token
    return response
 
######################
# Description: Get AppViewX Requests
# Parameters: None
# Returns: Response with requests matching criteria (Status = New Certificate)
######################
def GetRequests():
    url = URL_SEARCH
    sessionId = authAVX()
    headers = {
        "Content-Type": "application/json",
        "Token": sessionId,
    }
    payload = {
        "input":{
            "category":"Server",
            "keywordSearch" : {
                "certstatus":"New Certificate"
            }
        },
        "filter":{
            "max":"5",
            "start":"1",
            "sortColumn":"requestIds",
            "sortOrder":"desc"
        }
    }
    response = requests.post(url, headers=headers, json=payload)
    incidents = json.loads(response.text)
    incidents = incidents['response']['response']['objects']
    alert_return = []
    if len(incidents) > 0:
        for incident in incidents:
            if len(incidents) == 0:
                return alert_return
            if incident['status'] == 'New Certificate':
                requests_data = {}
                status = 0
                for requestid in incident['requestIds']:
                    request_data = GetRequestDetails(requestid)
                    if (request_data['created_time'] > getFetchInterval()):
                        key = f"Request_{requestid}"
                        requests_data[key] = request_data
                        status = 1
                if status == 0:
                    return
                # print(requests_data)
                merged_data = {**incident, **requests_data}
                incident_data = json.dumps(merged_data, indent=4)
                print(incident_data)
                alert_return.append(
                    {
                        'name': "AVX Certificate Request: " + incident['commonName'] + " " + incident['requestIds'][0],
                        'occurred': datetime.now(timezone.utc).astimezone().isoformat(),
                        'dbotMirrorId': incident['commonName'],
                        'rawJSON': incident_data
                    }
                )
    return alert_return
 
######################
# Description: Get AppViewX Request Details
# Parameters: requestId
# Returns: Response with request details (RequestId, Creation Time, etc.)
######################
def GetRequestDetails(requestId):
    requestId = requestId.replace('R', '')
    sessionId = authAVX()
    url = URL_REQUEST
    headers = {
        "Content-Type": "application/json",
        "Token": sessionId
    }
    url = url.replace('REQUESTID', requestId)
    response = requests.get(url, headers=headers)
    data = json.loads(response.text)
    data = data['response']['requestList'][0]
    return data
 
####################
# Description: This function will get the current time zone of the system
# Params: None
# Return: int. time zone offset
####################
def getFetchInterval():
    tz = timezone(timedelta(hours=0), name="UTC")
    interval = demisto.params().get('incidentFetchInterval')
    current_datetime = datetime.now(tz=tz) - timedelta(minutes=int(interval))
    unix_time = int(current_datetime.timestamp() * 1000)
    return unix_time
 
######################
# Description: Approve AppViewX Request
# Parameters: requestId, action
# Returns: API response - returns 200 if successful
######################
def ApproveRequest(requestId, action, stage):
    requestId = requestId.replace('R', '')
    url = URL_APPROVE
    sessionId = authAVX()
    headers = {
        "Content-Type": "application/json",
        "Token": sessionId,
    }
    payload = {
        "data": {
            "task_action": action
        },
        "header": {
            "request_id": requestId,
            "workorder_id": "0",
            "task_id": stage
        }
    }
 
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 200:
        return "Request " + requestId + " " + action + "d successfully"
    else:
        return response.text
 
######################
#    Main function   #
######################
def main():
    command = demisto.command()
    try:
        if command == 'test-module':
            return_results(test_module())
        elif command == 'fetch-incidents':
            demisto.incidents(GetRequests())
        elif command == 'avx-fetch-incidents':
            return_results(GetRequests())
        elif command == 'avx-get-request-details':
            return_results(GetRequestDetails(demisto.args().get('requestId')))
        elif command == 'avx-approve':
            return_results(ApproveRequest(demisto.args().get('requestId'), demisto.args().get('action'), demisto.args().get('stage')))
        elif command == 'avx-fetch-interval':
            return_results(getFetchInterval())
        else:
            raise NotImplementedError(f'AppViewX API error: '
                                      f'command {command} is not implemented')
    except Exception as e:
        return_error(str(e))
    pass
 
if __name__ in ('__main__', 'builtin', 'builtins'):
    main()
 
register_module_line('AVX-Integration', 'end', __line__())