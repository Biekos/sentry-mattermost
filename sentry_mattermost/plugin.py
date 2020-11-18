# Copyright (c) 2015 NDrive SA
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

import urllib2
import logging

from sentry import tagstore
from sentry.plugins.bases import notify
from sentry_plugins.base import CorePluginMixin
from sentry.utils import json
from sentry.integrations import FeatureDescription, IntegrationFeatures
from string import Formatter
from sentry import digests, ratelimits

logger = logging.getLogger("sentry.integrations.sentry_mattermost.plugin")



def get_rules(rules, group, project):
    return ', '.join(rules)


def get_tags(event):
    tag_list = event.tags
    if not tag_list:
        return ()

    return ', '.join([':'.join(tagstore.get_tag_key_label(k), tagstore.get_tag_value_label(k, v))
            for k, v in tag_list])


class PayloadFactory:

    @classmethod
    def create(cls, plugin, event, template, rules):
        project = event.group.project

        if not template:
            # In some cases like after updating the plugin, template config variable can be
            # None, in that case we need a fallback.
            template = "__[{project@get_full_name}]({project@get_absolute_url})__\n__[{group@title}]({group@get_absolute_url})__\n{group@culprit}\n{rules}\n{tags}"

        names = [fn for _, fn, _, _ in Formatter().parse(template)
                 if fn not in {None, "rules", "tags"}]

        params = {"rules": "", "tags": ""}
        for name in names:
            getter = None
            particules = name.split("@")
            for particule in particules:
                if not getter:
                    getter = event.__getattribute__(particule)
                else:
                    getter = getter.__getattribute__(particule)

            if callable(getter):
                params[name] = getter()
            else:
                params[name] = getter

        if plugin.get_option('include_rules', project):
            params["rules"] = get_rules(rules, event.group, project)

        if plugin.get_option('include_tags', project):
            params["tags"] = get_tags(event)

        # \n is not correctly interpreted from the text field of sentry
        template = template.replace("\\n", "\n")
        text = template.format(**params)

        payload = {
            "username": "Sentry",
            "icon_url": "https://myovchev.github.io/sentry-slack/images/logo32.png",  # noqa
            "text": text
        }
        return payload


def request(url, payload):
    data = "payload=" + json.dumps(payload)
    # Prevent servers from rejecting webhook calls by adding a existing user agent
    req = urllib2.Request(url, data, headers={
                          'User-Agent': "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:57.0) Gecko/20100101 Firefox/57.0"})
    response = urllib2.urlopen(req)
    return response.read()


class MattermostPlugin(CorePluginMixin, notify.NotificationPlugin):
    title = 'Mattermost'
    slug = 'mattermost'
    description = 'Enables notifications for Mattermost Open Source Chat'
    version = '0.0.6'
    author = 'Andre Freitas <andre.freitas@ndrive.com>, Guillaume Lastecoueres<px9e@gmx.fr>'
    author_url = 'https://github.com/Biekos/sentry-mattermost'
    required_field = "webhook"
    conf_key = "mattermost"

    feature_descriptions = [
        FeatureDescription(
            """
            Enables notifications for Mattermost Open Source Chat.  
            """,
            IntegrationFeatures.ALERT_RULE,
        )
    ]

    def __init__(self):
        super(MattermostPlugin, self).__init__()
        logger.info("Mattermost plugin loaded")

    def get_config(self, project, **kwargs):
        return [
            {
                "name": "webhook",
                "label": "Webhook URL",
                "type": "url",
                "placeholder": "e.g. https://mattermost.example.com/hooks/00000000000000000",
                "required": True,
                "help": "Your custom mattermost webhook URL.",
            },
            {
                "name": "template",
                "label": "Template",
                "type": "string",
                "required": True,
                "default": "__[{project@get_full_name}]({project@get_absolute_url})__\n__[{group@title}]({group@get_absolute_url})__\n{group@culprit}\n{rules}\n{tags}",
                "help": "You can define the template that the plugin will post to mattermost. More info: https://github.com/Biekos/sentry-mattermost",
            },
            {
                "name": "include_rules",
                "label": "Include Rules",
                "type": "bool",
                "required": False,
                "help": "Include rules with notifications.",
            },
            {
                "name": "include_tags",
                "label": "Include tags",
                "type": "bool",
                "required": False,
                "help": "Include tags with notifications."
            },
            {
                "name": "debug",
                "label": "Debug mode",
                "type": "bool",
                "required": True,
                "help": "Enable logging",
            }]

    def is_configured(self, project):
        return bool(self.get_option("webhook", project))

    def notify_users(self, group, event, triggering_rules, **kwargs):
        project = event.group.project
        debug_mode = self.get_option('debug', project)
        webhook = self.get_option('webhook', project)
        if debug_mode:
            logger = logging.getLogger("sentry.integrations.sentry_mattermost.plugin")
            logger.info("DEBUG:webhook used: {}".format(webhook))
        template = self.get_option('template', project)
        if debug_mode:
            logger.info("DEBUG:template used: {}".format(template))
        payload = PayloadFactory.create(
            self, event, template, triggering_rules)
        if debug_mode:
            logger.info("DEBUG:payload: {}".format(payload))

        res = request(webhook, payload)

        if debug_mode:
            logger.info("DEBUG:request executed: {}".format(res))
        return res

    def get_plugin_type(self):
        return "notification"

    def should_notify(self, group, event):
        logger = logging.getLogger("sentry.integrations.sentry_mattermost.plugin")
        logger.info("DEBUG:Should notify?")
        project = event.project
        if not self.is_configured(project):
            logger.info("DEBUG: No, the project is not correctly configured")
            return False

        # If the plugin doesn't support digests or they are not enabled,
        # perform rate limit checks to support backwards compatibility with
        # older plugins.
        try:
            if not (
                hasattr(self, "notify_digest") and digests.enabled(project)
            ) and self.__is_rate_limited(group, event):
                logger = logging.getLogger(
                    u"sentry.plugins.{0}".format(self.get_conf_key()))
                logger.info("notification.rate_limited",
                            extra={"project_id": project.id})
                logger.info("DEBUG: No, the project has reched rate limitation")
                return False
        except Exception as e:
             logger.info("DEBUG: Rate limitation did crashed")
             logger.info(e)
        logger.info("DEBUG: Yes")
        return True
