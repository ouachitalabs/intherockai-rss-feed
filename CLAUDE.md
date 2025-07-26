Use the makefile for all development commands.
The following targets are available:

Before doing anything, you have to activate the virtual environment with

```
. .venv/bin/activate
```

The `.venv/` directory lives in the root `intherock.ai/` folder.

Once activated, then you can run the following:

```
make help # see what's available
make install # updates any dependencies
make api # runs the api
```

All new packages must first be added to the requirements.txt file, then you run `make install` to sync your dependencies.

# Server Access
- ssh into the "server" using the following command: `ssh -i ~/.ssh/digitalocean_key app@services.ouachitalabs.com`

# Server Services
Running systemd services on services.ouachitalabs.com:
- `intherock-api.service` - InTheRock News Feed API (our main app)
- `nginx.service` - Web server and reverse proxy
- `ssh.service` - SSH server
- `cron.service` - Scheduled tasks
- `rsyslog.service` - System logging
- `do-agent.service` - DigitalOcean monitoring
- `droplet-agent.service` - DigitalOcean droplet agent
- Various system services (systemd-*, getty, etc.)

# Email Notifications
Email notifications are sent when new articles are processed. Configure with environment variables:

```bash
export SMTP_SERVER="smtp.gmail.com"
export SMTP_PORT="587"
export SENDER_EMAIL="your-email@gmail.com"
export SENDER_PASSWORD="your-app-password"
export RECIPIENT_EMAIL="recipient@example.com"
```

For Gmail, use an App Password instead of your regular password.