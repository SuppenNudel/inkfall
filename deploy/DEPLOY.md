# Deploy on inkfall.de

This app runs with Gunicorn behind Nginx.

## Fastest setup on a remote Linux server

1. Log in as root on the server.
2. Clone the repository into `/home/inkfall/project`.
3. Run the setup script.

```bash
sudo bash /home/inkfall/project/deploy/setup.sh
```

The script will:
- install the required system packages,
- create the `inkfall` system user if needed,
- clone or update the Git repository,
- create the Python virtual environment,
- install dependencies,
- install the `systemd` service,
- install the Nginx vhost,
- enable the auto-update timer.

## Files used by deployment

- `deploy/setup.sh` – initial server setup
- `deploy/update.sh` – manual or scheduled pull + restart
- `deploy/inkfall-update.timer` – runs the update service every 5 minutes
- `deploy/inkfall-update.service` – fetches the latest code and restarts the app
- `deploy/inkfall.service` – app runtime service
- `deploy/inkfall.de.nginx.conf` – reverse proxy configuration

## Auto-update behaviour without polling

For a push-based deployment, use the included GitHub webhook receiver.

1. Set a shared secret in the service file.
2. Start the webhook service.
3. Register the webhook in GitHub for the repo.
4. Point the webhook URL at your server endpoint, for example:

```text
https://inkfall.de/github-webhook/
```

The webhook service listens on `127.0.0.1:9001` and runs `deploy/update.sh` whenever a GitHub `push` event is received.

### Configure the webhook secret

```bash
sudo systemctl edit inkfall-webhook.service
```

Add this override block:

```ini
[Service]
Environment="INKFALL_WEBHOOK_SECRET=your-long-random-secret"
```

Then reload and restart the service:

```bash
sudo systemctl daemon-reload
sudo systemctl restart inkfall-webhook.service
```

### GitHub webhook setup

In the GitHub repository settings, create a webhook with:
- Payload URL: `https://inkfall.de/github-webhook/`
- Content type: `application/json`
- Secret: the same value as `INKFALL_WEBHOOK_SECRET`
- Events: `Just the push event`

## Manual update

If you want to trigger an update manually:

```bash
sudo systemctl start inkfall-update.service
```

## Verify

```bash
sudo systemctl status inkfall.service
sudo systemctl status inkfall-update.timer
curl -I http://127.0.0.1:8085/
curl -I https://inkfall.de/
```

## Useful logs

```bash
journalctl -u inkfall.service -n 100 --no-pager
journalctl -u inkfall-update.service -n 100 --no-pager
sudo tail -n 100 /var/log/nginx/error.log
```
