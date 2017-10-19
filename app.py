import json
import os
import signal
from tempfile import mkstemp

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('AppIndicator3', '0.1')
gi.require_version('Notify', '0.7')

from gi.repository import Gtk as gtk
from gi.repository import AppIndicator3 as appindicator
from gi.repository import Notify as notify

from slackclient import SlackClient


APPINDICATOR_ID = 'slack-status'

emoji_urls = {}


def preload_emoji_list(slack):
    """
    Pre-loads all Slack emoji URLs

    :Args:
        slack (SlackClient): Configured SlackClient instance
    """
    ret = slack.api_call('emoji.list')
    if not ret['ok']:
        return

    global emoji_urls
    emoji_urls = ret['emoji']


def get_emoji_filename(emoji):
    """
    Returns the filename of a locally-cached icon for the given emoji.
    Currently only works with custom emoji.

    :Args:
        emoji (str): The name of the emoji (without colons)

    :Returns:
        Path to the locally cached file (str) or None if not found
    """
    file = emoji_urls.get(emoji)
    if not file:
        return None

    if file.startswith('alias:'):
        alias = file.lstrip('alias:')
        return get_emoji_filename(alias)

    if file.startswith('http'):
        # Download and cache file
        import urllib.request
        url = emoji_urls[emoji]
        destination = mkstemp(suffix=os.path.basename(url))
        downloaded = urllib.request.urlretrieve(url, destination[1])

        file = emoji_urls[emoji] = downloaded[0]

    return file


class SlackStatus:
    def __init__(self):
        with open('config.json') as config_file:
            from collections import OrderedDict
            config = json.load(config_file, object_pairs_hook=OrderedDict)

        slack_token = config['slack_token']
        self.slack = SlackClient(slack_token)

        preload_emoji_list(self.slack)

        self.indicator = appindicator.Indicator.new(APPINDICATOR_ID, os.path.abspath('icon.png'), appindicator.IndicatorCategory.SYSTEM_SERVICES)
        self.indicator.set_status(appindicator.IndicatorStatus.ACTIVE)
        self.indicator.set_label('Slack Status', APPINDICATOR_ID)

        menu = gtk.Menu()

        for label, v in config['statuses'].items():
            icon = get_emoji_filename(v.get('emoji'))
            if icon:
                item = gtk.ImageMenuItem(label)
                img = gtk.Image()
                img.set_from_file(get_emoji_filename(v['emoji']))
                item.set_image(img)
                item.set_always_show_image(True)
            else:
                item = gtk.MenuItem(label)

            v['menu_item'] = item
            item.connect('activate', self.on_menu_click, label, v.get('text'), v.get('emoji'))
            menu.append(item)

        menu.append(gtk.SeparatorMenuItem())

        item_clear = gtk.MenuItem('Clear Status')
        item_clear.connect('activate', self.on_menu_click, 'Slack Status', '', '')
        menu.append(item_clear)

        item_quit = gtk.MenuItem('Quit')
        item_quit.connect('activate', quit)
        menu.append(item_quit)

        menu.show_all()
        self.indicator.set_menu(menu)

        notify.init(APPINDICATOR_ID)
        gtk.main()

    def on_menu_click(self, menu_item, label, status_text, status_emoji):
        self.indicator.set_label(label, APPINDICATOR_ID)

        if isinstance(menu_item, gtk.ImageMenuItem):
            self.indicator.set_icon(get_emoji_filename(status_emoji))
        elif not status_emoji:
            self.indicator.set_icon(os.path.abspath('icon.png'))

        if status_text and status_emoji:
            p = json.dumps({'status_text': status_text, 'status_emoji': ':'+status_emoji+':'})
        elif status_emoji and not status_text:
            p = json.dumps({'status_emoji': ':' + status_emoji + ':'})
        else:
            p = json.dumps({'status_text': '', 'status_emoji': ''})

        self.slack.api_call('users.profile.set', profile=p)


def quit(_):
    notify.uninit()
    gtk.main_quit()


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    SlackStatus()
