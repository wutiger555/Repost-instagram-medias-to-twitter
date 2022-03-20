import re
import requests
import time
import sys
from datetime import datetime
from twython import Twython
from datetime import datetime, timedelta
from io import BytesIO


class Instagram(object):
    '''
        initilize instagram login information
        w/ getLoginConfig function to get the required parameters
        needed: a valid instagram account to do the loign
    '''
    def __init__(self, username, password) -> None:
        print(f"=== initilize instagram object with username: [{username}] ===")
        self.link = 'https://www.instagram.com/accounts/login/'
        self.login_url = 'https://www.instagram.com/accounts/login/ajax/'
        self.username = username
        self.password = password
        self.csrftoken = None
        self.sessionid = None
        self.ds_user_id = None
        self.mycookies = None
        self.myheaders = {
            'User-Agent': 'Instagram 10.3.2 (iPhone7,2; iPhone OS 9_3_3; en_US; en-US; scale=2.00; 750x1334) AppleWebKit/420+'}
        self.videos = []
        self.images = []

    def setLoginConfig(self, csrftoken, sessionid, ds_user_id):
        self.csrftoken = csrftoken
        self.sessionid = sessionid
        self.ds_user_id = ds_user_id

    def getLoginPayload(self):
        time = int(datetime.now().timestamp())
        payload = {
            'username': f'{self.username}',
            'enc_password': f'#PWD_INSTAGRAM_BROWSER:0:{time}:{self.password}',
            'queryParams': {},
            'optIntoOneTap': 'false'
        }
        return payload

    def getLoginConfig(self):
        success = False
        for i in range(0,5):
            try:
                print(f"try to get login config #{i}...")
                with requests.Session() as s:
                    r = s.get(self.link)
                    csrf = re.findall(r"csrf_token\":\"(.*?)\"", r.text)[0]
                    r = s.post(
                        self.login_url,
                        data=self.getLoginPayload(),
                        headers={
                            "User-Agent":
                            "Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/77.0.3865.120 Safari/537.36",
                            "X-Requested-With": "XMLHttpRequest",
                            "Referer": "https://www.instagram.com/accounts/login/",
                            "x-csrftoken": csrf
                        })
                    if(r.status_code==429):
                        print('[',r.status_code,'] Too Many Reqeusts!')
                        sys.exit(1)
                    self.setLoginConfig(
                        s.cookies['csrftoken'], s.cookies['sessionid'], s.cookies['ds_user_id'])

                    self.mycookies = {'ds_user_id':	self.ds_user_id,
                                    'sessionid':	self.sessionid,
                                    'csrftoken':	self.csrftoken}
                    success = True
            except Exception as e:
                print('failed with:',e)
                time.sleep(1)
                continue
            break
        if(success):
            print('login config success.')
        else:
            print('login config fail.')
            sys.exit(1)

    def getImages(self):
        return self.images
    def getVideos(self):
        return self.videos

    def getInsStory(self,target_username):
        # get user id by username with ?__a=1 parameter
        try:
            acc_info = requests.get(f"https://www.instagram.com/{target_username}/?__a=1",
                                     cookies=self.mycookies, headers=self.myheaders).json()
            user_id = acc_info['graphql']['user']['id']
            print('username:',target_username,' user_id:',user_id)
        except requests.exceptions.RequestException as e:
            print('no such user!')
            raise SystemExit(e)

        # get all reel medias by insta api
        try:
            item = requests.get("https://i.instagram.com/api/v1/feed/user/" + str(
                user_id) + "/reel_media/", cookies=self.mycookies, headers=self.myheaders).json()
            print("-------------------------------")
            print(f"successfully get {len(item)} stories.")
            print("-------------------------------")
        except requests.exceptions.RequestException as e:
            raise SystemExit(e)

        for m in item['items']:
            tm = time.strftime('%Y-%m-%d %H:%M:%S',
                               time.localtime(m['taken_at']))
            # now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # if now-timedelta(minutes=15)<tm:
            if 'video_versions' in m:
                self.videos.append([m['video_versions'][0]['url'], tm])
            else:
                self.images.append([m['image_versions2']
                                    ['candidates'][0]['url'], tm])


class Twitter(object):
    def __init__(self, CONSUMER_KEY, CONSUMER_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET) -> None:
        print(f"initilize and verify twitter object....")
        self.twitter = Twython(CONSUMER_KEY, CONSUMER_SECRET,
                               ACCESS_TOKEN, ACCESS_TOKEN_SECRET)
        self.twitter.verify_credentials()

    def sortImg(self, ids):
        media = [[]]
        n = 0
        # Twitter only can upload 4 images in one post
        for i, id in enumerate(ids):
            media[n].append(id)
            if((i+1) % 4 == 0):
                n += 1
                media.append([])
        return media

    def uploadImg(self):
        img = ins.getImages()
        if not img:
            print('there is no images.')
            return None
        mids = []
        for url in img:
            try:
                r = requests.get(url[0])
                photo = BytesIO(r.content)
                mids.append([self.twitter.upload_media(media=photo),url[1]])
                print(f" - successfully uploaded one photo to twitter media server.")
            except requests.exceptions.RequestException as e:
                raise SystemExit(e)
        return mids

    def uploadVid(self):
        vids = ins.getVideos()
        if not vids:
            print('there is no videos.')
            return None
        mids = []
        for url in vids:
            r = requests.get(url[0])
            video = BytesIO(r.content)
            mids.append([self.twitter.upload_video(media=video, media_type='video/mp4',media_category='amplify_video', check_progress=True),url[1]])
            print(f" - successfully uploaded one video to twitter media server.")
        return mids

    def uploadStatus(self, ids, type):
        print(f"========= start uploading status with one {type} attachment to twitter =========")
        for id in ids:
            self.twitter.update_status(
                status=f'{id[1]} story uploaded.',
                media_ids=[id[0]['media_id']]
            )
            print(f" | {id[0]['media_id']} successfully uploaded.")

if __name__ == '__main__':
    ins = Instagram(username='', password='')
    ins.getLoginConfig()
    ins.getInsStory(target_username='')

    twitter = Twitter(
        CONSUMER_KEY='',
        CONSUMER_SECRET='',
        ACCESS_TOKEN='',
        ACCESS_TOKEN_SECRET=''
    )

    video_media_ids = twitter.uploadVid()
    if video_media_ids is not None:
        twitter.uploadStatus(video_media_ids,'video')
    else:
        print('no videos are uploaded recently.')

    image_media_ids = twitter.uploadImg()
    if image_media_ids is not None:
        twitter.uploadStatus(image_media_ids,'image')
    else:
        print('no images are uploaded recently.')