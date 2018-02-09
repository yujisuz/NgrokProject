#! /usr/bin/python3.4
import os
import time
import requests
import subprocess
import datetime
import json
import pprint
from ciscosparkapi import CiscoSparkAPI

APP_BASE_PATH = os.path.dirname(os.path.abspath(__file__))
PID_FILE_PATH = APP_BASE_PATH + '/data/NGROK.pid'
END_FILE_PATH = APP_BASE_PATH + '/data/NGROK_END'
TOKENS_FILE_PATH = APP_BASE_PATH + '/conf/.tokens.json'
YML_FILE_PATH = APP_BASE_PATH + '/conf/ngrok.yml'
PGREP_NAME = 'ngrok'
STAT_TERMINATE = -1 
STAT_DEAD = 0
STAT_ALIVE = 1
STAT_EXPIRE = 2
#PROCESS_LIFECYCLE = 1 # min
PROCESS_LIFECYCLE = 59 * 1# min
HEALTHCHECK_INTERVAL = 10# sec
def getUri():
    ret = dict()
    headers = {'Content-Type': 'application/json'}
    # delete tunnel not in use
    deleteUrl = 'http://localhost:4040/api/tunnels/web (http)'
    requests.delete(url=deleteUrl, headers=headers)

    time.sleep(1) # wait to reflected delete request
    tunnelsUrl = 'http://localhost:4040/api/tunnels'
    apiRet = requests.get(url=tunnelsUrl, headers=headers).json()
    for tunnel in apiRet.get('tunnels'):
        ret[tunnel.get('proto')] = tunnel.get('public_url')
    return ret

def sendSparkMessage(message, type='text'):
    jf = open(TOKENS_FILE_PATH, 'r')
    tokens = json.load(jf)
    jf.close()

    api = CiscoSparkAPI(access_token=tokens.get('notify_bot_token'))
    toPerson = tokens.get('notify_dest') 

    if type == 'markdown':
        api.messages.create(toPersonEmail=toPerson, markdown=message)
    else:
        api.messages.create(toPersonEmail=toPerson, text=message)

    return

def updateWebhook(url):
    jf = open(TOKENS_FILE_PATH, 'r')
    tokens = json.load(jf)
    jf.close()
    api = CiscoSparkAPI(access_token=tokens.get('webohook_bot_token'))
    retApi = api.webhooks.list()
    webhookName = 'WebhookForNgrok'
    webhookId = None
    for webhook in retApi:
        webhookDict = webhook._json_data

        if webhookName == webhookDict.get('name'):
            webhookId = webhookDict.get('id')
            break

    api.webhooks.update(webhookId=webhookId, name=webhookName, targetUrl=url)
    return

def notifyUri(uris):
    ngrokUrl = 'https://dashboard.ngrok.com/status'
    now = datetime.datetime.now()
    strNow = now.strftime('%b-%d %H:%M')
    message = '[{0} -  Established]({1})\n\n'.format(strNow, ngrokUrl)
    for proto, uri in uris.items():
        message += '* {0}'.format(uri) + '\n'
#    message += ngrokUrl
    sendSparkMessage(message=message, type='markdown')
    return

def healthcheck():
    if os.path.exists(END_FILE_PATH):
        return STAT_TERMINATE
    
    if getProcessIid(PGREP_NAME) < 0:
        return STAT_DEAD
 
    startAt = datetime.datetime.fromtimestamp(os.stat(PID_FILE_PATH).st_mtime)
    expireAt = startAt + datetime.timedelta(minutes=PROCESS_LIFECYCLE)
    current = datetime.datetime.now()
    if expireAt < current: 
        return STAT_EXPIRE

    return STAT_ALIVE

def getProcessIid(procname):
    cmd = 'pgrep -lf "{}"'.format(procname)
    cmdRetObj = subprocess.Popen(cmd, stdout=subprocess.PIPE, shell=True)
    cmdOut = cmdRetObj.communicate()[0]
    pids = cmdOut.decode('utf-8').split('\n') 
    ret = -1
    for line in pids:
        if line == '':
            continue
        
        pname = line.split(' ')[1]
        if procname == pname:
            ret = int(line.split(' ')[0])
            break

    return ret

def start():
    execcmd = 'nohup {0}/bin/ngrok start --config {1} web ssh &'.format(APP_BASE_PATH, YML_FILE_PATH)
    os.system(execcmd) 

    pid = getProcessIid(PGREP_NAME)
    f = open(PID_FILE_PATH, 'w')
    f.write(str(pid))
    f.close()

    time.sleep(3) # wait a few time for start API service
    uris = getUri()
    updateWebhook(uris.get('https'))
    notifyUri(uris)

    return

def stop():
    print('process stopping')
    pid = getProcessIid(PGREP_NAME)
    os.system('kill {}'.format(pid))
    time.sleep(1)

    if os.path.exists(PID_FILE_PATH):
        os.remove(PID_FILE_PATH)
    if os.path.exists(END_FILE_PATH):
        os.remove(END_FILE_PATH)
    return

def terminate():
    message = 'Service is gone to be terminated...'
    stop()
    print(message)
    sendSparkMessage(message=message)
    return

def main():
    try:
        start()
        while True:
            time.sleep(HEALTHCHECK_INTERVAL)
            stat = healthcheck()
            if stat == STAT_TERMINATE:
                terminate()
                break
            elif stat == STAT_DEAD:
                start()
            elif stat == STAT_ALIVE:
                continue
            elif stat == STAT_EXPIRE:
                stop()
                start()
            else:
                print('Unknown Status[{}]'.format(stat))
                continue
 
    finally:
        terminate()
    return 

if __name__ == "__main__":
    main()

