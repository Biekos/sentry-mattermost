Coucou

# Sentry Mattermost
A plugin for Sentry to enable notifications to Mattermost Open Source Chat.
This is based in the sentry-slack plugin: https://github.com/getsentry/sentry-slack

![Example](example.png)

# Usage
Install with pip and enable the plugin in a Sentry Project:

     pip2.7 install -e git+https://github.com/Biekos/sentry-mattermost.git@master#egg=sentry-mattermost

You may need to install git:

    apt install git

If you are using the docker version of sentry you need to enter into the right containers using: 

    docker exec -it sentry_onpremise_web_1 bash 
    docker exec -it sentry_onpremise_worker_1 bash 


Configure Mattermost:
- Create an Incoming Webhook
- Enable override usernames and profile picture icons in System Console Integrations

# Templating

You can change the template per project. It supports markdown. 

To configure the variable you need to write `{myvariable}`

Variable can design any attribute/function of the `group` class in https://github.com/getsentry/sentry/blob/master/src/sentry/models/group.py#L247

By doing `{group@message}` for example. 

Or any attribute/function of the `project` class in https://github.com/getsentry/sentry/blob/master/src/sentry/models/project.py#L78

By doing `{project@status}` for example. 

There are two specific variable `{rules}` and `{tags}` which when you want to include rules or tags will be replace by their content. 

The default value is:
`"__[{project@get_full_name}]({project@get_absolute_url})__\n__[{group@title}]({group@get_absolute_url})__\n{group@culprit}\n{rules}\n{tags}"`

# Contributing
We use Docker to setup a development stack. Make sure you have the latest
Docker Toolbox installed first.

### First time setup
Setups Docker containers and Sentry admin:

    make bootstrap restart

### Development
Each time you update the code, restart the containers:

    make restart

And access the sentry admin at

    http://<DOCKER IP>:8081
