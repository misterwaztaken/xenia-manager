# script is to check if github api is accessible in python 
# check on networks that have issue, if we can't access it
# we will have to use proxy which will suck
import requests
try:
    response = requests.get('https://api.github.com/users/xenia-project') 
    response.raise_for_status()
    print("Success!")
except requests.exceptions.RequestException as e:
    print(f"Error: {e}")