import requests
import os
import json
from datetime import datetime
from datetime import timedelta
from decimal import Decimal
import smtplib
from email.message import EmailMessage
import boto3
from boto3.dynamodb.conditions import Key, Attr

print('App Online!')

swid = os.environ.get('swid')
espn_s2 = os.environ.get('espn_s2')
accessKey = os.environ.get('accessKey')
secretKey = os.environ.get('secretKey')
emailPassword = os.environ.get('emailPassword')


currentDate = datetime.now() + timedelta(days=-1)
oneWeekAgo = (datetime.now() + timedelta(days=-10)).strftime('%m/%d/%Y')
year = 2022

# Grab Latest Scoring Period for usage in filter_key

response = requests.get(
    'https://fantasy.espn.com/apis/v3/games/fba/seasons/{}/segments/0/leagues/140392?view=mLiveScoring'.format(year),
    cookies=({'swid': swid,
              'espn_s2': espn_s2}))

scoringPeriodID = int(response.json()['scoringPeriodId']-1)


# Set Up ESPN Data Pull

my_referer = 'https://fantasy.espn.com/basketball/leaders?leagueId=140392'

filter_key = {"players":{"filterSlotIds":{"value":[0,1,2,3,4,5,6,7,8,9,10,11]},"filterStatsForCurrentSeasonScoringPeriodId":{"value":[scoringPeriodID]},"sortAppliedStatTotal":None,"sortAppliedStatTotalForScoringPeriodId":{"sortAsc":False,"sortPriority":1,"value":scoringPeriodID},"sortStatId":None,"sortStatIdForScoringPeriodId":None,"sortPercOwned":{"sortPriority":3,"sortAsc":False},"limit":100,"offset":0,"filterRanksForScoringPeriodIds":{"value":[scoringPeriodID]},"filterRanksForRankTypes":{"value":["STANDARD"]}}}

response = requests.get('https://fantasy.espn.com/apis/v3/games/fba/seasons/{}/segments/0/leagues/140392?view=kona_player_info'.format(year),
                      headers={'referer': my_referer,
                               'x-fantasy-filter': json.dumps(filter_key)},
                      params=({"players": {"limit": 1500,"sortDraftRanks": {"sortPriority": 100,"sortAsc": True,"value": "STANDARD"}}}),
                      cookies=({'swid': '{9D2E12F3-96FE-407C-AB32-8C043850DBD3}',
                          'espn_s2': 'AECUog3pWyF39KNJf%2B0wW6cgLRJgJoB4IeBYafbCU2iXRKQljQjCZFDz9NTr9fjeInoVXWRW1kn3NdN9%2FfgRgZct2YPqUN8r%2FAQ%2FmR19Wt9oRnpmvaXAbODW7fBS4lS6zv1aVhfq19nKB8Dw0FbFe9CM2K4h6XLqa9%2BLHmpSqeTVdu%2BpRTRTHB%2FdVXZ0wRmjni6vPFbPrUGMMphhK%2FwjOZxEhitBv1my21IgKkH8rf7anXnaRQ5tyy%2B0ymMDX7opvcTy5KN8uwfJaXEzZGZrj1J7' }))

json_stats = response.json()

# Prep Data for insertion into DynamoDB

playersList = []

for players in json_stats['players']:
    if players['onTeamId'] == 0 and players['player']['stats'][0]['appliedTotal'] > 23:
        playerDict = dict()
        playerDict['Name+Date'] = str(players['player']['fullName']) + ' ' + str(currentDate.strftime('%m/%d/%Y'))
        playerDict['Name'] = players['player']['fullName']
        playerDict['Points'] = Decimal(players['player']['stats'][0]['appliedTotal'])
        playerDict['Date'] = currentDate.strftime('%m/%d/%Y')
        playerDict['Status'] = players['status']
        playersList.append(playerDict)

if not playersList:
    print('No data today!')

else:

# Grab Past Week Info

    dynamodb = boto3.resource('dynamodb',aws_access_key_id=accessKey, aws_secret_access_key=secretKey, region_name='us-east-2')

    dytable = dynamodb.Table('WatchListPlayers')

    response = dytable.scan(FilterExpression=Attr("Date").gt(oneWeekAgo))

    items = response['Items']
    last_weeks_players = [x['Name'] for x in items]
    count_wk_players = []
    for x in set(last_weeks_players):
        wk_dict = dict()
        wk_dict['Player'] = x
        wk_dict['Count'] = last_weeks_players.count(x)
        count_wk_players.append(wk_dict)

# Combine dictionaries

    index_by_player = {d['Player']: d['Count'] for d in count_wk_players}

    for d in playersList:
        if d['Name'] in index_by_player:
            d['Count'] = index_by_player[d['Name']]
        else:
            d['Count'] = 0

# Insert Into DynamoDB

    for dicts in playersList:
        dytable.put_item(Item=dicts)

    print("Data inserted into DynamoDB")


    # Send email from dev snake

    emailData = 'These are the top unrostered scorers for yesterday, ' + currentDate.strftime('%m/%d/%Y') + ':\n' + '\n'

    for dicts in playersList:
        emailData += (dicts['Name'] + ' - ' + str(dicts['Points']) + ' (' + str(dicts['Status']) + ', '
                      + str(dicts['Count']) + ')' '\n')


    msg = EmailMessage()
    msg.set_content(emailData)

    msg['Subject'] = 'Free Agent Finds'
    msg['From'] = "snekbot95@gmail.com"
    msg['To'] = "ianpeck22@gmail.com"

    server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
    server.login("snekbot95@gmail.com", emailPassword)
    server.send_message(msg)
    server.quit()

    print("Email Sent!")

print('App Complete!')
