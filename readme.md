# 自動化將Instagram動態轉發至Twitter
## 專案說明
利用AWS Lambda觸發，設定每分鐘透過IG API到指定帳號檢測是否有新貼文/動態，如果有，則抓取其media url，將該圖片/影片發佈到Twitter的Media API後，獲得該media的media id，接著，發佈到Twitter帳號中。

## 架構圖
![](https://i.imgur.com/kerZbG0.png)
流程比較麻煩的點有兩部分，各是ig端以及twitter端
1. instagram提供的graph api沒辦法直接取得別人帳號的貼文內容(像是圖片、影片網址)，因此需要透過徒法煉鋼方式，模擬登入、拿TOKEN，然後再透過另外的API去取回多媒體網址。
2. twitter上傳多媒體檔案需要多個步驟，第一步是要將多媒體檔傳到一個額外的media api server中，取得media id，而在上傳到media api server的過程中又有三步驟要做驗證，在結束前面的程序後，call twitter api發布貼文的指令，並附上前面得到的response: media id。
## 開發講解
**1. 登入並取得IG的csrftoken, sessionid, ds_user_id**
在這個階段中，必須準備一個實際的IG帳號來做Login行為
登入後取得csrftoken, sessionid, ds_user_id三個資訊以利後續操作
原因是IG的官方API裡，並沒有辦法直接用API讓你存取他人的貼文
官方API只能用來操作/查看自己帳號的內容
```python=
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
```
> 這邊特別要提醒的是 要小心不要在同一小時裡面打太多reuqest
> instagram api有防範機制 過多請求將會鎖住IP
> 就會得到response code 429: Too Many Requests



**2. 取得限時動態資訊**
由"https://i.instagram.com/api/v1/feed/user/{cookies}"這個url做GET
在發REQUEST的時候，header記得放入
```python=
{
    'User-Agent': 'Instagram 10.3.2 (iPhone7,2; iPhone OS 9_3_3; en_US; en-US; scale=2.00; 750x1334) AppleWebKit/420+'
}
```
以及剛剛拿到的csrftoken, sessionid, ds_user_id放入cookies中

**3. 拆解限時動態資訊(JSON)**
由剛剛的HTTP GET得到的response 架構如以下
![](https://i.imgur.com/P1PC04n.png)

而主要的內容都在items之中
items中將會有數個element，每個element都代表一個現在這個使用者有的限時動態
![](https://i.imgur.com/sRYJ4Ii.png)

舉例如以下
這個帳號目前可供觀看的限時動態有九個，因此上面得到的element也是0~8沒錯
![](https://i.imgur.com/OVei84a.png)

而各item中內的架構如以下，這邊稍微講一些關鍵的attribute就好
* taken_at:指這個限時動態發布的時間(可透過time.localtime轉為datetime型態)
* video_versions:可以用這個屬性推估，如果存在這屬性，表示這則限時動態為影片
* image_versions2:如果該貼文為圖片，圖片的url可以在此找到
![](https://i.imgur.com/BFNavyM.png)

這邊先以圖片的限時動態為講解內容
打開image version可以看到兩個element
這邊的兩個element其實都代表一樣的資訊
只是#0是高畫質 #1畫質較差罷了
因此我們都直接拿#0的url即可
![](https://i.imgur.com/dFDZBV4.png)

程式部分，tm這邊是要用來預留，之後可以給時間limit選擇要留下來的限時動態
(假設Lambda每分鐘call，就判斷此限時貼文是否為前一中所發出的，是則觸發)

```python=
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
```

**4. 登入Twitter API驗證**
這邊採用了函式庫Twython
https://twython.readthedocs.io/en/latest/
其實這個函式庫也只是幫你把大部分twitter official的一些步驟寫好
比較簡略 容易開發而已
```python=
class Twitter(object):
    def __init__(self, CONSUMER_KEY, CONSUMER_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET) -> None:
        print(f"initilize and verify twitter object....")
        self.twitter = Twython(CONSUMER_KEY, CONSUMER_SECRET,
                               ACCESS_TOKEN, ACCESS_TOKEN_SECRET)
        self.twitter.verify_credentials()
```
**5. 將IG的多媒體檔由Twitter Media Upload API上傳**
這邊的步驟跟一些官方教學的步驟比較不同
大部分的教學都是去打開local的圖片文件
但這邊因為我們使用的是url的圖片
所以透過request打get到url圖片
然後再轉用BytesIO接
就可以達到一樣的效果
```python=
# Image
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
```
在影片上傳這部分其實比起圖片複雜許多
> Upload happens in 3 stages:
        - INIT call with size of media to be uploaded(in bytes). If this is more than 15mb, twitter will return error.
        - APPEND calls each with media chunk. This returns a 204(No Content) if chunk is received.
        - FINALIZE call to complete media upload. This returns media_id to be used with status update.
https://developer.twitter.com/en/docs/twitter-api/v1/media/upload-media/api-reference/post-media-upload

基本上他是有三個步驟要做: INIT, APPEND, FINALIZE
有興趣可以自己去看document
但這邊因為我們直接用了函式庫就不用特別自己寫
```python=
# Video
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

```
特別要注意的是twitter.upload_video參數
media_category這邊要用對的型態 才會上傳成功
> The category that represents how the media will be used. This field is required when using the media with the Ads APIPossible values: amplify_video, tweet_gif, tweet_image, and tweet_video

**6. 由Twitter Media Upload API得到的media id發布至Twitter中**
```python=
 def uploadStatus(self, ids, type):
        print(f"========= start uploading status with one {type} attachment to twitter =========")
        for id in ids:
            self.twitter.update_status(
                status=f'{id[1]} story uploaded.',
                media_ids=[id[0]['media_id']]
            )
            print(f" | {id[0]['media_id']} successfully uploaded.")
```