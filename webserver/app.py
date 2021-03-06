from flask import Flask, render_template, request, session, redirect 
from flask_wtf import Form
from wtforms import RadioField, SelectField
import requests
import json
import pymongo
from pymongo import MongoClient
import string
import random



#Requirement for WTForms. Only used for dev. 
SECRET_KEY = 'development'


#location of MongoDB using Docker hostnames. Only valid in Compose
mongoAddr = "database:27017"





#initialise the MongoDB tables
client = MongoClient(mongoAddr)
locationDB = client.locationDB
groupsTable = locationDB.groupsTable

#Find out what zones are predefined in CMX. Will be used to populate Web form
zones = requests.request("GET", "http://cmxlocationsandbox.cisco.com/api/config/v1/zoneCountParams/1", auth=('learning','learning'))
zonesFormat = json.loads(zones.text)
zoneNames = zonesFormat['zoneDetails']
zoneList = []

#MAC Hardcoded while testing - will eventually be pulled from CMX / App
mac1 = '00:00:2a:01:00:40'
mac2 = '00:00:2a:01:00:3e'
mac3 = '00:00:2a:01:00:15'
mac4 = '00:00:2a:01:00:08'
mac5 = '00:00:2a:01:00:09'
mac6 = '00:00:2a:01:00:0a'




#Function to create a push service from CMX. 
def createNotification(name, zone, macAddress):
    #Data for creating notification. Note at the moment getting error from CMX - further troubleshooting required
    

    cmxData = {
        "name": name,
        "userId": "learning",
        "rules": [
            {
                "conditions": [
                    {
                        "condition": "inout.deviceType == client"
                    },
                    {
                        "condition": "inout.in/out == in"
                    },
                    {
                        "condition": "inout.hierarchy == " + zone
                    },
                    {
                        "condition": "inout.macAddressList == "+macAddress+";"
                    }
                ]
            }
        ],
        "subscribers": [
            {
                "receivers": [
                    {
                        "uri": ngrokTunnel,
                        "messageFormat": "JSON",
                        "qos": "AT_MOST_ONCE"
                    }
                ]
            }
        ],
        "enabled": True,
        "enableMacScrambling": False,
        "notificationType": "InOut"
    }



    cmxJSON = json.dumps(cmxData)

    print (cmxJSON)

    try:
        #print ('Im about to do something')
        header = {'content-type': 'application/json', 'accept': 'application/json'}
        response = requests.request("PUT" , "https://cmxlocationsandbox.cisco.com/api/config/v1/notification" , auth=('learning','learning') , headers = header, data = cmxJSON , verify=False )
        status_code = response.status_code
        print (status_code)
        if (status_code == 201):
            return name
        else:
            response.raise_for_status()
            print("Error occured in POST -->"+(response.text))
    except requests.exceptions.HTTPError as err:
        print ("Error in connection -->"+str(err))
    finally:
        if response : response.close()

def findNgrok():
    header = {'content-type' : "application/json"}
    url = "http://172.30.0.30:4040/api/tunnels"
    try:
        response = requests.request("GET", url, headers=header, verify=False)
        status_code = response.status_code
        if (status_code == 200):
            return json.loads(response.text)
        else:
            response.raise_for_status()
            print("Error occured in GET -->"+(response.text))
    except requests.exceptions.HTTPError as err:
        print ("Error in connection -->"+str(err))
    finally:
        if response : response.close()


#Address of ngrok tunnel for Dev. Used as destination for CMX notifications
ngrokRaw = findNgrok()
#print (ngrokRaw)
for tun in ngrokRaw['tunnels']:
    #print (tun['name'])
    if tun['name'] == 'listener (http)':
        ngrokTunnel = tun['public_url'] + ':80/location'
        #print (ngrokTunnel)
        break
    else:
        print ('Ngrok tunnel not created')


# Flask App provides Web form for Admins to define the tracking policy, is also a listener for notifications from CMX
app = Flask(__name__)
app.config.from_object(__name__)

# WTForm used to create inputs, validate and bring back to Python
class SimpleForm(Form):
    
    #Grab available Zones from CMX, create drop down based on those zones
    for oneZone in zoneNames:
        zoneList.append((oneZone['hierarchy'] , oneZone['name']))
    zone = SelectField(u'Zone', choices=zoneList)
    # Define users and PPE, some hardcoding here for Dev simplicity
    user1 = SelectField(u'User1', choices=[(mac1, 'John'), (mac2, 'Adam'), (mac3, 'Sarah')])
    ppe1 = SelectField(u'Ppe1', choices=[(mac4, 'Helmet'), (mac5, 'Vest'), (mac6, 'Goggles')])
    user2 = SelectField(u'User2', choices=[('None','None'), ('John', 'John'), ('Adam', 'Adam'), ('Sarah', 'Sarah')])
    ppe2 = SelectField(u'Ppe2', choices=[('None','None'), ('Helmet', 'Helmet'), ('Vest', 'Vest'), ('Goggles', 'Goggles')])


#Root is the web form used to define tracking policy
@app.route('/',methods=['post','get'])
def defineGroups():
    form = SimpleForm()
    if form.validate_on_submit():

        #Zone data from CMX must be transformed to be used for queries.
        zoneFormat = (form.zone.data).replace('/','>')
        
        name = "InOutNotifier" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))

        #Define the datatype that will populate MongoDB and define the tracking policy
        data = {'zone': zoneFormat , 'user1' : form.user1.data , 'ppe1' : form.ppe1.data, 'user2' : form.user2.data , 'ppe2' : form.ppe2.data, 'name' : name, 'destinationURL' : ngrokTunnel}
        
        
        #For Dev environment - only allow one definition at a time.
        #Before allowing a new definition, delete all others. 
        groupsTable.delete_many({})
        groupsTable.insert_one(data)
        #Create a CMX notification for movements on the user in the specified zone
        createNotification(name, zoneFormat , form.user1.data)
        response = requests.request("POST" , "http://cmxsim:80/inout" , data="")
    else:
        print (form.errors)
    return render_template('defineGroups.html',form=form)

#more

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80, debug=True)