# Django SendGrid用サンプルプロジェクト
https://github.com/charly24/django-sendgrid
利用時のサンプルプロジェクト

構築/動作の流れは以下参照。
http://qiita.com/charly24/items/a820d1ff3a01be1cc475

※管理画面を見やすくするために[Django Grappelli](http://grappelliproject.com/)を導入しています

# 利用手順
## 環境構築
```
virtualenv --prompt "(sendgrid)" --python=/usr/bin/python3.5 virtualenv
source virtualenv/bin/activate
pip install -r requirements.txt
```

## settings.pyの以下箇所をSendGridの設定に従い記述する。
```
SENDGRID_EMAIL_USERNAME = ''
SENDGRID_EMAIL_PASSWORD = ''
SENDGRID_API_KEY = ''
```

## WEBサーバーの起動
```
./manage.py collectstatic
./manage.py runserver 127.0.0.1:8080
```
