# -*- coding: utf-8 -*-

import logging
import re

import urllib.error
import urllib.request
from django.conf import settings
from django.core.mail import EmailMultiAlternatives, EmailMessage
from django_sendgrid.backends import SendGridEmailBackend

logger = logging.getLogger(__name__)

__RE_URL = re.compile(r'((https?):((//)|(\\\\))+[\w\d:#@%/;$()~_?\+-=\\\.&]*)')


def convert_html_mail(body):
    """
    plain textをHTML形式に変換する。
    - URLをリンク形式に修正
    - 改行をbrタグに変換
    - bodyタグの中に本文を入れる
    :param body: plain textの本文
    :return: HTML形式の本文
    """
    # <br />の後に\r\nを挿入していないとSendGrid側で長い１行と判断されて、
    # 990文字毎に改行コードが自動的に挿入されてしまう。
    #
    # 以下参考
    # - https://sendgrid.com/docs/Classroom/Build/Format_Content/html_formatting_issues.html
    # - http://bit.ly/2d4M3Pv
    body = __RE_URL.sub(r'<a href="\1" target="_blank">\1</a>', body)
    body = '<html>' \
           '<head><meta http-equiv="Content-Type" content="text/html; charset=UTF-8" /></head>' \
           '<body>{}</body></html>'.format(
                '<br />\r\n'.join(body.replace('\r', '').split('\n'))
            )
    return body


class CustomSendGridEmailBackend(SendGridEmailBackend):
    """
    django_sendgrid.SendGridEmailBackendの拡張。
    django.core.mail.send_mailからの送信とSendGridEmailMessage/SendGridEmailMultiAlternativesからの
    送信を透過的に取り扱う。
    この仕組を通すことで、send_mailを利用した際にもSendGridからのメール送信を行うことができるが、
    apps.lib.mail.sendmailに記載の通りコントローラブルなHTMLメールに変換させたり
    メールのカテゴリの指定を行うためにはsendmailを利用する必要がある。
    ※django_sendgridのSignalには対応させていない
    """
    def send_messages(self, email_messages):
        # INSTALLED_APPS評価前にこのファイル内のModelがloadされてしまうため、以下の警告が発生する。
        # RemovedInDjango19Warning: Model class django_sendgrid.models.DroppedEvent doesn't
        # declare an explicit app_label and either isn't in an application in INSTALLED_APPS
        # or else was imported before its application was loaded. This will no longer be supported
        # in Django 1.9.
        # そのため、Runtimeで実行時にloadするように修正している
        from django_sendgrid.models import save_email_message
        from django_sendgrid.message import SendGridEmailMessage, SendGridEmailMultiAlternatives

        _email_messages = []
        for m in email_messages:
            if isinstance(m, (SendGridEmailMessage, SendGridEmailMultiAlternatives)):
                # SendGridのメール送信Modelからの送信の場合はそのまま配列に入れる
                _email_messages.append(m)
            else:
                # そうでない場合、EmailMessageを継承しているのであればSendGrid用のインスタンスに詰め替える
                if isinstance(m, EmailMultiAlternatives):
                    instance = SendGridEmailMultiAlternatives(
                        subject=m.subject, body=m.body, from_email=m.from_email, to=m.to, bcc=m.bcc,
                        connection=m.connection, attachments=m.attachments, headers=m.extra_headers,
                        alternatives=m.alternatives, cc=m.cc, reply_to=m.reply_to,
                    )
                elif isinstance(m, EmailMessage):
                    # 後でHTMLメールを設定するので、EmailMessageでもMultiAlternativesに詰め替えている
                    instance = SendGridEmailMultiAlternatives(
                        subject=m.subject, body=m.body, from_email=m.from_email, to=m.to, bcc=m.bcc,
                        connection=m.connection, attachments=m.attachments, headers=m.extra_headers,
                        cc=m.cc, reply_to=m.reply_to,
                    )
                else:
                    raise NotImplementedError(
                        'email_message must be inherited EmailMessage or EmailMultiAlternatives')

                # HTMLメールの指定が無い場合、HTMLメールに変換する
                for alternative in m.alternatives:
                    if alternative[1] == 'text/html':
                        break
                else:
                    instance.attach_alternative(convert_html_mail(m.body), 'text/html')

                instance.prep_message_for_sending()
                save_email_message(sender=instance, message=instance)
                _email_messages.append(instance)

        return super().send_messages(_email_messages)


def remove_bounce(email):
    """
    SendGrid APIを利用してバウンスメールアドレスを除去する。
    ※API呼び出し時に想定外のエラーとなった場合、例外が発生する

    refs: https://sendgrid.kke.co.jp/docs/API_Reference/Web_API_v3/bounces.html
    :param email: 除去対象のメールアドレス
    :return: 除去ないしは未登録であった場合はTrue
    """
    headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer {}'.format(settings.SENDGRID_API_KEY)
    }
    url = 'https://api.sendgrid.com/v3/suppression/bounces/{}'.format(email)
    req = urllib.request.Request(url, headers=headers, method='DELETE')
    try:
        with urllib.request.urlopen(req):
            return True
    except urllib.error.HTTPError as e:
        if e.code == 404:
            # 未登録/解除済のメールアドレスを除去しようとすると404エラーとなる(正常)
            logger.info('{} has not registered as a bounce.'.format(email))
            return True
        else:
            # それ以外のエラーの場合、例外として処理する
            raise
